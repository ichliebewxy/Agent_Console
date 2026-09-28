"""Shared classification for error strings returned by LangChain tools."""

ERROR_PREFIXES = (
    "TOOL_ERROR:",
    "OPENCLI_ERROR:",
    "SPECIALIST_ERROR:",
    "SKILL_ERROR:",
    "SKILL_AGENT_ERROR:",
    "SUBAGENT_ERROR:",
    "WORKSPACE_ERROR:",
    "LOCAL_RUNTIME_ERROR:",
    "PERMISSION_DENIED:",
    "TOOL_CALL_LIMIT_REACHED:",
    "UNKNOWN_EFFECT:",
)


def is_error_result(result: object) -> bool:
    return isinstance(result, str) and result.startswith(ERROR_PREFIXES)


def contains_error_result(text: str) -> bool:
    """Detect a tool error even when the agent embeds it in a step response."""
    return any(prefix in text for prefix in ERROR_PREFIXES)
