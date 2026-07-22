"""Thread-safe backend/config.json persistence and runtime catalog metadata."""
import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

DEFAULT_BASH_PERMISSIONS = {
    "default": "deny",
    "deny": [
        {
            "id": "deny-system-destructive",
            "description": "阻止提权、关机、磁盘和系统级破坏命令",
            "patterns": [
                r"\b(?:sudo|shutdown|reboot|mkfs(?:\.\w+)?|diskpart|bcdedit)\b",
                r"\b(?:format|fdisk|parted)\b",
                r"\bdd\s+if=",
                r"rm\s+-[^\r\n]*r[^\r\n]*f\s+(?:/|~|\*)",
                r"\b(?:reg|sc)\s+delete\b",
            ],
        },
        {
            "id": "deny-workspace-escape",
            "description": "阻止命令访问 backend/tmp 会话目录之外的本地路径",
            "patterns": [
                r"(?:^|[\s'\"])(?:\.\.[\\/])",
                r"(?:^|[\s'\"])[A-Za-z]:[\\/]",
                r"(?:^|[\s'\"])/(?:etc|home|root|usr|var|opt|proc|sys|dev)(?:[\\/\s'\"]|$)",
                r"%(?:USERPROFILE|APPDATA|LOCALAPPDATA|SYSTEMROOT|WINDIR)%",
                r"\$(?:HOME|USERPROFILE|APPDATA|SYSTEMROOT|WINDIR)\b",
            ],
        },
        {
            "id": "deny-shell-escalation",
            "description": "阻止下载后直接执行、策略绕过和危险权限修改",
            "patterns": [
                r"\bchmod\s+777\b",
                r"\bset-executionpolicy\b",
                r"\b(?:curl|wget|iwr|invoke-webrequest)\b[^\r\n|]*\|\s*(?:sh|bash|pwsh|powershell)\b",
            ],
        },
        {
            "id": "deny-opencli-high-risk",
            "description": "阻止 OpenCLI 删除、上传、任意代码执行和插件安装等高风险操作",
            "patterns": [
                r"^opencli\b[^\r\n]*\b(?:delete|remove|archive|upload|eval|auto-approve|approve)\b",
                r"^opencli\s+plugin\b[^\r\n]*\b(?:install|update|uninstall)\b",
                r"^opencli\s+external\b[^\r\n]*\b(?:install|register)\b",
                r"^opencli\s+daemon\b[^\r\n]*(?:0\.0\.0\.0|--public)\b",
            ],
        },
    ],
    "authorize": [
        {
            "id": "authorize-opencli-external-write",
            "description": "OpenCLI 登录、发帖、发送和浏览器交互仅在用户明确要求该副作用时执行",
            "patterns": [
                r"^opencli\b[^\r\n]*\b(?:login|refresh|post|send|message|follow|unfollow|like|unlike|favorite|unfavorite|subscribe|unsubscribe|comment|create|purchase|pay|order|generate|rename|pin|model)\b",
                r"^opencli\s+browser\b[^\r\n]*\b(?:click|type|fill|press|select|check|uncheck|drag|submit)\b",
                r"^opencli\s+(?:adapter|profile|daemon)\b[^\r\n]*\b(?:eject|reset|rename|use|stop|restart)\b",
            ],
        }
    ],
    "allow": [
        {
            "id": "allow-tmp-development",
            "description": "允许在当前 backend/tmp 会话目录内进行常见开发、查询和 OpenCLI 操作",
            "patterns": [
                r"^(?:python|python3|py|node|npm|npx|opencli|git|rg|grep|dir|type|echo|where|mkdir|uv|pytest|ruff|mypy|radon|pip-audit|cargo|pdftotext|pdfinfo|pandoc|wkhtmltopdf|qpdf|mutool|ffmpeg|tesseract)\b",
                r"^(?:get-childitem|get-content|set-content|test-path|select-string|copy-item|new-item|get-command|measure-object)\b",
            ],
        }
    ],
}

_ENV_ONLY = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
_BEARER_ENV_ONLY = re.compile(
    r"^Bearer\s+\$\{[A-Za-z_][A-Za-z0-9_]*\}$",
    flags=re.IGNORECASE,
)
_SENSITIVE_ARG = re.compile(
    r"(?:api[-_]?key|token|secret|password|credential|authorization|header|auth)",
    re.I,
)
_SENSITIVE_INLINE = re.compile(
    r"(?:bearer\s+|authorization\s*[:=]|\b(?:token|secret|password|credential)\b|(?:token|secret|api[-_]?key)\s*[:=])",
    re.I,
)
_SENSITIVE_PATH = re.compile(r"(?:token|secret|api[-_]?key|password|credential|auth)", re.I)


def _default_config() -> dict[str, Any]:
    return {
        "mcpServers": {},
        "skills": [],
        "permissions": {"bash": copy.deepcopy(DEFAULT_BASH_PERMISSIONS)},
        "discovery": {"updated_at": "", "skill_errors": []},
    }


def _normalize_transport(value: str) -> str:
    normalized = (value or "streamable_http").strip()
    aliases = {
        "streamableHttp": "streamable_http",
        "streamable-http": "streamable_http",
        "sse": "sse",
        "stdio": "stdio",
    }
    return aliases.get(normalized, normalized)


