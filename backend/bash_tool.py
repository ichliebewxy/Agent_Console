"""Reviewed Bash tool inspired by learn-claude-code s03_permission."""
import re
from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import tool

from config_service import CONFIG_STORE
from local_runtime_service import run_local_command
from ops_store import record_bash_audit
from runtime_context import current_runtime_context
from settings import LOCAL_RUN_COMMAND_MAX_CHARS


@dataclass(frozen=True)
class PermissionDecision:
    behavior: Literal["allow", "deny"]
    rule_id: str
    reason: str


_OPENCLI_SAFE_COMMANDS = {
    "version",
    "help",
    "list",
    "validate",
    "verify",
    "skills",
    "doctor",
    "state",
    "find",
    "get",
    "extract",
    "search",
    "query",
    "top",
    "hot",
    "trending",
    "current",
    "weather",
    "geo",
    "info",
    "detail",
    "read",
    "history",
    "projects",
    "status",
    "title",
    "url",
    "text",
    "value",
    "html",
    "attributes",
    "network",
    "download",
    "export",
    "screenshot",
    "open",
    "bind",
    "unbind",
    "close",
    "back",
    "scroll",
    "tab",
    "wait",
}


def _command_words(command: str) -> list[str]:
    return re.findall(r"[^\s\"']+", command)


def _opencli_needs_authorization(command: str) -> bool:
    words = [word.lower() for word in _command_words(command)]
    if not words or words[0] != "opencli":
        return False
    words = words[1:]
    if not words:
        return False
    if words[0].startswith("-"):
        return words[0] not in {"--version", "--help", "-h"}
    top_level_read = {"list", "validate", "verify", "skills", "doctor", "completion"}
    if words[0] in top_level_read:
        return False
    if words[0] == "browser":
        # browser <session> <command>; a missing command is help/discovery.
        operation = words[2] if len(words) > 2 else "help"
        return operation not in _OPENCLI_SAFE_COMMANDS
    if words[0] in {"plugin", "adapter", "profile", "daemon", "external", "auth"}:
        operation = words[1] if len(words) > 1 else "help"
        return operation not in {"help", "list", "status", "read"}
    operation = words[1] if len(words) > 1 else words[0]
    return operation not in _OPENCLI_SAFE_COMMANDS


def _unquoted_shell_control(command: str) -> str | None:
    """Return shell syntax that could introduce a second command."""
    single = False
    double = False
    escaped = False
    for index, character in enumerate(command):
        if character in "\r\n":
            return "newline"
        if escaped:
            escaped = False
            continue
        if character == "\\" and (single or double):
            escaped = True
            continue
        if character == "'" and not double:
            single = not single
            continue
        if character == '"' and not single:
            double = not double
            continue
        if single:
            continue
        if character == "`":
            return "backtick"
        if character == "^":
            return "cmd-caret"
        if character == "$" and index + 1 < len(command) and command[index + 1] == "(":
            return "command-substitution"
        if not double and character in ";&|":
            return character
    return None


