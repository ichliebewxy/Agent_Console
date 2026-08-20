"""Shared redaction helpers for public configuration snapshots.

config_service (legacy embedded MCP list) and mcp_config_service
(source-of-truth mcp_servers.json) both expose public snapshots over the API.
They share one set of secret-detection and redaction rules so that a raw
credential never reaches the config UI, reverse-proxy logs, or the frontend.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_ENV_ONLY = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
_BEARER_ENV_ONLY = re.compile(
    r"^Bearer\s+\$\{[A-Za-z_][A-Za-z0-9_]*\}$",
    flags=re.IGNORECASE,
)
_SENSITIVE_ARG = re.compile(
    r"(?:api[-_]?key|token|secret|password|credential|authorization|header|auth)",
    re.IGNORECASE,
)
_SENSITIVE_INLINE = re.compile(
    r"(?:bearer\s+|authorization\s*[:=]|\b(?:token|secret|password|credential)\b|(?:token|secret|api[-_]?key)\s*[:=])",
    re.IGNORECASE,
)
_SENSITIVE_PATH = re.compile(
    r"(?:token|secret|api[-_]?key|password|credential|auth)",
    re.IGNORECASE,
)


def redact_secret(value: Any) -> str:
    """Hide a literal secret while preserving pure environment placeholders."""
    text = str(value or "")
    if _ENV_ONLY.fullmatch(text) or _BEARER_ENV_ONLY.fullmatch(text):
        return text
    return "***configured***"


def redact_url(value: Any) -> str:
    """Redact userinfo, sensitive path segments, query values and URL fragments."""
    text = str(value or "")
    try:
        parsed = urlsplit(text)
    except ValueError:
        return "***configured***"
    path_parts = [
        "***configured***"
        if part and (len(part) >= 32 or _SENSITIVE_PATH.search(part))
        else part
        for part in parsed.path.split("/")
    ]
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"***configured***@{netloc.rsplit('@', 1)[1]}"
    query = urlencode(
        [(key, redact_secret(item)) for key, item in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    fragment = "***configured***" if parsed.fragment else ""
    return urlunsplit((parsed.scheme, netloc, "/".join(path_parts), query, fragment))


def redact_args(values: Any) -> list[str]:
    """Redact sensitive CLI arguments, including the value of a preceding flag."""
    args = [str(value) for value in values] if isinstance(values, list) else []
    redacted: list[str] = []
    redact_next = False
    for value in args:
        if redact_next:
            redacted.append(redact_secret(value))
            redact_next = False
            continue
        if "=" in value:
            flag, item = value.split("=", 1)
            if _SENSITIVE_ARG.search(flag):
                redacted.append(f"{flag}={redact_secret(item)}")
                continue
        if _SENSITIVE_INLINE.search(value) or (
            len(value) >= 32 and re.fullmatch(r"[A-Za-z0-9_./+=:-]+", value)
        ):
            redacted.append("***configured***")
            continue
        redacted.append(value)
        redact_next = bool(value.startswith("-") and _SENSITIVE_ARG.search(value))
    return redacted
