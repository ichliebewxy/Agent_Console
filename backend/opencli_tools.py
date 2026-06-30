"""OpenCLI browser automation tools."""
import os
import shutil
import subprocess
from typing import Optional

from langchain_core.tools import tool

from ops_store import record_tool_failure
from settings import (
    OPENCLI_BIN,
    OPENCLI_OUTPUT_MAX_CHARS,
    OPENCLI_SESSION,
    OPENCLI_TIMEOUT,
)


class OpenCLIError(RuntimeError):
    pass


def _node_opencli_command(cmd_path: str) -> list[str] | None:
    base_dir = os.path.dirname(os.path.abspath(cmd_path))
    script = os.path.join(base_dir, "node_modules", "@jackwener", "opencli", "dist", "src", "main.js")
    if not os.path.exists(script):
        return None
    node = os.path.join(base_dir, "node.exe")
    if not os.path.exists(node):
        node = shutil.which("node") or ""
    if not node:
        return None
    return [node, script]


def _opencli_command() -> list[str]:
    configured = OPENCLI_BIN
    candidates = []
    if configured:
        candidates.append(configured)

    if os.name == "nt":
        candidates.extend(["opencli.cmd", "opencli.exe", "opencli"])
    else:
        candidates.append("opencli")

    for candidate in candidates:
        found = shutil.which(candidate)
        if not found and os.path.exists(candidate):
            found = candidate
        if not found:
            continue

        if os.name == "nt" and found.lower().endswith((".cmd", ".bat")):
            node_command = _node_opencli_command(found)
            if node_command:
                return node_command

        if os.name == "nt" and found.lower().endswith(".ps1"):
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if not powershell:
                raise OpenCLIError("找到 opencli.ps1，但找不到 PowerShell，无法执行 OpenCLI。")
            return [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                found,
            ]

        return [found]

    raise OpenCLIError(
        "找不到 opencli 命令。请先安装 @jackwener/opencli，并确认 npm 全局 bin 目录在 PATH 中；"
        "也可以在 .env 中设置 OPENCLI_BIN=C:\\Users\\wangy\\AppData\\Roaming\\npm\\opencli.cmd。"
    )


def _cmd_quote(value: str) -> str:
    escaped = value.replace('"', r'\"')
    return f'"{escaped}"'


def _subprocess_command(args: list[str]) -> list[str] | str:
    command = _opencli_command()
    executable = command[0].lower()
    if os.name == "nt" and executable.endswith((".cmd", ".bat")):
        # Batch files are interpreted by cmd.exe. Quote every argument so URLs
        # such as ?ps=10&pn=1 are not split at "&" into a second command.
        cmdline = "call " + " ".join(_cmd_quote(part) for part in [command[0], *args])
        # subprocess(list) adds another Windows quoting layer around the /c
        # payload. Passing the full command line string keeps cmd parsing sane.
        return f"cmd.exe /d /c {cmdline}"
    return [*command, *args]


def _run_opencli(args: list[str], timeout: int = OPENCLI_TIMEOUT) -> str:
    cmd = _subprocess_command(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        executable = cmd.split()[0] if isinstance(cmd, str) else cmd[0]
        raise OpenCLIError(f"找不到 OpenCLI 可执行文件: {executable}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OpenCLIError(f"OpenCLI 命令超时: {' '.join(cmd)}") from exc

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        raise OpenCLIError(
            f"OpenCLI 执行失败，exit_code={result.returncode}\n"
            f"cmd={cmd if isinstance(cmd, str) else ' '.join(cmd)}\nstdout={stdout}\nstderr={stderr}"
        )

    output = stdout or stderr or "(no output)"
    if len(output) > OPENCLI_OUTPUT_MAX_CHARS:
        output = output[:OPENCLI_OUTPUT_MAX_CHARS] + "\n\n...[truncated]"
    return output


def _run_tool(tool_name: str, args: list[str], payload: dict, timeout: int = OPENCLI_TIMEOUT) -> str:
    try:
        return _run_opencli(args, timeout=timeout)
    except OpenCLIError as exc:
        message = str(exc)
        fallback = "Returned OpenCLI error summary to the model."
        record_tool_failure(tool_name, message, payload, fallback)
        return (
            f"OPENCLI_ERROR: {message}\n"
            "请不要用相同参数反复重试；可先调用 opencli_doctor 检查环境，"
            "或向用户说明 OpenCLI/Browser Bridge 当前不可用。"
        )


def _session_or_default(session: Optional[str]) -> str:
    return (session or OPENCLI_SESSION).strip() or "lcagent"


@tool
def opencli_doctor() -> str:
    """检查 OpenCLI 和 Browser Bridge 环境是否可用。任务开始前或出错时使用。"""
    return _run_tool("opencli_doctor", ["doctor"], {}, timeout=90)


@tool
def browser_open(url: str, session: Optional[str] = None) -> str:
    """用 OpenCLI 浏览器会话打开一个 URL。适合开始网页任务。"""
    s = _session_or_default(session)
    return _run_tool("browser_open", ["browser", s, "open", url], {"url": url, "session": s})


@tool
def browser_state(session: Optional[str] = None) -> str:
    """读取当前页面结构化 DOM 快照和可操作元素 refs。点击或输入前必须先调用。"""
    s = _session_or_default(session)
    return _run_tool("browser_state", ["browser", s, "state"], {"session": s})


@tool
def browser_click(target: str, session: Optional[str] = None) -> str:
    """点击页面元素。target 应优先使用 browser_state 返回的数字 ref，或明确选择器。"""
    s = _session_or_default(session)
    return _run_tool("browser_click", ["browser", s, "click", target], {"target": target, "session": s})


@tool
def browser_type(target: str, text: str, session: Optional[str] = None) -> str:
    """向输入框输入文本。target 应优先使用 browser_state 返回的数字 ref。"""
    s = _session_or_default(session)
    return _run_tool(
        "browser_type",
        ["browser", s, "type", target, text],
        {"target": target, "text": text, "session": s},
    )


@tool
def browser_extract(instruction: str = "", session: Optional[str] = None) -> str:
    """从当前页面抽取信息。instruction 用于说明抽取目标，实际抽取由 OpenCLI 完成。"""
    s = _session_or_default(session)
    return _run_tool(
        "browser_extract",
        ["browser", s, "extract"],
        {"instruction": instruction, "session": s},
    )


@tool
def browser_network(session: Optional[str] = None) -> str:
    """查看当前页面最近的网络请求/响应，适合分析接口、抓取 API 数据。"""
    s = _session_or_default(session)
    return _run_tool("browser_network", ["browser", s, "network"], {"session": s})


@tool
def browser_wait(condition: str, session: Optional[str] = None) -> str:
    """等待页面条件成立。支持 selector/text/time/xhr/download 前缀，否则按文本等待。"""
    s = _session_or_default(session)
    parts = condition.strip().split(maxsplit=1)
    wait_types = {"selector", "text", "time", "xhr", "download"}
    if parts and parts[0].lower() in wait_types:
        args = ["browser", s, "wait", parts[0].lower()]
        if len(parts) > 1:
            args.append(parts[1])
    else:
        args = ["browser", s, "wait", "text", condition]
    return _run_tool("browser_wait", args, {"condition": condition, "session": s})


OPENCLI_TOOLS = [
    opencli_doctor,
    browser_open,
    browser_state,
    browser_click,
    browser_type,
    browser_extract,
    browser_network,
    browser_wait,
]
