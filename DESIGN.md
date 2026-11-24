# Design

## Architecture

The application separates API routes, schemas, ingestion, vector storage, generation, and guardrails. FastAPI provides HTTP and OpenAPI; PyMuPDF and python-docx extract source text; `intfloat/e5-small-v2` creates normalized 384-dimensional vectors by default; and Pinecone stores cosine-searchable chunks while Neon/PostgreSQL maintains the document registry.

## Chunking

The default strategy uses 500-character chunks with 100-character overlap. The offline evaluation compares this setting with 800/150; 500/100 currently performs better on the verified source-page retrieval measures. PDF chunk metadata includes the document ID, filename, SHA-256 hash, page number, and chunk position. DOCX content is section-aware through paragraph heading names and stores the active heading as chunk metadata.

## Retrieval

Queries use the embedding model's `query:` prefix and passages use `passage:`. Cosine similarity is used because both stored and query vectors are normalized. The default answer retrieves five chunks.

## Grounding

The prompt requires claims to be cited from retrieved chunks and requires an explicit refusal when context is insufficient. The implementation also refuses prompt-injection patterns and returns HTTP errors for invalid requests. Gemini is optional; an extractive local fallback keeps the service usable without credentials.

## Testing

Tests cover the health route, frontend, blocked input, unsupported uploads, and Pydantic request validation. The project will extend tests to upload, duplicate detection, retrieval, deletion, and refusal behavior.
