from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class IngestionJob:
    doc_id: str
    tenant_id: str
    sha256: str
    version: int
    status: str
    filename: str = ""
    content_type: str = ""
    object_key: str = ""


class IngestionService:
    def __init__(self, repo: Any, object_store: Any, queue: Any):
        self.repo = repo
        self.object_store = object_store
        self.queue = queue

    async def create_job(
        self,
        *,
        tenant_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        uploaded_by: str,
    ) -> IngestionJob:
        import hashlib

        sha256 = hashlib.sha256(content).hexdigest()
        existed = await self.repo.find_by_hash(tenant_id=tenant_id, sha256=sha256)
        if existed:
            return IngestionJob(
                doc_id=existed.doc_id,
                tenant_id=tenant_id,
                sha256=sha256,
                version=existed.version,
                status="deduplicated",
                filename=existed.filename,
                content_type=content_type,
            )

        doc = await self.repo.create_document(
            tenant_id=tenant_id,
            filename=filename,
            sha256=sha256,
            content_type=content_type,
            uploaded_by=uploaded_by,
            uploaded_at=datetime.now(UTC),
            status="pending",
        )
        object_key = f"{tenant_id}/{doc.doc_id}/{filename}"

        await self.object_store.put(
            bucket="raw-documents",
            key=object_key,
            body=content,
            content_type=content_type,
        )
        await self.queue.enqueue(
            "ingest_document",
            {
                "doc_id": doc.doc_id,
                "tenant_id": tenant_id,
                "sha256": sha256,
                "object_key": object_key,
            },
        )

        return IngestionJob(
            doc_id=doc.doc_id,
            tenant_id=tenant_id,
            sha256=sha256,
            version=doc.version,
            status="queued",
            filename=filename,
            content_type=content_type,
            object_key=object_key,
        )


class LocalIngestionTracker:
    def __init__(self, path: Path | None = None):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = path or DATA_DIR / "ingestion_manifest.json"

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    def find_ready_by_hash(self, sha256: str, tenant_id: str = "default") -> dict[str, Any] | None:
        for row in self._load():
            if row.get("tenant_id") == tenant_id and row.get("sha256") == sha256 and row.get("status") == "ready":
                return row
        return None

    def start(
        self,
        *,
        filename: str,
        sha256: str,
        content_type: str = "",
        tenant_id: str = "default",
        uploaded_by: str = "local",
    ) -> dict[str, Any]:
        rows = self._load()
        version = 1 + max(
            [
                int(row.get("version") or 0)
                for row in rows
                if row.get("tenant_id") == tenant_id and row.get("filename") == filename
            ]
            or [0]
        )
        now = datetime.now(UTC).isoformat()
        row = {
            "id": uuid4().hex,
            "tenant_id": tenant_id,
            "filename": filename,
            "sha256": sha256,
            "content_type": content_type,
            "uploaded_by": uploaded_by,
            "version": version,
            "status": "processing",
            "chunk_count": 0,
            "parent_chunk_count": 0,
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
        rows.append(row)
        self._save(rows)
        return row

    def mark_ready(self, doc_id: str, *, chunk_count: int, parent_chunk_count: int) -> dict[str, Any] | None:
        return self._update(
            doc_id,
            {
                "status": "ready",
                "chunk_count": chunk_count,
                "parent_chunk_count": parent_chunk_count,
                "error": "",
            },
        )

    def mark_failed(self, doc_id: str, error: str) -> dict[str, Any] | None:
        return self._update(doc_id, {"status": "failed", "error": error})

    def delete_by_filename(self, filename: str, tenant_id: str = "default") -> int:
        rows = self._load()
        kept = [row for row in rows if not (row.get("tenant_id") == tenant_id and row.get("filename") == filename)]
        deleted = len(rows) - len(kept)
        if deleted:
            self._save(kept)
        return deleted

    def _update(self, doc_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        rows = self._load()
        for index, row in enumerate(rows):
            if row.get("id") != doc_id:
                continue
            updated = {
                **row,
                **patch,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            rows[index] = updated
            self._save(rows)
            return updated
        return None
