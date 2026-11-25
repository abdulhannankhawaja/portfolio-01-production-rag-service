import httpx
import pytest

from app.storage import (
    DuplicateDocumentError,
    EmbeddingRateLimitError,
    EmbeddingUnavailableError,
    VectorStore,
)


def make_store(tmp_path):
    store = VectorStore(
        tmp_path,
        "unused-test-model",
        embedding_provider="cohere",
        cohere_api_key="test-key",
    )
    query_vector = [1.0, 0.0] + [0.0] * 382
    document_vector = [0.8, 0.6] + [0.0] * 382

    def embed(texts, is_query=False):
        vector = query_vector if is_query else document_vector
        return [vector[:] for _ in texts]

    store.embed = embed
    return store


def test_chroma_uses_cosine_similarity_and_deletes_all_document_vectors(tmp_path):
    store = make_store(tmp_path)
    chunks = [{
        "text": "The source describes AI risk governance.",
        "page": 7,
        "section": None,
        "chunk_index": 0,
    }]
    store.add_document("doc-1", "hash-1", "guide.pdf", chunks, 100)

    result = store.query("What does the source describe?", 5)

    assert len(result) == 1
    assert result[0]["chunk_id"] == "doc-1:0"
    assert result[0]["filename"] == "guide.pdf"
    assert result[0]["page"] == 7
    assert result[0]["score"] == pytest.approx(0.8, abs=1e-5)
    assert store.collection.metadata["hnsw:space"] == "cosine"

    store.delete_document("doc-1")

    assert store.query("What does the source describe?", 5) == []
    assert store.get_document("doc-1") == {}


def test_document_chunks_have_full_metadata_and_duplicate_hash_is_rejected(tmp_path):
    store = make_store(tmp_path)
    store.add_document(
        "doc-1",
        "same-hash",
        "guide.docx",
        [{"text": "A heading and paragraph.", "page": None, "section": "Risks", "chunk_index": 3}],
        100,
    )

    saved = store.collection.get(ids=["doc-1:3"], include=["metadatas"])
    metadata = saved["metadatas"][0]
    assert metadata["chunk_id"] == "doc-1:3"
    assert metadata["document_id"] == "doc-1"
    assert metadata["file_name"] == "guide.docx"
    assert metadata["section"] == "Risks"
    assert metadata["chunk_position"] == 3
    assert "page" not in metadata

    with pytest.raises(DuplicateDocumentError):
        store.add_document(
            "doc-2",
            "same-hash",
            "other.docx",
            [{"text": "Duplicate content.", "page": None, "section": "", "chunk_index": 0}],
            100,
        )


def test_startup_cleanup_removes_pending_database_record_and_vectors(tmp_path):
    store = make_store(tmp_path)
    with store._connect() as connection:
        connection.execute(
            """
            INSERT INTO documents (
                document_id, file_name, sha256_hash, file_type,
                file_size_bytes, chunk_count, status
            ) VALUES ('pending-doc', 'pending.pdf', 'pending-hash', 'pdf', 10, 1, 'PENDING')
            """
        )
    store.collection.upsert(
        ids=["pending-doc:0"],
        embeddings=[[1.0, 0.0] + [0.0] * 382],
        documents=["unfinished chunk"],
        metadatas=[{
            "chunk_id": "pending-doc:0",
            "document_id": "pending-doc",
            "file_name": "pending.pdf",
            "sha256": "pending-hash",
            "chunk_position": 0,
            "status": "PENDING",
        }],
    )

    store._cleanup_pending()

    assert store.collection.get(ids=["pending-doc:0"], include=["metadatas"])["ids"] == []
    assert store.get_document("pending-doc") == {}


def test_failed_vector_write_removes_pending_registry_and_partial_vectors(
    tmp_path,
    monkeypatch,
):
    store = make_store(tmp_path)

    def fail_update(**kwargs):
        raise RuntimeError("simulated vector update failure")

    monkeypatch.setattr(store.collection, "update", fail_update)

    with pytest.raises(RuntimeError, match="simulated vector update failure"):
        store.add_document(
            "doc-fail",
            "hash-fail",
            "guide.pdf",
            [{"text": "Partial write test.", "page": 1, "section": None, "chunk_index": 0}],
            20,
        )

    assert store.collection.get(
        where={"document_id": "doc-fail"},
        include=["metadatas"],
    )["ids"] == []
    assert store.get_document("doc-fail") == {}


def test_cohere_retries_transient_rate_limits_with_a_bounded_count(monkeypatch):
    store = VectorStore.__new__(VectorStore)
    store.embedding_provider = "cohere"
    store.cohere_api_key = "test-key"
    store.cohere_embedding_model = "test-model"
    store.max_retries = 2
    store.embedding_timeout = 5
    responses = iter([
        httpx.Response(429),
        httpx.Response(429),
        httpx.Response(200, json={"embeddings": {"float": [[0.1] * 384]}}),
    ])
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return next(responses)

    monkeypatch.setattr("app.storage.httpx.post", post)
    monkeypatch.setattr("app.storage.time.sleep", lambda _: None)

    result = store.embed(["question"], is_query=True)

    assert len(result[0]) == 384
    assert len(calls) == 3


def test_cohere_timeout_becomes_unavailable_and_four_xx_is_not_retried(monkeypatch):
    store = VectorStore.__new__(VectorStore)
    store.embedding_provider = "cohere"
    store.cohere_api_key = "test-key"
    store.cohere_embedding_model = "test-model"
    store.max_retries = 1
    store.embedding_timeout = 5
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.storage.httpx.post", timeout)
    monkeypatch.setattr("app.storage.time.sleep", lambda _: None)
    with pytest.raises(EmbeddingUnavailableError):
        store.embed(["question"])
    assert len(calls) == 2

    calls.clear()
    def bad_request(*args, **kwargs):
        calls.append(1)
        return httpx.Response(400)

    monkeypatch.setattr("app.storage.httpx.post", bad_request)
    with pytest.raises(EmbeddingUnavailableError):
        store.embed(["question"])
    assert len(calls) == 1


def test_cohere_rate_limit_error_is_distinguishable(monkeypatch):
    store = VectorStore.__new__(VectorStore)
    store.embedding_provider = "cohere"
    store.cohere_api_key = "test-key"
    store.cohere_embedding_model = "test-model"
    store.max_retries = 0
    store.embedding_timeout = 5
    monkeypatch.setattr("app.storage.httpx.post", lambda *args, **kwargs: httpx.Response(429))

    with pytest.raises(EmbeddingRateLimitError):
        store.embed(["question"])
