# Production RAG Service

A code-based PDF/DOCX retrieval-augmented question-answering API and minimal
browser frontend. The default stack runs locally: FastAPI, PyMuPDF,
python-docx, local E5 embeddings, persistent Chroma, and a SQLite document
registry. Gemini and Cohere are optional providers; neither is required to
start the service.

## Corpus

The checked-in evaluation corpus is the two official NIST PDFs:

- NIST AI RMF 1.0
- NIST AI 600-1, Generative AI Profile

These are public PDF sources selected earlier in the project. They are used for
retrieval evaluation, not as evidence that the required user-reviewed, mixed
PDF/DOCX corpus is complete. DOCX upload is covered with test fixtures; a
user-provided real DOCX and hand-reviewed evaluation labels are still needed
before claiming the corpus requirements are fully met.

## Requirements and setup

- Python 3.11 or newer
- Internet access on first use to download the local embedding model/tokenizer
- No Pinecone, Neon, Gemini, or Cohere account is required for local mode

```bash
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the frontend and
`http://127.0.0.1:8000/docs` for the OpenAPI/Swagger documentation.

The first local embedding request downloads `intfloat/e5-small-v2` if it is not
cached. Chroma vectors and the SQLite registry are stored under `data/`, which
is ignored by Git. Original uploaded files are not retained after extraction;
the service stores document metadata and extracted chunks.

## Configuration

Copy `.env.example` to `.env`. Never commit `.env` or paste credentials into
source files.

- `EMBEDDING_PROVIDER=local` uses the 384-dimensional E5 model on CPU.
- `EMBEDDING_PROVIDER=cohere` uses the optional Cohere embedding API; set its
  key and verify the current provider pricing, model availability, and quotas
  before enabling it.
- `GEMINI_API_KEY` enables Gemini answer generation. Without it, deterministic
  extractive generation is used. Check Google's current pricing, terms, model
  availability, and quotas before sending document content to the API.
- `CHUNK_SIZE` and `CHUNK_OVERLAP` are token counts, not characters.
- `TOP_K` controls retrieval count. `MIN_RETRIEVAL_SCORE` defaults to `0.84`
  for local E5. It is an empirically selected similarity cutoff from a small
  diagnostic set, not answer confidence; recalibrate before production use.
- Upload size, question length, provider timeout/retries, and per-process
  request rate are configurable in `.env.example`.

Optional providers can incur charges or have account-specific limits. This
project does not promise that third-party free tiers are available or sufficient.

## Features

- PDF and DOCX text extraction; PDF page citations and DOCX heading/section
  metadata. DOCX tables are flattened to text. Scanned PDFs are rejected; OCR
  is not implemented.
- Token-aware overlapping chunks with document ID, filename, page/section,
  position, and stable chunk ID metadata.
- SHA-256 duplicate detection and `PENDING` → `READY` lifecycle. Failed
  ingestion cleans up vectors; startup removes unfinished records.
- Chroma cosine retrieval; reported similarity is `1 - cosine_distance` and is
  not a confidence estimate.
- Structured generation output with server-validated retrieved chunk IDs.
  Unsupported or invalid answers fail closed; retrieved text is treated as
  untrusted data.
- Request IDs, latency/status logging without request content, per-process
  rate limiting, and bounded provider timeouts/retries.
- Persistent data is local and single-instance; the in-memory rate limiter is
  not distributed across workers.

## API

- `POST /documents` — upload PDF or DOCX (201)
- `GET /documents` — list ready documents
- `GET /documents/{document_id}` — get document metadata
- `DELETE /documents/{document_id}` — remove document chunks and metadata (204)
- `POST /questions` — ask a grounded question and receive citations plus every
  fetched chunk, including rank, source, text, and similarity. `/ask` remains
  an undocumented compatibility alias.
- `GET /health` — process health check

Duplicate content returns 409; unsupported types 415; invalid questions 400 or
422 as appropriate; upload overflow 413; rate limits 429; and storage/provider
failures 503.

## Tests and evaluation

```bash
pytest -q
python eval/run_evaluation.py
```

The offline evaluation validates evidence quotes against the checked-in PDFs,
compares two token-chunking configurations, measures Hit@5/Page Recall@5/MRR,
checks local extractive answer key-term coverage and citations, and sweeps a
similarity threshold. It makes no external API calls and writes `EVAL.md`,
`eval/results/latest.json`, and `eval/results/latest.csv`.

Key-term coverage is not answer correctness or faithfulness. The labels and
reference answers have not been independently hand-graded, and the evaluation
does not yet include a validated LLM judge, judge-versus-human agreement, or
human-scored faithfulness/correctness. See [EVAL.md](./EVAL.md) for measured
results and limitations.

The Jupyter pipeline notebook in `notebooks/pipeline.ipynb` uses the actual
service pipeline with the checked-in PDF corpus and a temporary local store.
It does not replace the missing user-provided DOCX corpus or independent
review.

## Submission evidence still required

- Hand-review the evaluation questions, references, and source labels; add a
  real DOCX corpus document and verify its evidence.
- Hand-grade at least ten answers if an LLM-judge comparison is added.
- Capture genuine Swagger and frontend screenshots; no screenshots are claimed
  in this repository yet.
- Record the required demo video and demonstrate the rubric checklist.
- Add the actual full AI chat-history export yourself; see `AI_USAGE.md` for
  the documented tools and known prompts.

Do not treat this repository as submission-ready until these evidence-dependent
items are complete and reviewed.
