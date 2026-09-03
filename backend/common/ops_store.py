import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from backend.config.runtime_data import TMP_ROOT, PROJECT_ROOT, migrate_file


DATA_DIR = TMP_ROOT / "audit"


class JsonListStore:
    def __init__(self, filename: str):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = migrate_file(PROJECT_ROOT / "data" / filename, DATA_DIR / filename)

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


tool_failure_store = JsonListStore("tool_failures.json")


def record_tool_failure(
    tool_name: str,
    error: str,
    payload: Optional[Dict[str, Any]] = None,
    fallback: str = "",
) -> Dict[str, Any]:
    row = {
        "tool_name": tool_name,
        "error": error,
        "payload": payload or {},
        "fallback": fallback,
        "status": "open",
    }
    return tool_failure_store.create(row)
