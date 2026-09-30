"""Persistent, per-session resource policy. No agent or storage implementation lives here."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4

from settings import PROJECT_ROOT


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SCOPES = {"user", "project", "session"}


@dataclass(frozen=True)
class SessionResources:
    project_id: str | None = None
    # None inherits the installed catalog. An empty list disables every skill.
    skills: tuple[str, ...] | None = None
    memory_read_scopes: tuple[str, ...] = ("user", "session")
    memory_write_scope: str = "session"


def validate_resources(value: dict) -> SessionResources:
    if not isinstance(value, dict):
        raise ValueError("Session resources must be an object.")
    if set(value) - {"project_id", "skills", "memory_read_scopes", "memory_write_scope"}:
        raise ValueError("Unknown session resource field.")
    project_id = value.get("project_id") or None
    if project_id is not None and (not isinstance(project_id, str) or not _ID.fullmatch(project_id)):
        raise ValueError("Invalid project_id.")
    skills = value.get("skills")
    if skills is not None:
        if not isinstance(skills, list) or len(skills) > 256 or any(
            not isinstance(name, str) or not _ID.fullmatch(name) for name in skills
        ):
            raise ValueError("skills must be a list of valid skill names.")
        if len(set(skills)) != len(skills):
            raise ValueError("Duplicate skill names are not allowed.")
    read = value.get("memory_read_scopes", ["user", "session"])
    write = value.get("memory_write_scope", "session")
    if not isinstance(read, list) or not read or len(set(read)) != len(read) or set(read) - _SCOPES:
        raise ValueError("Invalid memory_read_scopes.")
    if write not in _SCOPES:
        raise ValueError("Invalid memory_write_scope.")
    if project_id is None and ("project" in read or write == "project"):
        raise ValueError("Project memory requires project_id.")
    return SessionResources(project_id, tuple(skills) if skills is not None else None, tuple(read), write)


class SessionResourceStore:
    def __init__(self, path: Path = PROJECT_ROOT / "data" / "session_resources.json"):
        self.path = Path(path)
        self._lock = RLock()

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        if not _ID.fullmatch(user_id) or not _ID.fullmatch(session_id):
            raise ValueError("Invalid user_id or session_id.")
        return f"{user_id}\0{session_id}"

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Session resource store is invalid.")
        return data

    def get(self, user_id: str, session_id: str) -> SessionResources:
        key = self._key(user_id, session_id)
        with self._lock:
            record = self._read().get(key)
        return validate_resources(record) if record is not None else SessionResources()

    def put(self, user_id: str, session_id: str, value: dict) -> SessionResources:
        key = self._key(user_id, session_id)
        resources = validate_resources(value)
        with self._lock:
            data = self._read()
            data[key] = asdict(resources)
            self._write(data)
        return resources

    def delete(self, user_id: str, session_id: str) -> None:
        key = self._key(user_id, session_id)
        with self._lock:
            data = self._read()
            if key in data:
                del data[key]
                self._write(data)

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


SESSION_RESOURCES = SessionResourceStore()
