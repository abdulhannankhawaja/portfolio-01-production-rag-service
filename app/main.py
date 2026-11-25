import logging
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.generation import Generator
from app.schemas import DocumentOut, QuestionRequest, QuestionResponse
from app.services import RAGService, ServiceError
from app.storage import VectorStore


logger = logging.getLogger("rag.request")
logger.setLevel(logging.INFO)
app = FastAPI(
    title=settings.app_name,
    description=(
        "Upload PDF/DOCX documents, retrieve ranked passages, and ask questions "
        "with citations limited to chunks returned for that request."
    ),
    version="1.0.0",
)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
store = VectorStore(
    settings.data_dir,
    settings.embedding_model,
    embedding_provider=settings.embedding_provider,
    cohere_api_key=settings.cohere_api_key,
    cohere_embedding_model=settings.cohere_embedding_model,
    embedding_timeout=settings.embedding_timeout_seconds,
    max_retries=settings.provider_max_retries,
)
generator = Generator(
    settings.gemini_api_key,
    settings.gemini_model,
    temperature=settings.llm_temperature,
    timeout_seconds=settings.llm_timeout_seconds,
    max_retries=settings.provider_max_retries,
)


class RequestRateLimiter:
    def __init__(self, limit: int, period_seconds: float = 60.0):
        self.limit = limit
        self.period_seconds = period_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def allow(self, client_id: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self.lock:
            timestamps = self.requests[client_id]
            while timestamps and current - timestamps[0] >= self.period_seconds:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                return False
            timestamps.append(current)
            return True


rate_limiter = RequestRateLimiter(settings.max_requests_per_minute)
RATE_LIMITED_PATHS = {"/ask", "/questions", "/documents"}


def service() -> RAGService:
    return RAGService(store, generator, settings)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()
    status_code = 500
    try:
        if (
            request.url.path in RATE_LIMITED_PATHS
            or request.url.path.startswith("/documents/")
        ):
            client_id = request.client.host if request.client else "unknown"
            if not rate_limiter.allow(client_id):
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Request rate limit exceeded"},
                )
                response.headers["X-Request-ID"] = request_id
                status_code = response.status_code
                return response
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception(
            "request failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise
    finally:
        log = logger.info if status_code < 400 else logger.warning
        log(
            "request complete request_id=%s method=%s path=%s status=%s latency_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            status_code,
            (time.perf_counter() - started_at) * 1000,
        )


def _http_error(error: ServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(static_dir / "index.html")


@app.get(
    "/health",
    summary="Check service availability",
    description="Confirms that the API process is responsive.",
    response_description="Service status",
)
def health():
    return {"status": "ok"}


@app.post(
    "/documents",
    response_model=DocumentOut,
    status_code=201,
    summary="Upload and index a document",
    description="Accepts PDF or DOCX files; duplicate SHA-256 content returns 409.",
    responses={
        400: {"description": "Empty, corrupt, encrypted, or unextractable file"},
        409: {"description": "Duplicate document"},
        413: {"description": "File exceeds configured upload size"},
        415: {"description": "Unsupported file type"},
        429: {"description": "Embedding provider rate limit"},
        503: {"description": "Ingestion or storage service unavailable"},
    },
)
async def upload_document(file: UploadFile = File(...)):
    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        content = await file.read(max_bytes + 1)
    finally:
        await file.close()
    try:
        return await run_in_threadpool(
            service().upload_document,
            file.filename or "unnamed",
            content,
        )
    except ServiceError as exc:
        raise _http_error(exc) from exc
@app.get(
    "/documents",
    response_model=list[DocumentOut],
    summary="List indexed documents",
)
async def list_documents():
    try:
        return await run_in_threadpool(service().list_documents)
    except ServiceError as exc:
        raise _http_error(exc) from exc


@app.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    summary="Get document metadata",
    responses={404: {"description": "Document does not exist"}},
)
async def get_document(document_id: str):
    try:
        return await run_in_threadpool(service().get_document, document_id)
    except ServiceError as exc:
        raise _http_error(exc) from exc


@app.delete(
    "/documents/{document_id}",
    status_code=204,
    summary="Delete a document and its vectors",
    responses={
        404: {"description": "Document does not exist"},
        503: {"description": "Vector deletion could not be verified"},
    },
)
async def delete_document(document_id: str):
    try:
        await run_in_threadpool(service().delete_document, document_id)
    except ServiceError as exc:
        raise _http_error(exc) from exc


@app.post(
    "/questions",
    response_model=QuestionResponse,
    summary="Ask a grounded question",
    description=(
        "Returns an answer, citations validated against this request's retrieval "
        "results, and all retrieved chunks including rank and cosine similarity."
    ),
    responses={
        400: {"description": "Question blocked by input guardrail"},
        429: {"description": "Request or upstream provider rate limit"},
        503: {"description": "Retrieval or answer provider unavailable"},
    },
)
@app.post(
    "/ask",
    response_model=QuestionResponse,
    include_in_schema=False,
)
async def ask(request: QuestionRequest):
    try:
        return await run_in_threadpool(
            service().ask,
            request.question,
            request.top_k,
        )
    except ServiceError as exc:
        raise _http_error(exc) from exc
