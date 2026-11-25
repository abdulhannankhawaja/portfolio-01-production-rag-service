# Design Decisions

## Architecture

The application separates configuration, schemas, parsing/chunking, vector
storage, generation, guardrails, service orchestration, HTTP routes, evaluation,
and tests:

- `app/config.py` owns environment-backed settings.
- `app/ingestion.py` validates/extracts supported files and creates chunks.
- `app/storage.py` owns embeddings, persistent Chroma, and the SQLite lifecycle
  registry.
- `app/generation.py` owns the local extractor and optional Gemini provider.
- `app/guardrails.py` validates questions, checks citations, and scans output.
- `app/services.py` coordinates operations and maps failures to safe service
  errors.
- `app/auth.py` owns user persistence, password hashing, and JWT helpers.
- `app/observability.py` stores local request traces and aggregate metrics.
- `app/main.py` wires the app, authentication dependencies, FastAPI routes,
  request logging, and per-process rate limiting.
- `frontend/src/` contains the React UI; Vite builds it into `app/static/` for
  FastAPI to serve.

Blocking parsing, embedding, database, and model operations run in FastAPI's
worker thread pool rather than on the async event loop.

### Upload flow

```text
PDF/DOCX/TXT/MD/PPTX request
  -> size/extension checks
  -> format-specific signature, encoding, archive, and expansion checks
  -> SHA-256 duplicate check
  -> page, slide, paragraph, heading, table, or plain-text extraction
  -> tokenizer-aware chunks with source metadata
  -> embed all chunks
  -> SQLite PENDING record
  -> Chroma PENDING vectors -> verify -> Chroma READY -> SQLite READY
  -> return document metadata
```

Failures after the pending record trigger vector and registry cleanup. A startup
recovery pass removes leftover PENDING records and vectors. This is a
best-effort lifecycle across SQLite and Chroma, **not an atomic distributed
transaction**. The original upload bytes are not retained, so delete removes
the registry row and all indexed vectors.

Supported formats are PDF, DOCX, TXT, Markdown, and PPTX. PDF pages and PPTX
slides retain numeric source locations; DOCX headings are retained as section
metadata. Scanned PDFs have no OCR support. Office ZIP archives are bounded
and integrity-checked; plain text must be UTF-8. These checks reject malformed
or structurally invalid input but are not malware scanning.

### Question flow

```text
question
  -> length/injection checks
  -> E5 query embedding
  -> Chroma cosine search, READY-only
  -> distance-to-similarity conversion and optional threshold gate
  -> local extractive answer or structured Gemini JSON
  -> validate cited chunk ids against this retrieval result
  -> output leak/grounding checks
  -> answer + trusted citation metadata + all fetched chunks
```

Retrieved document text and the user question are serialized as data and
separated from the Gemini system instruction. The prompt says not to follow
instructions inside retrieved text; structured output and server-side source
ID validation add checks beyond the prompt. This does not guarantee resistance
to every prompt injection or establish semantic truth.

## Chosen components and trade-offs

### Corpus

The checked-in evaluation corpus is two official NIST PDFs: the AI Risk
Management Framework 1.0 and Generative AI Profile. They provide focused,
legally reusable public policy content with page-level evidence. They are a
small, narrow corpus and do not test broad subject coverage or PPTX/TXT/MD
retrieval. DOCX, PPTX, TXT, and Markdown upload are tested with generated
fixtures, but there is no user-provided real DOCX evaluation document. Do not
treat the existing corpus labels or reference answers as user-reviewed.

### Text extraction and file validation

- **Chosen:** PyMuPDF for page-aware PDF text; `python-docx` for DOCX paragraphs,
  heading labels, and tables flattened into row text; `python-pptx` for slide
  text and tables; strict UTF-8 decoding for TXT and Markdown.
- **Rejected:** OCR for scanned PDFs and complex layout/table reconstruction;
  they add runtime/model dependencies and were not needed for this small
  text-first corpus.
- **Trade-off:** local extraction has no per-request API charge and preserves
  PDF pages/PPTX slides, but complex columns, headers/footers, and table
  relationships may be imperfect. Scanned/empty PDFs and encrypted files are
  rejected rather than assigned invented page text. Office archives have
  member/expanded-size limits; tables lose cell structure when flattened.

### Chunking

- **Chosen:** tokenizer-count windows with configurable overlap and preferred
  boundaries at paragraph, line, sentence, and word separators. Defaults are
  500 tokens with 100-token overlap.
- **Compared:** the offline run compares 400/100 and 500/100, changing only
  chunk size while keeping overlap fixed. Both settings fit within E5's input
  context; the evaluation runner rejects oversized passages instead of
  silently measuring truncated embeddings. Current measured
  Hit@5/Page Recall@5/MRR@5 are in [EVAL.md](./EVAL.md).
- **Rejected:** fixed character windows, because token budgets map more directly
  to embedding and generation context.
- **Trade-off:** overlap helps preserve boundary context but increases vector
  count, disk use, and indexing time. The gold set is too small to establish a
  general winner.

### Embeddings

- **Chosen:** local `intfloat/e5-small-v2`, normalized 384-dimensional vectors,
  with `query: ` and `passage: ` prefixes.
- **Rejected:** remote embeddings as the default because local inference avoids
  per-request charges and sending every document to an API.
