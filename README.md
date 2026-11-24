# portfolio-01-production-rag-service
A code-based Production RAG Service built with Python, FastAPI, configurable embeddings, Pinecone, and Neon.

## Corpus

The service is configured for the two official NIST PDFs in `corpus/`:

- NIST AI RMF 1.0
- NIST AI 600-1, Generative AI Profile

## Setup

```bash
python -m pip install -r requirements.txt
cp .env.example .env
# Optional: set GEMINI_API_KEY in .env for Gemini generation.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Pinecone and Neon are required for document storage:

- Set `PINECONE_API_KEY`, `PINECONE_INDEX`, `PINECONE_CLOUD`, and `PINECONE_REGION`.
- Set `NEON_DATABASE_URL` to the PostgreSQL connection string.
- The index must use 384 dimensions and cosine metric for the configured E5 model.
- Keep `.env` untracked; never paste credentials into source files or documentation.
- Optional: set `MIN_RETRIEVAL_SCORE` to reject retrieved chunks below a cosine
  similarity score. It is unset by default; calibrate separately for each
  embedding provider before enabling it.

### No-cost provider options

The current integrations can be used without a paid plan for a small portfolio
deployment, subject to each provider's current eligibility, quotas, regions,
and terms:

- **Embeddings:** Keep `EMBEDDING_PROVIDER=local` to run E5 locally without an
  embedding API key or per-request API charges.
- **Answer generation:** Gemini is optional. Google currently offers a free
  tier for selected models, with limited access and rate limits. Free-tier
  prompts may be used to improve Google's products, so do not send confidential
  documents through it. Check the [Gemini API pricing and terms](https://ai.google.dev/gemini-api/docs/pricing)
  before choosing a model.
- **Vector storage:** Pinecone currently lists a free Starter plan. Check its
  [plan and usage limits](https://www.pinecone.io/pricing/) before deployment.
- **Document registry:** Neon currently lists a permanent Free plan with
  resource limits. Check its [current plan details](https://neon.com/pricing).
- **Optional Cohere embeddings:** Cohere trial API calls are free but rate
  limited, and Cohere says trial keys are not permitted for production or
  commercial use. Use a production key only if you accept its pricing; otherwise
  keep the local embedding default. See [Cohere pricing and key terms](https://cohere.com/pricing).

Free plans and quotas can change and are not production service-level
guarantees. Confirm current terms before use; these options avoid a paid
dependency but do not guarantee that every account or workload remains free.

Open `http://127.0.0.1:8000/` for the frontend or `http://127.0.0.1:8000/docs` for Swagger.

Without a Gemini API key, the service runs deterministically in extractive mode. With `GEMINI_API_KEY`, it uses the configured Gemini model.

## Embeddings

The default embedding provider is the local `intfloat/e5-small-v2` model. To use Cohere instead, set:

```bash
EMBEDDING_PROVIDER=cohere
COHERE_API_KEY=your-local-secret
COHERE_EMBEDDING_MODEL=embed-multilingual-light-v3.0
```

The configured Cohere model returns 384-dimensional vectors, matching the existing Pinecone index configuration. Never commit the key.

## API

- `POST /documents` — upload a PDF or DOCX
- `GET /documents` — list ingested documents
- `GET /documents/{document_id}` — get document metadata
- `DELETE /documents/{document_id}` — delete a document and all of its vectors
- `POST /ask` — answer a grounded question and return retrieved chunks
- `GET /health` — health check

## Tests

```bash
pytest -q
```

## Evaluation

```bash
python eval/run_evaluation.py
```

The offline evaluation validates evidence quotes against the NIST PDFs, runs
25 golden questions, compares 800/150 and 500/100 chunking, evaluates the local
extractive answers, and sweeps retrieval thresholds. It does not call Gemini,
Cohere, Pinecone, or Neon. Results and metric limitations are written to
`EVAL.md`; the small gold set is not sufficient to establish production
accuracy or a production threshold.

## Safety

Never commit `.env` or API keys. Upload and question limits, empty-content checks, injection-pattern checks, citation validation, and refusal behavior are enforced in the application guardrails.
