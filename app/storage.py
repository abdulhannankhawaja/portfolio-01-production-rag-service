import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import chromadb
import httpx


class DuplicateDocumentError(ValueError):
    pass


class EmbeddingRateLimitError(RuntimeError):
    pass


class EmbeddingUnavailableError(RuntimeError):
    pass


class VectorStore:
    def __init__(
        self,
        data_dir: Path,
        embedding_model: str,
        embedding_provider: str = "local",
        cohere_api_key: str | None = None,
        cohere_embedding_model: str = "embed-multilingual-light-v3.0",
        embedding_timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.data_dir / "documents.sqlite3"
        self.embedding_provider = embedding_provider.lower()
        self.cohere_api_key = cohere_api_key
        self.cohere_embedding_model = cohere_embedding_model
        self.embedding_timeout = embedding_timeout
        self.max_retries = max_retries

        if self.embedding_provider not in {"local", "cohere"}:
            raise ValueError("EMBEDDING_PROVIDER must be 'local' or 'cohere'")
        if self.embedding_provider == "cohere" and not cohere_api_key:
            raise ValueError("COHERE_API_KEY is required when EMBEDDING_PROVIDER=cohere")

        self.embedding_model = embedding_model
        self.encoder = None
        self.tokenizer = None
        self.client = chromadb.PersistentClient(path=str(self.data_dir / "chroma"))
        self.collection = self.client.get_or_create_collection(
            name="rag_documents",
            metadata={"hnsw:space": "cosine"},
        )
        self._init_registry()
        self._cleanup_pending()

    def get_tokenizer(self):
        if self.tokenizer is None:
            from transformers import AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(self.embedding_model)
        return self.tokenizer

    def _get_encoder(self):
        if self.encoder is None:
            from sentence_transformers import SentenceTransformer

            self.encoder = SentenceTransformer(self.embedding_model)
            self.tokenizer = self.encoder.tokenizer
        return self.encoder

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_registry(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    file_name TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('PENDING', 'READY')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(owner_id, sha256_hash)
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(documents)")
            }
            if "owner_id" not in columns:
                connection.execute("ALTER TABLE documents RENAME TO documents_legacy")
                connection.execute(
                    """
                    CREATE TABLE documents (
                        document_id TEXT PRIMARY KEY,
                        owner_id TEXT,
                        file_name TEXT NOT NULL,
                        sha256_hash TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        file_size_bytes INTEGER NOT NULL,
                        chunk_count INTEGER NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('PENDING', 'READY')),
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(owner_id, sha256_hash)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO documents (
                        document_id, owner_id, file_name, sha256_hash, file_type,
                        file_size_bytes, chunk_count, status, created_at
                    )
                    SELECT document_id, NULL, file_name, sha256_hash, file_type,
                           file_size_bytes, chunk_count, status, created_at
                    FROM documents_legacy
                    """
                )
                connection.execute("DROP TABLE documents_legacy")

    def _delete_vectors(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})
        remaining = self.collection.get(
            where={"document_id": document_id},
            include=["metadatas"],
        )["ids"]
        if remaining:
            raise RuntimeError("Vector cleanup did not remove every document chunk")

    def _cleanup_pending(self) -> None:
        with self._connect() as connection:
            pending_ids = [
                row["document_id"]
                for row in connection.execute(
                    "SELECT document_id FROM documents WHERE status = 'PENDING'"
                )
            ]
        for document_id in pending_ids:
            self._delete_vectors(document_id)
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM documents WHERE document_id = ? AND status = 'PENDING'",
                    (document_id,),
                )

    def _cohere_embed(self, texts: list[str], is_query: bool) -> list[list[float]]:
        body = {
            "model": self.cohere_embedding_model,
            "texts": texts,
            "input_type": "search_query" if is_query else "search_document",
            "embedding_types": ["float"],
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    "https://api.cohere.com/v2/embed",
                    headers={
                        "Authorization": f"Bearer {self.cohere_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=self.embedding_timeout,
                )
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise EmbeddingUnavailableError("Embedding provider timed out") from exc
            except httpx.HTTPError as exc:
                raise EmbeddingUnavailableError("Embedding provider request failed") from exc

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.max_retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code == 429:
                    raise EmbeddingRateLimitError("Embedding provider rate limit exceeded")
                raise EmbeddingUnavailableError("Embedding provider is unavailable")
            if response.status_code >= 400:
                raise EmbeddingUnavailableError(
                    f"Embedding provider rejected the request (HTTP {response.status_code})"
                )
            try:
                embeddings = response.json()["embeddings"]["float"]
            except (KeyError, TypeError, ValueError) as exc:
                raise EmbeddingUnavailableError(
                    "Embedding provider returned an invalid response"
                ) from exc
            return embeddings

        raise EmbeddingUnavailableError("Embedding provider is unavailable")

    def embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        if self.embedding_provider == "cohere":
            embeddings = self._cohere_embed(texts, is_query)
        else:
            prefix = "query: " if is_query else "passage: "
            embeddings = self._get_encoder().encode(
                [prefix + text for text in texts],
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=64,
            ).tolist()

        if len(embeddings) != len(texts) or any(
            len(embedding) != 384 for embedding in embeddings
        ):
            raise EmbeddingUnavailableError(
                "Embedding provider must return one 384-dimensional vector per input"
            )
        return embeddings

    def has_hash(self, sha256: str, owner_id: str) -> bool:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT 1 FROM documents
                WHERE sha256_hash = ? AND owner_id = ? LIMIT 1
                """,
                (sha256, owner_id),
            ).fetchone() is not None

    def add_document(
        self,
        document_id: str,
        owner_id: str,
        sha256: str,
        filename: str,
        chunks: list[dict],
        size_bytes: int = 0,
    ) -> None:
        if not chunks:
            raise ValueError("Document has no extractable text")
        if self.has_hash(sha256, owner_id):
            raise DuplicateDocumentError("This document has already been uploaded")

        embeddings = self.embed([chunk["text"] for chunk in chunks])
        chunk_ids = [f"{document_id}:{chunk['chunk_index']}" for chunk in chunks]
        metadatas = []
        for chunk_id, chunk in zip(chunk_ids, chunks):
            metadata = {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "owner_id": owner_id,
                "file_name": filename,
                "sha256": sha256,
                "chunk_position": int(chunk["chunk_index"]),
                "status": "PENDING",
            }
            if chunk.get("page") is not None:
                metadata["page"] = int(chunk["page"])
            if chunk.get("section"):
                metadata["section"] = str(chunk["section"])
            metadatas.append(metadata)

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO documents (
                        document_id, owner_id, file_name, sha256_hash, file_type,
                        file_size_bytes, chunk_count, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        document_id,
                        owner_id,
                        filename,
                        sha256,
                        Path(filename).suffix.lower().lstrip("."),
                        size_bytes,
                        len(chunks),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateDocumentError("This document has already been uploaded") from exc

        try:
            self.collection.upsert(
                ids=chunk_ids,
                embeddings=embeddings,
                documents=[chunk["text"] for chunk in chunks],
                metadatas=metadatas,
            )
            ready_metadatas = [metadata | {"status": "READY"} for metadata in metadatas]
            self.collection.update(ids=chunk_ids, metadatas=ready_metadatas)
            stored = self.collection.get(ids=chunk_ids, include=["metadatas"])
            if len(stored["ids"]) != len(chunk_ids) or any(
                metadata.get("status") != "READY"
                for metadata in stored["metadatas"]
            ):
                raise RuntimeError("Not all document chunks reached READY status")
            with self._connect() as connection:
                connection.execute(
                    "UPDATE documents SET status = 'READY' WHERE document_id = ?",
                    (document_id,),
                )
        except Exception as exc:
            try:
                self._delete_vectors(document_id)
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM documents WHERE document_id = ?",
                        (document_id,),
                    )
            except Exception as cleanup_error:
                raise RuntimeError(
                    "Document ingestion failed and cleanup was incomplete"
                ) from cleanup_error
            raise

    def list_document_ids(self, owner_id: str) -> list[str]:
        with self._connect() as connection:
            return [
                row["document_id"]
                for row in connection.execute(
                    "SELECT document_id FROM documents "
                    "WHERE status = 'READY' AND owner_id = ? "
                    "ORDER BY created_at, document_id",
                    (owner_id,),
                )
            ]

    def get_document(self, document_id: str, owner_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT file_name, sha256_hash, chunk_count, file_size_bytes
                FROM documents
                WHERE document_id = ? AND owner_id = ? AND status = 'READY'
                """,
                (document_id, owner_id),
            ).fetchone()
        if row is None:
            return {}
        return {
            "document_id": document_id,
            "owner_id": owner_id,
            "filename": row["file_name"],
            "sha256": row["sha256_hash"],
            "chunk_count": row["chunk_count"],
            "size_bytes": row["file_size_bytes"],
        }

    def delete_document(self, document_id: str, owner_id: str) -> bool:
        if not self.get_document(document_id, owner_id):
            return False
        self._delete_vectors(document_id)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM documents WHERE document_id = ?",
                (document_id,),
            )
        return True

    def query(self, question: str, top_k: int, owner_id: str) -> list[dict]:
        embedding = self.embed([question], is_query=True)[0]
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where={
                "$and": [
                    {"status": "READY"},
                    {"owner_id": owner_id},
                ]
            },
            include=["documents", "metadatas", "distances"],
        )
        document_ids = {
            metadata["document_id"]
            for metadata in result["metadatas"][0]
        }
        if not document_ids:
            return []
        placeholders = ",".join("?" for _ in document_ids)
        with self._connect() as connection:
            ready_ids = {
                row["document_id"]
                for row in connection.execute(
                    f"SELECT document_id FROM documents "
                    f"WHERE status = 'READY' AND owner_id = ? "
                    f"AND document_id IN ({placeholders})",
                    (owner_id, *document_ids),
                )
            }
        chunks = []
        for chunk_id, text, metadata, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            if metadata["document_id"] not in ready_ids:
                continue
            similarity = 1.0 - float(distance)
            if not -1.0 <= similarity <= 1.0:
                raise RuntimeError("Chroma returned an invalid cosine similarity")
            chunks.append({
                "chunk_id": metadata["chunk_id"],
                "text": text,
                "document_id": metadata["document_id"],
                "filename": metadata["file_name"],
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "chunk_index": metadata["chunk_position"],
                "score": similarity,
            })
        return chunks
