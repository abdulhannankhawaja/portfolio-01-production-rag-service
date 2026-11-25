import uuid
from contextlib import nullcontext
from pathlib import Path

from app.config import Settings
from app.generation import (
    SYSTEM_PROMPT,
    Generator,
    GenerationRateLimitError,
    GenerationResult,
    REFUSAL_TEXT,
)
from app.guardrails import contains_sensitive_output, is_grounded, validate_question
from app.ingestion import extract_text, sha256_bytes, split_text
from app.observability import Observability
from app.schemas import Citation, DocumentOut, QuestionResponse
from app.storage import (
    DuplicateDocumentError,
    EmbeddingRateLimitError,
    VectorStore,
)


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _document_response(document_id: str, item: dict) -> DocumentOut:
    filename = item["filename"]
    return DocumentOut(
        id=document_id,
        filename=filename,
        file_type=Path(filename).suffix.lower(),
        size_bytes=item.get("size_bytes", 0),
        chunk_count=item["chunk_count"],
        sha256=item["sha256"],
    )


class RAGService:
    """Coordinate upload, retrieval, generation, and response validation."""

    def __init__(
        self,
        store: VectorStore,
        generator: Generator,
        settings: Settings,
        telemetry: Observability | None = None,
    ):
        self.store = store
        self.generator = generator
        self.settings = settings
        self.telemetry = telemetry

    def upload_document(
        self,
        owner_id: str,
        filename: str,
        content: bytes,
    ) -> DocumentOut:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt", ".md", ".pptx"}:
            raise ServiceError(
                415,
                "Only PDF, DOCX, TXT, MD, and PPTX files are supported",
            )
        if not content:
            raise ServiceError(400, "Uploaded file is empty")
        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ServiceError(413, f"File exceeds {self.settings.max_upload_mb} MB")

        sha256 = sha256_bytes(content)
        try:
            if self.store.has_hash(sha256, owner_id):
                raise ServiceError(409, "This document has already been uploaded")
            pages = extract_text(content, filename)
            tokenizer = (
                self.store.get_tokenizer()
                if hasattr(self.store, "get_tokenizer")
                else getattr(self.store, "tokenizer", None)
            )
            chunks = split_text(
                pages,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
                tokenizer=tokenizer,
            )
            if not chunks:
                raise ServiceError(400, "Document contains no extractable text")
            document_id = str(uuid.uuid4())
            self.store.add_document(
                document_id,
                owner_id,
                sha256,
                filename,
                chunks,
                len(content),
            )
        except ServiceError:
            raise
        except DuplicateDocumentError as exc:
            raise ServiceError(409, "This document has already been uploaded") from exc
        except EmbeddingRateLimitError as exc:
            raise ServiceError(429, "Embedding provider rate limit exceeded") from exc
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc
        except Exception as exc:
            raise ServiceError(503, "Document ingestion service is unavailable") from exc

        return DocumentOut(
            id=document_id,
            filename=filename,
            file_type=suffix,
            size_bytes=len(content),
            chunk_count=len(chunks),
            sha256=sha256,
        )

    def list_documents(self, owner_id: str) -> list[DocumentOut]:
        try:
            documents = []
            for document_id in self.store.list_document_ids(owner_id):
                item = self.store.get_document(document_id, owner_id)
                if item:
                    documents.append(_document_response(document_id, item))
            return documents
        except Exception as exc:
            raise ServiceError(503, "Document registry is unavailable") from exc

    def get_document(self, document_id: str, owner_id: str) -> DocumentOut:
        try:
            item = self.store.get_document(document_id, owner_id)
        except Exception as exc:
            raise ServiceError(503, "Document registry is unavailable") from exc
        if not item:
            raise ServiceError(404, "Document not found")
        return _document_response(document_id, item)

    def delete_document(self, document_id: str, owner_id: str) -> None:
        try:
            deleted = self.store.delete_document(document_id, owner_id)
        except Exception as exc:
            raise ServiceError(503, "Document deletion is incomplete") from exc
        if not deleted:
            raise ServiceError(404, "Document not found")

    def ask(
        self,
        question: str,
        top_k: int | None,
        owner_id: str,
    ) -> QuestionResponse:
        try:
            question = validate_question(question, self.settings.max_question_chars)
        except ValueError as exc:
            raise ServiceError(400, str(exc)) from exc

        try:
            retrieval_span = (
                self.telemetry.span(
                    "retrieval",
                    {
                        "top_k": top_k or self.settings.top_k,
                        "embedding_provider": self.settings.embedding_provider,
                    },
                )
                if self.telemetry
                else nullcontext()
            )
            with retrieval_span:
                retrieved = self.store.query(
                    question,
                    top_k or self.settings.top_k,
                    owner_id,
                )
        except EmbeddingRateLimitError as exc:
            raise ServiceError(429, "Embedding provider rate limit exceeded") from exc
        except Exception as exc:
            raise ServiceError(503, "Retrieval service is unavailable") from exc

        fetched = [
            {
                **chunk,
                "chunk_id": chunk.get("chunk_id", f"retrieved-{rank}"),
                "rank": rank,
            }
            for rank, chunk in enumerate(retrieved, start=1)
        ]
        if self.telemetry:
            with self.telemetry.span(
                "reranking",
                {"enabled": False, "strategy": "vector_similarity_order"},
            ) as span:
                span.skip("No separate reranker is configured")
            score_filter_span = self.telemetry.span(
                "score_filter",
                {"minimum_score": self.settings.min_retrieval_score},
            )
        else:
            score_filter_span = nullcontext()
        with score_filter_span:
            eligible = [
                chunk for chunk in fetched
                if self.settings.min_retrieval_score is None
                or chunk["score"] >= self.settings.min_retrieval_score
            ]
        if self.telemetry:
            self.telemetry.set_question_metrics(
                input_tokens=None,
                output_tokens=None,
                token_source="unavailable",
                cost_usd=0.0 if not self.generator.api_key else None,
                model="refusal" if not eligible else self.generator.model,
                retrieved_chunks=len(fetched),
            )
        if not eligible:
            if self.telemetry:
                with self.telemetry.span(
                    "llm_call",
                    {"provider": "not_called", "reason": "no_chunks_above_threshold"},
                ) as span:
                    span.skip("No retrieved chunks passed the score threshold")
            return self._response(
                REFUSAL_TEXT,
                [],
                fetched,
                "refusal",
                True,
                False,
            )

        try:
            generation_span = (
                self.telemetry.span(
                    "llm_call" if self.generator.api_key else "extractive_generation",
                    {
                        "provider": "gemini" if self.generator.api_key else "local",
                        "model": self.generator.model,
                        "retrieved_chunks": len(eligible),
                    },
                )
                if self.telemetry
                else nullcontext()
            )
            with generation_span:
                generated: GenerationResult = self.generator.generate(question, eligible)
        except GenerationRateLimitError as exc:
            raise ServiceError(429, "LLM rate limit exceeded") from exc
        except Exception as exc:
            raise ServiceError(503, "Answer generation is unavailable") from exc
        if self.telemetry:
            self.telemetry.set_question_metrics(
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
                token_source=generated.token_source,
                cost_usd=generated.cost_usd,
                model=generated.model,
                retrieved_chunks=len(fetched),
            )

        retrieved_by_id = {chunk["chunk_id"]: chunk for chunk in eligible}
        if any(chunk_id not in retrieved_by_id for chunk_id in generated.cited_chunk_ids):
            raise ServiceError(503, "Answer generation returned invalid citations")
        if not generated.answerable:
            return self._response(
                REFUSAL_TEXT,
                [],
                fetched,
                generated.model,
                True,
                False,
            )

        cited_ids = list(dict.fromkeys(generated.cited_chunk_ids))
        if not cited_ids:
            raise ServiceError(503, "Answer generation returned no citations")
        cited_chunks = [retrieved_by_id[chunk_id] for chunk_id in cited_ids]
        sensitive_values = (
            self.settings.gemini_api_key,
            self.settings.cohere_api_key,
            SYSTEM_PROMPT,
        )
        if contains_sensitive_output(generated.answer, sensitive_values):
            return self._response(
                REFUSAL_TEXT,
                [],
                fetched,
                "refusal",
                True,
                False,
            )

        answer = generated.answer.strip()
        answer += " " + " ".join(
            f"[{index}]"
            for index in range(1, len(cited_chunks) + 1)
        )
        if not is_grounded(answer, cited_chunks):
            return self._response(
                REFUSAL_TEXT,
                [],
                fetched,
                "refusal",
                True,
                False,
            )
        return self._response(
            answer,
            cited_chunks,
            fetched,
            generated.model,
            False,
            True,
        )

    @staticmethod
    def _response(
        answer: str,
        cited_chunks: list[dict],
        retrieved: list[dict],
        model: str,
        refusal: bool,
        grounded: bool,
    ) -> QuestionResponse:
        def citation(chunk: dict, rank: int) -> Citation:
            return Citation(
                chunk_id=chunk["chunk_id"],
                document_id=chunk["document_id"],
                filename=chunk["filename"],
                page=chunk.get("page"),
                section=chunk.get("section"),
                chunk_index=chunk["chunk_index"],
                rank=chunk.get("rank", rank),
                text=chunk["text"],
                score=chunk["score"],
            )

        return QuestionResponse(
            answer=answer,
            citations=[
                citation(chunk, rank)
                for rank, chunk in enumerate(cited_chunks, start=1)
            ],
            retrieved_chunks=[
                citation(chunk, rank)
                for rank, chunk in enumerate(retrieved, start=1)
            ],
            grounded=grounded,
            refusal=refusal,
            model=model,
        )
