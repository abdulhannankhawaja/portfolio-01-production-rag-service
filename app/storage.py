from pathlib import Path
import psycopg
from psycopg.types.json import Json
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
import httpx


class VectorStore:
    def __init__(
        self,
        data_dir: Path,
        embedding_model: str,
        pinecone_api_key: str | None = None,
        pinecone_index: str = "quickstart",
        pinecone_cloud: str = "aws",
        pinecone_region: str = "us-east-1",
        neon_database_url: str | None = None,
        embedding_provider: str = "local",
        cohere_api_key: str | None = None,
        cohere_embedding_model: str = "embed-multilingual-light-v3.0",
    ):
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is required")
        if not neon_database_url:
            raise ValueError("NEON_DATABASE_URL is required")
        self.data_dir = data_dir
        self.embedding_provider = embedding_provider.lower()
        self.cohere_api_key = cohere_api_key
        self.cohere_embedding_model = cohere_embedding_model
        self.encoder = None if self.embedding_provider == "cohere" else SentenceTransformer(embedding_model)
        if self.embedding_provider == "cohere" and not self.cohere_api_key:
            raise ValueError("COHERE_API_KEY is required when EMBEDDING_PROVIDER=cohere")
        self.db_url = neon_database_url

        pc = Pinecone(api_key=pinecone_api_key)
        if not pc.has_index(pinecone_index):
            pc.create_index(
                name=pinecone_index,
                dimension=384,
                metric="cosine",
                spec=ServerlessSpec(cloud=pinecone_cloud, region=pinecone_region),
            )
        self.index = pc.Index(pinecone_index)
        self.namespace = "documents"
        self._init_registry()
        self._cleanup_pending()

    def _connect(self):
        return psycopg.connect(self.db_url, connect_timeout=10)

    def _init_registry(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        file_name TEXT NOT NULL,
                        sha256_hash TEXT NOT NULL UNIQUE,
                        stored_path TEXT,
                        file_type TEXT,
                        file_size_bytes BIGINT NOT NULL DEFAULT 0,
                        chunk_count INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        vector_ids JSONB NOT NULL DEFAULT '[]',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    def _cleanup_pending(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT document_id FROM documents WHERE status = 'PENDING'")
                pending = [row[0] for row in cursor.fetchall()]
                for document_id in pending:
                    self.index.delete(
                        filter={"document_id": {"$eq": document_id}},
                        namespace=self.namespace,
                    )
                cursor.execute("DELETE FROM documents WHERE status = 'PENDING'")

    def embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        if self.embedding_provider == "cohere":
            response = httpx.post(
                "https://api.cohere.com/v2/embed",
                headers={
                    "Authorization": f"Bearer {self.cohere_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.cohere_embedding_model,
                    "texts": texts,
                    "input_type": "search_query" if is_query else "search_document",
                    "embedding_types": ["float"],
                },
                timeout=30.0,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Cohere embedding unavailable: HTTP {response.status_code}"
                )
            embeddings = response.json()["embeddings"]["float"]
            if embeddings and len(embeddings[0]) != 384:
                raise RuntimeError(
                    "Cohere embeddings must be 384-dimensional for the configured Pinecone index"
                )
            return embeddings
        prefix = "query: " if is_query else "passage: "
        return self.encoder.encode(
            [prefix + text for text in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def has_hash(self, sha256: str) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM documents WHERE sha256_hash = %s LIMIT 1", (sha256,))
                return cursor.fetchone() is not None

    def add_document(
        self,
        document_id: str,
        sha256: str,
        filename: str,
        chunks: list[dict],
        size_bytes: int = 0,
    ) -> None:
        if not chunks:
            raise ValueError("Document has no extractable text")
        try:
            ids = [f"{document_id}:{chunk['chunk_index']}" for chunk in chunks]
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO documents (
                            document_id, file_name, stored_path, sha256_hash, file_type,
                            file_size_bytes, chunk_count, status, vector_ids
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s)
                        """,
                        (
                            document_id,
                            filename,
                            "",
                            sha256,
                            Path(filename).suffix.lower().lstrip("."),
                            size_bytes,
                            len(chunks),
                            Json(ids),
                        ),
                    )

            embeddings = self.embed([chunk["text"] for chunk in chunks])
            vectors = []
            for chunk_id, embedding, chunk in zip(ids, embeddings, chunks):
                vectors.append({
                    "id": chunk_id,
                    "values": embedding,
                    "metadata": {
                        "document_id": document_id,
                        "filename": filename,
                        "sha256": sha256,
                        "page": chunk["page"],
                        "section": chunk.get("section"),
                        "chunk_index": chunk["chunk_index"],
                        "status": "PENDING",
                        "text": chunk["text"],
                    },
                })
            self.index.upsert(vectors=vectors, namespace=self.namespace)

            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE documents SET status = 'READY', updated_at = NOW() "
                        "WHERE document_id = %s",
                        (document_id,),
                    )
            for vector in vectors:
                vector["metadata"]["status"] = "READY"
            self.index.upsert(vectors=vectors, namespace=self.namespace)
        except Exception:
            self.index.delete(
                filter={"document_id": {"$eq": document_id}},
                namespace=self.namespace,
            )
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM documents WHERE document_id = %s", (document_id,))
            raise

    def list_document_ids(self) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT document_id FROM documents WHERE status = 'READY' ORDER BY created_at"
                )
                return [row[0] for row in cursor.fetchall()]

    def get_document(self, document_id: str) -> dict:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT file_name, sha256_hash, chunk_count, file_size_bytes FROM documents "
                    "WHERE document_id = %s AND status = 'READY'",
                    (document_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return {}
                return {
                    "document_id": document_id,
                    "filename": row[0],
                    "sha256": row[1],
                    "chunk_count": row[2],
                    "size_bytes": row[3],
                }

    def delete_document(self, document_id: str) -> bool:
        if not self.get_document(document_id):
            return False
        self.index.delete(
            filter={"document_id": {"$eq": document_id}},
            namespace=self.namespace,
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM documents WHERE document_id = %s", (document_id,))
        return True

    def query(self, question: str, top_k: int) -> list[dict]:
        result = self.index.query(
            vector=self.embed([question], is_query=True)[0],
            top_k=top_k,
            filter={"status": {"$eq": "READY"}},
            include_metadata=True,
            namespace=self.namespace,
        )
        chunks = []
        for match in result.matches:
            metadata = match.metadata or {}
            chunks.append({
                "text": metadata.get("text", ""),
                "document_id": metadata["document_id"],
                "filename": metadata["filename"],
                "page": metadata["page"],
                "section": metadata.get("section"),
                "chunk_index": metadata["chunk_index"],
                "score": float(match.score),
            })
        return chunks
