"""Independent MCP server configuration.

The MCP server list deliberately lives outside ``config.json``.  ``config.json``
contains UI/runtime metadata (skills, permissions, and discovery timestamps),
while this file is the source of truth for servers loaded at application
startup.  Secrets may be represented by ``${ENV_VAR}`` placeholders and are
expanded only when a client is created.
"""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


MCP_CONFIG_PATH = Path(__file__).resolve().parent / "mcp_servers.json"
_ENV_ONLY = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
_BEARER_ENV_ONLY = re.compile(r"^Bearer\s+\$\{[A-Za-z_][A-Za-z0-9_]*\}$", re.I)
_SENSITIVE_ARG = re.compile(
    r"(?:api[-_]?key|token|secret|password|credential|authorization|header|auth)",
    re.I,
)
_SENSITIVE_INLINE = re.compile(
    r"(?:bearer\s+|authorization\s*[:=]|\b(?:token|secret|password|credential)\b|(?:token|secret|api[-_]?key)\s*[:=])",
    re.I,
)
_SENSITIVE_PATH = re.compile(r"(?:token|secret|api[-_]?key|password|credential|auth)", re.I)


def _normalize_transport(value: str) -> str:
    aliases = {
        "streamableHttp": "streamable_http",
        "streamable-http": "streamable_http",
        "http": "streamable_http",
    }
    return aliases.get((value or "streamable_http").strip(), (value or "streamable_http").strip())


def _public_secret(value: Any) -> str:
    text = str(value or "")
    if _ENV_ONLY.fullmatch(text) or _BEARER_ENV_ONLY.fullmatch(text):
        return text
    return "***configured***"


def _public_url(value: Any) -> str:
    text = str(value or "")
    try:
        parsed = urlsplit(text)
    except ValueError:
        return "***configured***"
    path_parts = [
        "***configured***" if part and (len(part) >= 32 or _SENSITIVE_PATH.search(part)) else part
        for part in parsed.path.split("/")
    ]
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"***configured***@{netloc.rsplit('@', 1)[1]}"
    query = urlencode([(key, _public_secret(item)) for key, item in parse_qsl(parsed.query, keep_blank_values=True)])
    fragment = "***configured***" if parsed.fragment else ""
    return urlunsplit((parsed.scheme, netloc, "/".join(path_parts), query, fragment))


def _public_args(values: Any) -> list[str]:
    args = [str(value) for value in values] if isinstance(values, list) else []
    redacted: list[str] = []
    redact_next = False
    for value in args:
        if redact_next:
            redacted.append(_public_secret(value))
            redact_next = False
            continue
        if "=" in value:
            flag, item = value.split("=", 1)
            if _SENSITIVE_ARG.search(flag):
                redacted.append(f"{flag}={_public_secret(item)}")
                continue
        if _SENSITIVE_INLINE.search(value) or (
            len(value) >= 32 and re.fullmatch(r"[A-Za-z0-9_./+=:-]+", value)
        ):
            redacted.append("***configured***")
            continue
        redacted.append(value)
        redact_next = bool(value.startswith("-") and _SENSITIVE_ARG.search(value))
    return redacted


def _normalize_server(server: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(server)
    normalized["transport"] = _normalize_transport(str(normalized.get("transport") or normalized.pop("type", "streamable_http")))
    # A pre-migration config may contain discovered tool schemas. Discard them
    # while loading so this file can never become a second tool registry.
    normalized.pop("tools", None)
    normalized.setdefault("enabled", True)
    normalized.setdefault("headers", {})
    normalized.setdefault("args", [])
    normalized.setdefault("env", {})
    normalized.setdefault("error", "")
    return normalized


class MCPServerStore:
    """Thread-safe persistence for the independent MCP server list."""

    def __init__(self, path: Path = MCP_CONFIG_PATH):
        self.path = Path(path).resolve()
        self._lock = RLock()
        self._servers: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            parsed = {}
        raw = parsed.get("mcpServers", parsed) if isinstance(parsed, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        self._servers = {
            str(name): _normalize_server(server)
            for name, server in raw.items()
            if isinstance(server, dict)
        }
        self._save_locked()

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps({"mcpServers": self._servers}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.path)

    def snapshot(self, *, public: bool = False) -> dict[str, Any]:
        with self._lock:
            servers = copy.deepcopy(self._servers)
        if public:
            for server in servers.values():
                server["headers"] = {
                    key: _public_secret(value) for key, value in (server.get("headers") or {}).items()
                }
                server["env"] = {
                    key: _public_secret(value) for key, value in (server.get("env") or {}).items()
                }
                server["url"] = _public_url(server.get("url"))
                server["args"] = _public_args(server.get("args"))
        return {"mcpServers": servers}

    def upsert(self, name: str, server: dict[str, Any]) -> None:
        with self._lock:
            self._servers[name] = _normalize_server(server)
            self._save_locked()

    def remove(self, name: str) -> bool:
        with self._lock:
            if name not in self._servers:
                return False
            del self._servers[name]
            self._save_locked()
            return True

    def update_discovery(self, results: dict[str, dict[str, Any]]) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            for name, result in results.items():
                server = self._servers.get(name)
                if server is None:
                    continue
                # Never persist the server's tool schemas. Only a count and the
                # last error are useful runtime metadata; actual tools are
                # reconstructed from the MCP server on the next startup.
                server["tool_count"] = int(result.get("tool_count") or 0)
                server["error"] = str(result.get("error") or "")
                server["updated_at"] = now
            self._save_locked()


MCP_STORE = MCPServerStore()