def review_bash_command(
    command: str,
    *,
    user_authorized_side_effect: bool = False,
    opencli_access: Literal["unknown", "read", "write", "p4"] = "unknown",
) -> PermissionDecision:
    """Apply hard validation, then deny rules, allow rules, and default behavior."""
    command = (command or "").strip()
    if not command:
        return PermissionDecision("deny", "invalid-empty", "命令不能为空")
    if "\x00" in command or len(command) > LOCAL_RUN_COMMAND_MAX_CHARS:
        return PermissionDecision("deny", "invalid-command", "命令包含 NUL 或超过长度限制")
    shell_control = _unquoted_shell_control(command)
    if shell_control:
        return PermissionDecision(
            "deny",
            "deny-shell-chaining",
            f"命令包含未允许的 shell 控制符：{shell_control}",
        )

    config = CONFIG_STORE.bash_permissions()
    for rule in config.get("deny") or []:
        for pattern in rule.get("patterns") or []:
            try:
                if re.search(pattern, command, flags=re.IGNORECASE):
                    return PermissionDecision(
                        "deny",
                        str(rule.get("id") or "configured-deny"),
                        str(rule.get("description") or "命中 Bash 拒绝规则"),
                    )
            except re.error:
                continue

    authorization_rule = None
    for rule in config.get("authorize") or []:
        for pattern in rule.get("patterns") or []:
            try:
                if re.search(pattern, command, flags=re.IGNORECASE):
                    if not user_authorized_side_effect:
                        return PermissionDecision(
                            "deny",
                            str(rule.get("id") or "explicit-user-authorization-required"),
                            str(
                                rule.get("description")
                                or "该外部副作用需要用户在当前任务中明确要求"
                            ),
                        )
                    authorization_rule = rule
                    break
            except re.error:
                continue

    if command.lower().lstrip().startswith("opencli") and opencli_access == "p4":
        return PermissionDecision(
            "deny",
            "deny-opencli-p4",
            "OpenCLI registry marks this command P4; execution is disabled by policy",
        )

    if _opencli_needs_authorization(command):
        if opencli_access == "read":
            authorization_rule = {
                "id": "allow-opencli-registry-read",
                "description": "OpenCLI live registry marked this dynamic command access=read",
            }
        elif not user_authorized_side_effect:
            return PermissionDecision(
                "deny",
                "authorize-opencli-unknown",
                "OpenCLI 动态命令未标明为只读；需要当前用户明确授权该副作用",
            )
        else:
            authorization_rule = {
                "id": "authorize-opencli-unknown",
                "description": "OpenCLI 动态命令由用户在当前任务中明确授权",
            }

    for rule in config.get("allow") or []:
        for pattern in rule.get("patterns") or []:
            try:
                if re.search(pattern, command, flags=re.IGNORECASE):
                    if authorization_rule is not None:
                        rule_id = str(
                            authorization_rule.get("id")
                            or "explicit-user-authorization"
                        )
                        reason = (
                            "OpenCLI live registry marked this command read-only; execution recorded."
                            if rule_id == "allow-opencli-registry-read"
                            else "用户在当前任务中明确要求该外部副作用；已记录授权执行。"
                        )
                        return PermissionDecision(
                            "allow",
                            rule_id,
                            reason,
                        )
                    return PermissionDecision(
                        "allow",
                        str(rule.get("id") or "configured-allow"),
                        str(rule.get("description") or "命中 Bash 允许规则"),
                    )
            except re.error:
                continue

    return PermissionDecision(
        "deny",
        "default-deny",
        "命令未命中明确允许规则；请改成更小、更明确的命令",
    )


def _exit_code(result: str) -> int | None:
    match = re.search(r"LOCAL_RUNTIME_EXIT_CODE=(-?\d+)", result or "")
    return int(match.group(1)) if match else None


@tool("bash")
async def bash(
    command: str,
    user_authorized_side_effect: bool = False,
    opencli_access: Literal["unknown", "read", "write", "p4"] = "unknown",
) -> str:
    """Review and run one command in backend/tmp; OpenCLI access must match live registry evidence."""
    command = (command or "").strip()
    decision = review_bash_command(
        command,
        user_authorized_side_effect=user_authorized_side_effect,
        opencli_access=opencli_access,
    )
    context = current_runtime_context()
    if decision.behavior == "deny":
        record_bash_audit(
            behavior="deny",
            rule_id=decision.rule_id,
            reason=decision.reason,
            command=command,
            user_id=context.user_id,
            session_id=context.session_id,
        )
        return (
            f"PERMISSION_DENIED: rule={decision.rule_id}; reason={decision.reason}. "
            "Do not retry the same command; choose a safer scoped command."
        )

    result = await run_local_command(command)
    record_bash_audit(
        behavior="allow",
        rule_id=decision.rule_id,
        reason=decision.reason,
        command=command,
        user_id=context.user_id,
        session_id=context.session_id,
        exit_code=_exit_code(result),
    )
    return result


BASH_TOOLS = [bash]
