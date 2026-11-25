# Production RAG Service

A locally runnable retrieval-augmented question-answering (RAG) app. Create an
account, upload documents, and ask questions that are answered from retrieved
passages with source citations. The API and browser UI run locally by default;
Gemini and Cohere are optional integrations.

> **Scope:** This is a portfolio/demo application, not a hardened public
> production deployment. See [Security and limitations](#security-and-limitations)
> and [Evaluation](#evaluation) before using it with sensitive or important data.

## Contents

- [How it works](#how-it-works)
- [Features](#features)
- [Project structure](#project-structure)
- [Run locally](#run-locally)
- [Use the application](#use-the-application)
- [Configuration](#configuration)
- [API](#api)
- [Development and tests](#development-and-tests)
- [Edge-case coverage](#edge-case-coverage)
- [Data and privacy](#data-and-privacy)
- [Security and limitations](#security-and-limitations)
- [Evaluation](#evaluation)
- [Screenshots and documentation](#screenshots-and-documentation)

## How it works

The service follows a retrieval-first workflow:

1. **Upload:** The server checks file size and type, validates/extracts supported
   content, hashes it for duplicate detection, and splits text into overlapping
   token-sized chunks.
2. **Index:** The configured embedding model converts chunks into vectors.
   Chroma stores the vectors and source metadata; SQLite tracks document
   ownership and indexing state.
3. **Retrieve:** A question is checked against input guardrails, embedded, and
   used to find the most similar chunks belonging to the signed-in user.
4. **Answer:** The local extractive answerer is used by default. If Gemini is
   configured, it receives the question and retrieved passages as untrusted
   data and returns a structured answer.
5. **Validate and cite:** The server verifies that every generated citation
   refers to a passage retrieved for that request, applies output checks, then
   returns the answer, citations, and retrieved passages.

The similarity score is a vector-search distance conversion, **not** a
probability or measure of answer correctness.

## Features

### Document ingestion

- Accepts **PDF, DOCX, TXT, Markdown (`.md`), and PPTX**.
- Preserves PDF page and PPTX slide numbers. DOCX headings are retained as
  section metadata and DOCX/PPTX tables are flattened to readable text.
- TXT and Markdown must be UTF-8. Scanned PDFs are not OCR'd.
- Uses token-aware chunks (default: 500 tokens with 100-token overlap) with
  preferred boundaries around paragraphs, lines, sentences, and words.
- Uses SHA-256 to detect duplicate file content for the same account.
- Stores extracted chunks, vectors, and metadata; it does not retain the
  original uploaded file.
- Validates PDF signatures and Office archive structure, integrity, expansion
  limits, and encrypted-file flags. It rejects malformed, encrypted, empty,
  oversized, and unsupported files.

### Retrieval and answers

- Defaults to local `intfloat/e5-small-v2` embeddings and persistent Chroma with
  cosine distance. E5 query/document prefixes are applied in local mode.
- Retrieves up to five passages by default. The optional minimum similarity
  threshold defaults to `0.84`; tune it against a representative, reviewed
  dataset rather than treating it as confidence.
- Uses a deterministic extractive answerer when no Gemini key is configured.
- Gemini output uses a constrained JSON shape. The server validates cited
  chunk IDs and constructs citation source metadata from stored records.
- Returns both answer citations and all retrieved passages, including ranks,
  source locations, text, and similarity scores.
- Refuses unsupported questions rather than intentionally filling gaps with
  outside knowledge.

### Accounts and operations

- Signup/login with Argon2id password hashes and signed, expiring JWTs.
- Document list, retrieval, and deletion are scoped to the authenticated user.
- Request IDs, bounded upload/question sizes, per-process request rate limits,
  provider timeouts/retries, and explicit service errors.
- Optional local observability records request metrics and RAG-stage traces.
  Prompts and document text are not included in telemetry.
- Optional Cohere embeddings and Gemini generation. Both may send document or
  question content to an external provider; review provider terms, privacy,
  quotas, and pricing before enabling them.

## Project structure

```text
app/
  auth.py             Password hashing, user storage, JWT helpers
  config.py           Environment-backed application settings
  generation.py       Local answerer and optional Gemini integration
  guardrails.py       Question checks, grounding, and output-secret checks
  ingestion.py        File validation, text extraction, and chunking
  main.py             FastAPI setup, middleware, and HTTP routes
  observability.py    Local traces, spans, and metrics
  schemas.py          Request and response models
  services.py         Upload, retrieval, generation, and response orchestration
  storage.py          Chroma vectors, embeddings, and SQLite document registry
  static/             Built frontend served by FastAPI (generated output)
frontend/
  src/                React application source and styles
  public/             Static frontend assets
  package.json        Frontend commands and dependencies
corpus/               Checked-in NIST PDF evaluation sources
data/                 Local databases and vector index (ignored by Git)
docs/                 Design, evaluation, and project documentation
eval/                 Offline evaluation inputs, runner, and results
tests/                API, ingestion, generation, storage, and evaluation tests
```

The backend modules keep parsing, storage, business orchestration, generation,
and HTTP concerns separate. Build the React source into `app/static/` before
starting the API; do not edit the generated bundle directly.

## Run locally

### Prerequisites

- Python 3.11 or newer
- Node.js `20.19+` or `22.12+` and npm (to build the browser frontend)
- Internet access the first time the local embedding model/tokenizer is
  downloaded

No Gemini, Cohere, Pinecone, or hosted database account is needed for local
mode.

The current saved test run was performed with **Python 3.14.2**. Python 3.11+
is the documented target, but this repository does not yet include a CI
version matrix proving every supported Python release. `requirements.txt` does
not include `uvloop`; Windows installation is documented but has not been
validated on a Windows machine, and native ML/vector dependencies may have
platform-specific wheel requirements.

### 1. Create and activate a Python environment

From the repository root:

```bash
python -m venv .venv
```

Activate it:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 2. Install backend dependencies and configure the app

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create your local settings file:

```bash
# macOS/Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Open `.env` and set a stable, private `JWT_SECRET_KEY` before creating accounts.
Generate a random value with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the printed value into `.env` as `JWT_SECRET_KEY=...`. Keep `.env`
private; it is excluded from Git. If the key is left unset, the app generates a
temporary key at startup and login tokens expire when the process restarts.

### 3. Build the browser frontend

```bash
cd frontend
npm ci
npm run build
cd ..
```

This writes the production frontend into `app/static/`, where FastAPI serves
it. Rebuild after changing files under `frontend/src/` or `frontend/public/`.

### 4. Start the API and open the app

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Visit:

- Browser app: <http://127.0.0.1:8000/>
- Interactive API docs: <http://127.0.0.1:8000/docs>
- Liveness check: <http://127.0.0.1:8000/health>

Stop the server with `Ctrl+C`. The first local embedding operation may take
longer while the model is downloaded and initialized.

## Use the application

1. Open the browser app and choose **Create account**. Use a password of at
   least 12 characters.
2. Sign in, then choose a PDF, DOCX, TXT, MD, or PPTX file and select
   **Index document**. The file is parsed and indexed; the original upload is
   not retained.
3. Ask a question in the chat. The response displays its answer, citations, and
   expandable retrieved passages. Use the source page/slide or DOCX section to
   inspect the evidence yourself.
4. Delete a document from the document list when it is no longer needed.
5. Open **Observability** to view request metrics and recent processing traces.

Each account sees and searches only its own indexed documents. The browser
keeps the access token in session storage for the current tab.

## Configuration

Settings are read from `.env`; defaults are defined in
[app/config.py](./app/config.py) and the copyable template is
[.env.example](./.env.example).

| Setting | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `data` | Local SQLite databases and Chroma data |
| `EMBEDDING_PROVIDER` | `local` | `local` E5 model or optional `cohere` |
| `EMBEDDING_MODEL` | `intfloat/e5-small-v2` | Local sentence-transformer model |
| `COHERE_API_KEY` | unset | Required only for Cohere embeddings |
| `COHERE_EMBEDDING_MODEL` | `embed-multilingual-light-v3.0` | Cohere embedding model |
| `GEMINI_API_KEY` | unset | Enables Gemini; otherwise local extraction is used |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini generation model |
| `JWT_SECRET_KEY` | random per process | Stable private secret for login tokens |
| `JWT_ACCESS_TOKEN_MINUTES` | `60` | JWT lifetime; maximum is 24 hours |
| `MAX_UPLOAD_MB` | `25` | Maximum upload size |
| `MAX_QUESTION_CHARS` | `2000` | Maximum question length |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `100` | Chunking window and overlap in tokens |
| `TOP_K` | `5` | Default number of retrieved passages |
| `MIN_RETRIEVAL_SCORE` | `0.84` | Optional similarity gate; not confidence |
| `MAX_REQUESTS_PER_MINUTE` | `60` | Per-process/IP request rate limit |
| `LLM_TIMEOUT_SECONDS` | `30` | Gemini request timeout |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Cohere request timeout |
| `PROVIDER_MAX_RETRIES` | `2` | Bounded retry count for transient provider errors |
| `LLM_TEMPERATURE` | `0.0` | Gemini generation temperature |
| `GEMINI_INPUT_COST_PER_MILLION` / `GEMINI_OUTPUT_COST_PER_MILLION` | unset | Optional current rates for estimated Gemini cost reporting |

The similarity threshold is a small-corpus diagnostic default, not a
calibrated confidence value. Provider prices and model availability change;
check current provider information before enabling paid services.

## API

All document, question, and observability endpoints require a bearer token.
Signup, login, and `/health` are public. Full schemas and interactive examples
are available at `/docs`.

| Method and route | Purpose |
|---|---|
| `POST /auth/signup` | Create an account |
| `POST /auth/login` | Authenticate and receive an access token |
| `POST /documents` | Upload and index a supported document |
| `GET /documents` | List the signed-in user's documents |
| `GET /documents/{document_id}` | Get owned document metadata |
| `DELETE /documents/{document_id}` | Delete an owned document and vectors |
| `POST /questions` | Retrieve passages and return a grounded answer |
| `GET /observability` | Get local metrics and recent request traces |
| `GET /health` | Check whether the API process responds |

Example request sequence (replace the values with your own):

```bash
# Create an account once
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"reader","password":"replace-with-a-long-password"}'

# Sign in and copy access_token from the JSON response
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"reader","password":"replace-with-a-long-password"}'

# Upload a document; replace YOUR_TOKEN with the returned access_token
curl -X POST http://127.0.0.1:8000/documents \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@./guide.pdf"

# Ask a question
curl -X POST http://127.0.0.1:8000/questions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"What does the document say about risk management?","top_k":5}'
```

Common responses include `400` for invalid or unextractable content, `401` for
missing/invalid authentication, `409` for duplicate content, `413` for an
oversized upload, `415` for an unsupported extension, `429` for rate limits,
and `503` for unavailable storage or providers.

## Development and tests

Run backend tests from the repository root:

```bash
pytest -q
```

Run the frontend linter and production build:

```bash
cd frontend
npm run lint
npm run build
```

Run the offline retrieval evaluation:

```bash
cd ..
python eval/run_evaluation.py
```

The evaluation uses the checked-in NIST PDFs and makes no external API calls.
It writes `docs/EVAL.md` and `eval/results/latest.json` /
`eval/results/latest.csv`.

## Data and privacy

The service stores its local data under `DATA_DIR` (default: `data/`):

- `chroma/` contains vectors and indexed passage text.
- `documents.sqlite3` contains document metadata and ownership.
- `users.sqlite3` contains usernames and password hashes.
- `observability.sqlite3` contains request metrics and spans, not prompts or
  document text.

Original uploaded files are not retained, but extracted text remains in the
local vector database until the document is deleted. Protect and back up the
data directory according to the sensitivity of your documents. Deleting a
document through the app removes its vectors and registry entry.

## Edge-case coverage

The project tests empty/scanned and malformed files, duplicate uploads, upload
and document-text limits, empty-corpus and unanswerable questions, post-delete
search, contradictory passages, tables/Unicode text, provider timeout/rate
limits, and concurrent storage requests. The exact behavior, test names, known
limits, and a suggested demo-video sequence are listed in
[docs/EDGE_CASES.md](./docs/EDGE_CASES.md). There is no demo video in this
repository yet; the checklist is a guide for recording one, not evidence that
the cases have been demonstrated.

## Security and limitations

- Uploaded document text is treated as untrusted data; the model prompt says
  not to follow instructions in retrieved passages. The application does not
  execute document instructions. Prompt wording and pattern checks cannot
  guarantee that a model will never be influenced by prompt injection.
- File validation rejects malformed/encrypted or structurally invalid supported
  files and enforces size/expansion limits. **There is no antivirus or general
  malware scanner.** Do not treat validation as proof that an upload is safe.
- Do not upload confidential documents to Gemini or Cohere unless their data
  handling is approved for your use case.
- Citations are restricted to passages retrieved for the current request, but
  this does not prove that every answer claim is correct or fully supported.
  Verify important answers against the cited source.
- Scanned PDFs have no OCR support. Complex PDF layouts, headers, footers, and
  flattened Office tables may not extract perfectly.
- SQLite and Chroma are local, single-instance storage. The in-memory rate
  limiter is per process and is not suitable as a distributed abuse-control
  mechanism.
- Set a stable `JWT_SECRET_KEY` before use. If left unset, tokens become invalid
  after restart. Legacy documents without an owner are not exposed to accounts
  and may need to be uploaded again.

## Evaluation

The checked-in evaluation set uses two official NIST PDFs and a small set of
script-validated questions and evidence labels. It reports retrieval metrics
such as Hit@5, Page Recall@5, and MRR@5, plus answer/refusal proxies. It does
not establish semantic answer accuracy, faithfulness, or production quality;
labels have not been independently hand-reviewed and human answer grades are
not available. Read the limitations and current measurements in
[docs/EVAL.md](./docs/EVAL.md) and [docs/ACCURACY_REPORT.md](./docs/ACCURACY_REPORT.md).
The repository does not include a user-provided real DOCX evaluation document;
DOCX and the other non-PDF formats are covered by generated test fixtures.

## Screenshots and documentation

See the [screenshot gallery](./docs/screenshots/README.md) for the supplied
login, account creation, workspace, answer, API, and observability captures.
The images are visual references; confirm a capture matches the current build
before presenting it as proof of a feature.

Other project notes are indexed in [docs/README.md](./docs/README.md), including
[design decisions](./docs/DESIGN.md), the detailed
[AI usage and prompt record](./docs/AI_USAGE.md), and
[evaluation results](./docs/EVAL.md).
