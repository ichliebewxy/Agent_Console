"""User/project skill defaults, independent of the installed skill packages."""

import json
import os
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4

from settings import PROJECT_ROOT


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class SkillBindingStore:
    def __init__(self, path: Path = PROJECT_ROOT / "data" / "skill_bindings.json"):
        self.path = Path(path)
        self._lock = RLock()

    def _key(self, user_id: str, project_id: str | None) -> str:
        if not _ID.fullmatch(user_id) or (project_id is not None and not _ID.fullmatch(project_id)):
            raise ValueError("Invalid user or project ID.")
        return f"{user_id}\0{project_id or ''}"

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Skill binding store is invalid.")
        return data

    def get(self, user_id: str, project_id: str | None = None) -> dict[str, bool]:
        key = self._key(user_id, project_id)
        with self._lock:
            value = self._read().get(key, {})
        if not isinstance(value, dict) or any(not isinstance(name, str) or not isinstance(enabled, bool) for name, enabled in value.items()):
            raise ValueError("Skill binding record is invalid.")
        return value

    def put(self, user_id: str, project_id: str | None, bindings: dict[str, bool]) -> dict[str, bool]:
        if not isinstance(bindings, dict) or len(bindings) > 256 or any(
            not _ID.fullmatch(name) or not isinstance(enabled, bool)
            for name, enabled in bindings.items()
        ):
            raise ValueError("Invalid skill bindings.")
        key = self._key(user_id, project_id)
        with self._lock:
            data = self._read()
            data[key] = bindings
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        return bindings.copy()


SKILL_BINDINGS = SkillBindingStore()
