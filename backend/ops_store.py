import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class JsonListStore:
    def __init__(self, filename: str):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = DATA_DIR / filename

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, rows: List[Dict[str, Any]]) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    def list(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self._load()
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: row.get("updated_at") or row.get("created_at") or "", reverse=True)
        return rows[:limit]

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        row = {
            "id": payload.get("id") or uuid4().hex,
            "status": payload.get("status") or "open",
            "created_at": now,
            "updated_at": now,
            **payload,
        }
        rows = self._load()
        rows.append(row)
        self._save(rows)
        return row

    def upsert_open(self, payload: Dict[str, Any], match_keys: List[str]) -> Dict[str, Any]:
        rows = self._load()
        for idx, row in enumerate(rows):
            if row.get("status") not in {"open", "retry_requested"}:
                continue
            if all(row.get(key) == payload.get(key) for key in match_keys):
                now = datetime.now().isoformat()
                updated = {
                    **row,
                    **payload,
                    "status": "open",
                    "updated_at": now,
                    "occurrence_count": int(row.get("occurrence_count") or 1) + 1,
                }
                rows[idx] = updated
                self._save(rows)
                return updated
        return self.create({**payload, "occurrence_count": 1})

tool_failure_store = JsonListStore("tool_failures.json")


def record_tool_failure(
    tool_name: str,
    error: str,
    payload: Optional[Dict[str, Any]] = None,
    fallback: str = "",
    dedupe: bool = False,
) -> Dict[str, Any]:
    row = {
        "tool_name": tool_name,
        "error": error,
        "payload": payload or {},
        "fallback": fallback,
        "status": "open",
        "callback_note": "",
    }
    if dedupe:
        return tool_failure_store.upsert_open(row, ["tool_name", "payload"])
    return tool_failure_store.create(row)