def _merge_permission_defaults(configured: Any) -> dict[str, Any]:
    """Keep security defaults present while preserving user-added rules."""
    source = configured if isinstance(configured, dict) else {}
    merged = copy.deepcopy(source)
    merged["default"] = str(source.get("default") or "deny")
    for behavior in ("deny", "authorize", "allow"):
        rows = source.get(behavior)
        rows = copy.deepcopy(rows) if isinstance(rows, list) else []
        by_id = {
            str(row.get("id")): row
            for row in rows
            if isinstance(row, dict) and row.get("id")
        }
        for default_rule in DEFAULT_BASH_PERMISSIONS[behavior]:
            existing = by_id.get(default_rule["id"])
            if existing is None:
                rows.append(copy.deepcopy(default_rule))
                continue
            patterns = existing.get("patterns")
            patterns = list(patterns) if isinstance(patterns, list) else []
            for pattern in default_rule["patterns"]:
                if pattern not in patterns:
                    patterns.append(pattern)
            existing["patterns"] = patterns
            existing.setdefault("description", default_rule["description"])
        merged[behavior] = rows
    return merged


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
    path_parts = []
    for part in parsed.path.split("/"):
        if part and (len(part) >= 32 or _SENSITIVE_PATH.search(part)):
            path_parts.append("***configured***")
        else:
            path_parts.append(part)
    safe_path = "/".join(path_parts)
    if not parsed.query:
        netloc = parsed.netloc
        if "@" in netloc:
            netloc = f"***configured***@{netloc.rsplit('@', 1)[1]}"
        fragment = "***configured***" if parsed.fragment else ""
        return urlunsplit((parsed.scheme, netloc, safe_path, "", fragment))
    query = urlencode(
        [(key, _public_secret(item)) for key, item in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"***configured***@{netloc.rsplit('@', 1)[1]}"
    fragment = "***configured***" if parsed.fragment else ""
    return urlunsplit((parsed.scheme, netloc, safe_path, query, fragment))


def _public_args(values: Any) -> list[str]:
    args = [str(value) for value in values] if isinstance(values, list) else []
    redacted = []
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


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = Path(path).resolve()
        self._lock = RLock()
        self._data = self._load()
        self._save_locked()

    def _load(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            parsed = {}
        data = _default_config()
        if isinstance(parsed, dict):
            data.update(parsed)
        servers = data.get("mcpServers")
        data["mcpServers"] = servers if isinstance(servers, dict) else {}
        for name, server in list(data["mcpServers"].items()):
            if not isinstance(server, dict):
                del data["mcpServers"][name]
                continue
            server["transport"] = _normalize_transport(
                str(server.get("transport") or server.pop("type", "streamable_http"))
            )
            server.setdefault("enabled", True)
            server.setdefault("headers", {})
            server.setdefault("tools", [])
            server.setdefault("error", "")
        if not isinstance(data.get("skills"), list):
            data["skills"] = []
        permissions = data.get("permissions")
        if not isinstance(permissions, dict):
            permissions = {}
        permissions["bash"] = _merge_permission_defaults(permissions.get("bash"))
        data["permissions"] = permissions
        if not isinstance(data.get("discovery"), dict):
            data["discovery"] = {"updated_at": "", "skill_errors": []}
        data["discovery"].setdefault("skill_errors", [])
        return data

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.path)

    def snapshot(self, *, public: bool = False) -> dict[str, Any]:
        with self._lock:
            data = copy.deepcopy(self._data)
        if public:
            for server in data.get("mcpServers", {}).values():
                headers = server.get("headers") or {}
                server["headers"] = {
                    key: _public_secret(value)
                    for key, value in headers.items()
                }
                environment = server.get("env") or {}
                server["env"] = {
                    key: _public_secret(value)
                    for key, value in environment.items()
                }
                server["url"] = _public_url(server.get("url"))
                server["args"] = _public_args(server.get("args"))
        return data

    def upsert_mcp_server(self, name: str, server: dict[str, Any]) -> None:
        clean = copy.deepcopy(server)
        clean["transport"] = _normalize_transport(str(clean.get("transport") or ""))
        clean.setdefault("enabled", True)
        clean.setdefault("headers", {})
        clean["tools"] = []
        clean["error"] = ""
        with self._lock:
            self._data["mcpServers"][name] = clean
            self._save_locked()

    def remove_mcp_server(self, name: str) -> bool:
        with self._lock:
            if name not in self._data["mcpServers"]:
                return False
            del self._data["mcpServers"][name]
            self._save_locked()
            return True

    def update_mcp_discovery(self, results: dict[str, dict[str, Any]]) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            for name, result in results.items():
                server = self._data["mcpServers"].get(name)
                if server is None:
                    continue
                server["tools"] = copy.deepcopy(result.get("tools") or [])
                server["error"] = str(result.get("error") or "")
                server["updated_at"] = now
            self._data["discovery"]["updated_at"] = now
            self._save_locked()

    def sync_skills(
        self,
        skills: list[dict[str, Any]],
        errors: list[dict[str, str]] | None = None,
    ) -> None:
        with self._lock:
            self._data["skills"] = copy.deepcopy(skills)
            self._data["discovery"]["skill_errors"] = copy.deepcopy(errors or [])
            self._data["discovery"]["updated_at"] = datetime.now().isoformat()
            self._save_locked()

    def bash_permissions(self) -> dict[str, Any]:
        with self._lock:
            rules = self._data.get("permissions", {}).get("bash")
            return copy.deepcopy(rules or DEFAULT_BASH_PERMISSIONS)


CONFIG_STORE = ConfigStore()
