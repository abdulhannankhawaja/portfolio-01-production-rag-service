import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.generation import Generator
from app.guardrails import is_grounded, validate_question
from app.ingestion import extract_text, sha256_bytes, split_text
from app.schemas import Citation, DocumentOut, QuestionRequest, QuestionResponse
from app.storage import VectorStore


app = FastAPI(title=settings.app_name)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
store = VectorStore(
    settings.data_dir,
    settings.embedding_model,
    pinecone_api_key=settings.pinecone_api_key,
    pinecone_index=settings.pinecone_index,
    pinecone_cloud=settings.pinecone_cloud,
    pinecone_region=settings.pinecone_region,
    neon_database_url=settings.neon_database_url,
    embedding_provider=settings.embedding_provider,
    cohere_api_key=settings.cohere_api_key,
    cohere_embedding_model=settings.cohere_embedding_model,
)
generator = Generator(settings.gemini_api_key, settings.gemini_model)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or "unnamed"
    if Path(filename).suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(415, "Only PDF and DOCX files are supported")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(400, "Uploaded file is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
    sha256 = sha256_bytes(content)
    if store.has_hash(sha256):
        raise HTTPException(409, "This document has already been uploaded")
    try:
        pages = extract_text(content, filename)
        chunks = split_text(pages, settings.chunk_size, settings.chunk_overlap)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not chunks:
        raise HTTPException(400, "Document contains no extractable text")
    try:
        document_id = str(uuid.uuid4())
        store.add_document(document_id, sha256, filename, chunks, len(content))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Ingestion service unavailable: {exc}") from exc
    return DocumentOut(
        id=document_id,
        filename=filename,
        file_type=Path(filename).suffix.lower(),
        size_bytes=len(content),
        chunk_count=len(chunks),
        sha256=sha256,
    )


@app.get("/documents", response_model=list[DocumentOut])
def list_documents():
    documents = []
    for document_id in store.list_document_ids():
        item = store.get_document(document_id)
        if item:
            documents.append(DocumentOut(
                id=document_id,
                filename=item["filename"],
                file_type=Path(item["filename"]).suffix.lower(),
                size_bytes=item.get("size_bytes", 0),
                chunk_count=item["chunk_count"],
                sha256=item["sha256"],
            ))
    return documents


@app.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str):
    item = store.get_document(document_id)
    if not item:
        raise HTTPException(404, "Document not found")
    return DocumentOut(
        id=document_id,
        filename=item["filename"],
        file_type=Path(item["filename"]).suffix.lower(),
        size_bytes=item.get("size_bytes", 0),
        chunk_count=item["chunk_count"],
        sha256=item["sha256"],
    )


@app.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str):
    if not store.delete_document(document_id):
        raise HTTPException(404, "Document not found")
    return None


@app.post("/ask", response_model=QuestionResponse)
def ask(request: QuestionRequest):
    try:
        question = validate_question(request.question, settings.max_question_chars)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    chunks = store.query(question, request.top_k or settings.top_k)
    if settings.min_retrieval_score is not None:
        chunks = [
            chunk for chunk in chunks
            if chunk["score"] >= settings.min_retrieval_score
        ]
    if not chunks:
        answer = "The documents do not contain enough information to answer this question."
        return QuestionResponse(
            answer=answer, citations=[], retrieved_chunks=[],
            grounded=True, refusal=True, model="refusal",
        )
    try:
        answer, model = generator.generate(question, chunks)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    citations = [
        Citation(
            document_id=chunk["document_id"],
            filename=chunk["filename"],
            page=chunk["page"],
            section=chunk.get("section"),
            chunk_index=chunk["chunk_index"],
            text=chunk["text"],
            score=chunk["score"],
        )
        for chunk in chunks
    ]
    refusal = "do not contain enough information" in answer.lower()
    return QuestionResponse(
        answer=answer,
        citations=citations,
        retrieved_chunks=citations,
        grounded=not refusal and is_grounded(answer, chunks),
        refusal=refusal,
        model=model,
    )
