import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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
    store.add_document("doc-1", "user-1", "hash-1", "guide.pdf", chunks, 100)

    result = store.query("What does the source describe?", 5, "user-1")

    assert len(result) == 1
    assert result[0]["chunk_id"] == "doc-1:0"
    assert result[0]["filename"] == "guide.pdf"
    assert result[0]["page"] == 7
    assert result[0]["score"] == pytest.approx(0.8, abs=1e-5)
    assert store.collection.metadata["hnsw:space"] == "cosine"

    store.delete_document("doc-1", "user-1")

    assert store.query("What does the source describe?", 5, "user-1") == []
    assert store.get_document("doc-1", "user-1") == {}


def test_document_chunks_have_full_metadata_and_duplicate_hash_is_rejected(tmp_path):
    store = make_store(tmp_path)
    store.add_document(
        "doc-1",
        "user-1",
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
            "user-1",
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
    assert store.get_document("pending-doc", "user-1") == {}


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
            "user-1",
            "hash-fail",
            "guide.pdf",
            [{"text": "Partial write test.", "page": 1, "section": None, "chunk_index": 0}],
            20,
        )

    assert store.collection.get(
        where={"document_id": "doc-fail"},
        include=["metadatas"],
    )["ids"] == []
    assert store.get_document("doc-fail", "user-1") == {}


def test_documents_and_similarity_search_are_isolated_by_owner(tmp_path):
    store = make_store(tmp_path)
    store.add_document(
        "alice-doc",
        "alice",
        "shared-hash",
        "alice.pdf",
        [{"text": "Private text for Alice.", "page": 1, "section": None, "chunk_index": 0}],
        100,
    )
    store.add_document(
        "bob-doc",
        "bob",
        "shared-hash",
        "bob.pdf",
        [{"text": "Private text for Bob.", "page": 1, "section": None, "chunk_index": 0}],
        100,
    )

    alice_results = store.query("What is private?", 5, "alice")
    bob_results = store.query("What is private?", 5, "bob")

    assert [item["filename"] for item in alice_results] == ["alice.pdf"]
    assert [item["filename"] for item in bob_results] == ["bob.pdf"]
    assert store.list_document_ids("alice") == ["alice-doc"]
    assert store.get_document("bob-doc", "alice") == {}
    assert store.delete_document("bob-doc", "alice") is False
    assert store.get_document("bob-doc", "bob")["filename"] == "bob.pdf"


def test_legacy_documents_migrate_as_unowned_and_remain_private(tmp_path):
    database_path = tmp_path / "documents.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE documents (
                document_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                sha256_hash TEXT NOT NULL UNIQUE,
                file_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('PENDING', 'READY')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO documents (
                document_id, file_name, sha256_hash, file_type,
                file_size_bytes, chunk_count, status
            ) VALUES ('legacy-doc', 'legacy.pdf', 'legacy-hash', 'pdf', 100, 1, 'READY')
            """
        )

    store = make_store(tmp_path)

    with store._connect() as connection:
        row = connection.execute(
            "SELECT owner_id FROM documents WHERE document_id = 'legacy-doc'"
        ).fetchone()
    assert row["owner_id"] is None
    assert store.list_document_ids("new-user") == []
    assert store.get_document("legacy-doc", "new-user") == {}


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


def test_concurrent_duplicate_uploads_create_only_one_document(tmp_path):
    store = make_store(tmp_path)
    embeddings_ready = Barrier(4)
    vector = [0.8, 0.6] + [0.0] * 382

    def embed(texts, is_query=False):
        embeddings_ready.wait(timeout=10)
        return [vector[:] for _ in texts]

    store.embed = embed

    def upload(index):
        try:
            store.add_document(
                f"parallel-{index}",
                "user-1",
                "same-parallel-hash",
                f"guide-{index}.txt",
                [{
                    "text": f"Concurrent document {index}.",
                    "page": None,
                    "section": None,
                    "chunk_index": 0,
                }],
                32,
            )
            return "created"
        except DuplicateDocumentError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(upload, range(4)))

    assert results.count("created") == 1
    assert results.count("duplicate") == 3
    assert len(store.list_document_ids("user-1")) == 1
    assert store.collection.count() == 1


def test_concurrent_queries_and_distinct_uploads_remain_consistent(tmp_path):
    store = make_store(tmp_path)

    def upload(index):
        store.add_document(
            f"document-{index}",
            "user-1",
            f"hash-{index}",
            f"guide-{index}.txt",
            [{
                "text": f"Concurrent risk governance document {index}.",
                "page": None,
                "section": None,
                "chunk_index": 0,
            }],
            40,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(upload, range(4)))
        results = list(executor.map(
            lambda _: store.query("risk governance", 10, "user-1"),
            range(8),
        ))

    assert all(len(result) == 4 for result in results)
    assert all(
        {chunk["document_id"] for chunk in result}
        == {f"document-{index}" for index in range(4)}
        for result in results
    )