- **Trade-off:** model download and CPU inference add setup time and latency;
  English-oriented E5 is not a multilingual guarantee. Cohere can be selected
  optionally, but model dimensions, terms, quota, and cost must be checked before
  enabling it. E5 prefixes are not applied to Cohere.

### Vector database and registry

- **Chosen:** persistent Chroma with cosine distance, plus a small SQLite
  registry for unique file hashes, document listing, and PENDING/READY state.
- **Rejected:** a cloud vector DB and managed SQL registry as mandatory
  dependencies; they add credentials, network latency, external data transfer,
  account/quota dependence, and possible cost.
- **Trade-off:** local operation is easy to reproduce and requires no provider
  account, but one local Chroma/SQLite data directory is not a distributed,
  multi-host production deployment. Back up `data/` securely; it contains
  extracted document content.
- Every Chroma chunk stores `chunk_id`, `document_id`, `file_name`, `sha256`,
  chunk position, page or section, and lifecycle status.

### Retrieval and score semantics

- **Chosen:** top-k defaults to 5; Chroma collection space is explicitly
  `cosine`. Because Chroma returns distance, the API reports
  `similarity = 1 - distance` and tests the conversion.
- **Threshold:** local E5 defaults to a diagnostic minimum similarity of 0.84,
  chosen from the small offline threshold sweep. It is not answer confidence.
  Five negative examples and twenty answerable examples are inadequate for a
  production decision; recalibrate on independently reviewed data.
- **Rejected:** hybrid search and reranking; the current small corpus does not
  justify another service or latency stage. Retrieval misses are listed in the
  evaluation report.

### LLM, generation, and grounding

- **Chosen:** a deterministic extractive local generator by default; optional
  Gemini generation uses a JSON response schema (`answer`, `answerable`,
  `cited_chunk_ids`), configured temperature, timeout, and bounded retries.
- **Rejected:** making a remote LLM mandatory; that would make a paid/quota-bound
  dependency essential and complicate reproducibility and data privacy.
- **Grounding policy:** answer only from retrieved chunks. The brief allows
  general knowledge, but this implementation deliberately does not supplement
  with uncited external facts. An unsupported response is a fixed refusal with
  no citations.
- The server checks cited IDs are a subset of chunks retrieved for the same
  request and constructs citation filenames/pages from stored metadata, not
  model-generated metadata. This validates citation identity, not every factual
  claim.
- Gemini privacy, price, rate limits, model availability, and data-use terms
  depend on the account and must be checked in current official documentation
  before use. Do not send confidential documents through an unapproved provider.

### API design

| Route | Purpose | Success |
|---|---|---|
| `POST /documents` | Validate and ingest supported formats; duplicate hashes rejected | 201 |
| `GET /documents` | List ready document metadata | 200 |
| `GET /documents/{id}` | Fetch one document's metadata | 200 |
| `DELETE /documents/{id}` | Delete vectors and registry row | 204 |
| `POST /questions` | Return answer, citations, and retrieved chunks | 200 |
| `POST /auth/signup` | Create an account with an Argon2id password hash | 201 |
| `POST /auth/login` | Authenticate and issue a signed bearer token | 200 |
| `GET /observability` | Get local metrics and recent request traces | 200 |
| `GET /health` | Process liveness | 200 |

`/ask` remains as an undocumented compatibility alias. Errors use consistent
FastAPI details: 400 invalid/extraction guardrail, 404 missing document, 409
duplicate, 413 too large, 415 unsupported type, 422 schema validation, 429
rate-limited, and 503 provider/storage failures. Upstream internals are not
returned to clients.

The question response includes `citations` built from trusted retrieved data
and `retrieved_chunks` for every answer, including refusals. Each fetched item
includes its rank, source, text, stable ID, and cosine similarity.

### Guardrails and limitations

- Empty, over-length, and common prompt-injection/jailbreak phrases are blocked
  before retrieval. Pattern checks are not a complete injection detector.
- Retrieval thresholding is a heuristic off-topic/weak-evidence gate, not a
  semantic confidence measure.
- Retrieved file text is untrusted. Gemini output must match the JSON schema and
  cite only retrieved IDs; local extraction does not execute document text.
- Document ownership is enforced for list, get, delete, and retrieval APIs.
  Passwords are stored as Argon2id hashes and access tokens are signed JWTs.
- Secret values are checked in generated answers. This scan does not detect
  every transformed, encoded, or partial leak.
- Citation-ID checks and lexical overlap do not prove answer correctness,
  faithfulness, or that every sentence is supported. Human review remains
  necessary.
- Upload checks are not a substitute for antivirus or general malware scanning.
- In-memory rate limiting is per process/IP and does not coordinate multiple
  workers. Local SQLite/Chroma storage is single-instance, not a distributed
  deployment.

## Evaluation and testing

The evaluation runner uses real text from the checked-in PDFs, 25 questions,
20 answerable and 5 out-of-corpus, and compares two chunking settings. It
reports retrieval, threshold/refusal behavior, local answer key-term overlap,
and citation-ID/page coverage. See [EVAL.md](./EVAL.md) for definitions,
results, misses, and limitations.

The tests run API behaviors with deterministic fakes plus a real local
Chroma/SQLite upload → query → delete path using fixed test embeddings. Tests
cover success and error cases, cleanup, score conversion, citations, rate
limits, and malformed provider results. The Jupyter notebook runs the service
pipeline on the checked-in NIST PDF corpus using a temporary local store. It
does not demonstrate a user-provided DOCX corpus, independently reviewed
labels, or human-graded answer quality.
