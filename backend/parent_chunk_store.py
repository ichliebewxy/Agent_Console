"""父级分块文档存储（用于 Auto-merging Retriever）"""
import json
from pathlib import Path
from typing import Dict, List


class ParentChunkStore:
    """基于本地 JSON 的父级分块存储。"""

    def __init__(self, store_path: Path | None = None):
        base_dir = Path(__file__).resolve().parent
        self.store_path = store_path or (base_dir.parent / "data" / "parent_chunks.json")
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, dict]:
        if not self.store_path.exists():
            return {}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def _save(self, data: Dict[str, dict]) -> None:
        tmp_path = self.store_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp_path.replace(self.store_path)

    def upsert_documents(self, docs: List[dict]) -> int:
        """写入/更新父级分块，返回写入条数。"""
        if not docs:
            return 0

        store = self._load()
        upserted = 0
        for doc in docs:
            chunk_id = (doc.get("chunk_id") or "").strip()
            if not chunk_id:
                continue
            store[chunk_id] = {
                "text": doc.get("text", ""),
                "filename": doc.get("filename", ""),
                "file_type": doc.get("file_type", ""),
                "file_path": doc.get("file_path", ""),
                "page_number": doc.get("page_number", 0),
                "chunk_id": chunk_id,
                "parent_chunk_id": doc.get("parent_chunk_id", ""),
                "root_chunk_id": doc.get("root_chunk_id", ""),
                "chunk_level": int(doc.get("chunk_level", 0) or 0),
                "chunk_idx": int(doc.get("chunk_idx", 0) or 0),
            }
            upserted += 1

        self._save(store)
        return upserted

    def get_documents_by_ids(self, chunk_ids: List[str]) -> List[dict]:
        if not chunk_ids:
            return []
        store = self._load()
        return [store[item] for item in chunk_ids if item in store]

    def delete_by_filename(self, filename: str) -> int:
        """按文件名删除父级分块，返回删除条数。"""
        if not filename:
            return 0

        store = self._load()
        before = len(store)
        filtered = {
            key: value for key, value in store.items()
            if value.get("filename") != filename
        }
        deleted = before - len(filtered)
        if deleted > 0:
            self._save(filtered)
        return deleted
