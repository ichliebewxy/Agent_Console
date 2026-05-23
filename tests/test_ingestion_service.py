from dataclasses import dataclass

import pytest

from backend.services.ingestion_service import IngestionService, LocalIngestionTracker


@dataclass
class FakeDocument:
    doc_id: str
    tenant_id: str
    filename: str
    sha256: str
    version: int


class FakeRepo:
    def __init__(self):
        self.documents = []

    async def find_by_hash(self, *, tenant_id, sha256):
        return next(
            (doc for doc in self.documents if doc.tenant_id == tenant_id and doc.sha256 == sha256),
            None,
        )

    async def create_document(self, **payload):
        doc = FakeDocument(
            doc_id=f"doc-{len(self.documents) + 1}",
            tenant_id=payload["tenant_id"],
            filename=payload["filename"],
            sha256=payload["sha256"],
            version=1,
        )
        self.documents.append(doc)
        return doc


class FakeObjectStore:
    def __init__(self):
        self.objects = []

    async def put(self, **payload):
        self.objects.append(payload)


class FakeQueue:
    def __init__(self):
        self.jobs = []

    async def enqueue(self, name, payload):
        self.jobs.append((name, payload))


@pytest.mark.asyncio
async def test_duplicate_upload_is_idempotent():
    repo = FakeRepo()
    store = FakeObjectStore()
    queue = FakeQueue()
    service = IngestionService(repo, store, queue)

    first = await service.create_job(
        tenant_id="tenant-a",
        filename="faq.txt",
        content=b"hello nebulanest",
        content_type="text/plain",
        uploaded_by="alice",
    )
    second = await service.create_job(
        tenant_id="tenant-a",
        filename="faq-copy.txt",
        content=b"hello nebulanest",
        content_type="text/plain",
        uploaded_by="alice",
    )

    assert first.status == "queued"
    assert second.status == "deduplicated"
    assert first.doc_id == second.doc_id
    assert len(store.objects) == 1
    assert len(queue.jobs) == 1


def test_local_ingestion_tracker_records_ready_and_dedupes(tmp_path):
    tracker = LocalIngestionTracker(tmp_path / "manifest.json")
    row = tracker.start(filename="faq.txt", sha256="abc", content_type="text/plain")

    tracker.mark_ready(row["id"], chunk_count=3, parent_chunk_count=2)
    existing = tracker.find_ready_by_hash("abc")

    assert existing is not None
    assert existing["filename"] == "faq.txt"
    assert existing["chunk_count"] == 3
