"""List and safely resolve downloadable files created in a chat session."""
import base64
import hashlib
import hmac
import mimetypes
import os
import secrets
import stat as stat_module
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from runtime_context import session_files_dir
from settings import ARTIFACT_SIGNING_KEY, BACKEND_TMP_DIR

_INTERNAL_DIRS = {".cache", ".npm-cache", ".pycache", "__pycache__"}


@lru_cache(maxsize=1)
def _signing_key() -> bytes:
    """Load the configured capability key or create one local persistent key."""
    if ARTIFACT_SIGNING_KEY:
        return ARTIFACT_SIGNING_KEY.encode("utf-8")
    key_path = BACKEND_TMP_DIR / ".artifact_signing_key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        value = key_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        value = secrets.token_urlsafe(48)
        try:
            with key_path.open("x", encoding="utf-8") as handle:
                handle.write(value)
        except FileExistsError:
            value = key_path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("Artifact signing key is empty.")
    return value.encode("utf-8")


def artifact_access_token(user_id: str, session_id: str) -> str:
    payload = f"{user_id}\0{session_id}".encode("utf-8")
    digest = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_artifact_access(user_id: str, session_id: str, token: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(artifact_access_token(user_id, session_id), token)


def _safe_artifact_path(user_id: str, session_id: str, relative_path: str) -> Path:
    root = session_files_dir(user_id, session_id, create=False)
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Artifact path escapes the session workspace.")
    return target


def _safe_artifact_open_path(user_id: str, session_id: str, relative_path: str) -> Path:
    """Resolve the parent only so O_NOFOLLOW can protect the final path component."""
    root = session_files_dir(user_id, session_id, create=False)
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("Artifact path escapes the session workspace.")
    parent = (root / relative.parent).resolve()
    if not parent.is_relative_to(root):
        raise ValueError("Artifact path escapes the session workspace.")
    return parent / relative.name


def list_session_artifacts(user_id: str, session_id: str, limit: int = 200) -> list[dict]:
    root = session_files_dir(user_id, session_id, create=False)
    if not root.exists():
        return []
    artifacts = []
    token = artifact_access_token(user_id, session_id)
    encoded_user = quote(user_id, safe="")
    encoded_session = quote(session_id, safe="")
    stack = [root]
    while stack and len(artifacts) < limit:
        directory = stack.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            for entry in entries:
                if len(artifacts) >= limit:
                    break
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in _INTERNAL_DIRS:
                            continue
                        stack.append(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    path = Path(entry.path)
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                relative = path.relative_to(root).as_posix()
                encoded_path = quote(relative, safe="/")
                mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                artifacts.append(
                    {
                        "path": relative,
                        "name": path.name,
                        "size": stat.st_size,
                        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "mime_type": mime_type,
                        "download_url": (
                            f"/sessions/{encoded_user}/{encoded_session}/artifacts/"
                            f"{encoded_path}?token={quote(token, safe='')}"
                        ),
                    }
                )
    artifacts.sort(key=lambda item: item["path"])
    return artifacts


def resolve_session_artifact(user_id: str, session_id: str, relative_path: str) -> Path:
    target = _safe_artifact_path(user_id, session_id, relative_path)
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    return target


def open_session_artifact(user_id: str, session_id: str, relative_path: str):
    """Atomically open a regular artifact without following a final symlink."""
    target = _safe_artifact_open_path(user_id, session_id, relative_path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags)
    try:
        stat = os.fstat(descriptor)
        if not stat_module.S_ISREG(stat.st_mode):
            raise FileNotFoundError(relative_path)
        return os.fdopen(descriptor, "rb"), target, stat
    except Exception:
        os.close(descriptor)
        raise
