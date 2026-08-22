"""Plan-and-Execute plus reflection for the main Agent.

This module keeps the LLM plumbing for decomposing a user task into ordered
sub-tasks and for reflecting on progress after each sub-task.  The orchestration
itself (which reuses the existing main Agent for actual execution) lives in
agent.py so the streaming/SSE and tool-event plumbing stays in one place.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from chat_models import build_chat_model
from settings import PLAN_EXECUTE_MAX_STEPS, PLAN_EXECUTE_RESULT_MAX_CHARS

_NL = chr(10)
_CR = chr(13)
_MARKDOWN_FENCE = chr(96) * 3


# --------------------------------------------------------------------------- #
# Heuristic gate: decide without an LLM call whether a turn looks like a
# multi-step task.  Simple questions and greetings keep the cheap single run.
# --------------------------------------------------------------------------- #

_TASK_WORDS = (
    "帮我", "请", "编写", "写一个", "开发", "实现", "制作", "创建", "生成", "构建",
    "搭建", "安装", "配置", "部署", "分析", "对比", "调研", "整理", "汇总", "总结",
    "提炼", "修复", "优化", "重构", "测试", "验证", "调试", "下载", "爬取", "抓取",
    "采集", "转换", "导出", "导入", "翻译", "设计", "拆分", "分步", "步骤", "依次",
    "逐个", "build", "create", "write", "implement", "develop", "make", "install",
    "deploy", "analyze", "compare", "research", "summarize", "fix", "test",
    "download", "scrape", "crawl", "convert", "export", "design",
)

_CONNECTORS = (
    "然后", "接着", "之后", "最后", "再", "并且", "同时", "以及", "还有", "先",
    "第一步", "then", "and then", "first", "finally", "also", "next",
)

_EXPLICIT_PLAN_MARKERS = ("分步", "一步步", "逐个完成", "step by step", "plan")


def is_multi_step_task(text: str) -> bool:
    """Cheap, deterministic check for whether a turn warrants plan-and-execute."""
    t = (text or "").strip()
    if not t:
        return False
    # Explicit "do it step by step" requests always override the length gate.
    if any(m in t for m in _EXPLICIT_PLAN_MARKERS):
        return True
    if len(t) < 20:
        return False

    separators = "。！？!?;；" + _NL + _CR
    sentences = [
        s for s in re.split("[" + re.escape(separators) + "]+", t) if s.strip()
    ]
    sentence_count = len(sentences) or 1

    kw_count = sum(1 for w in _TASK_WORDS if w in t)
    connector_count = sum(1 for c in _CONNECTORS if c in t)
    is_question = t.rstrip().endswith(("？", "?", "吗", "呢"))

    if is_question and sentence_count <= 1 and kw_count <= 1:
        return False
    if kw_count >= 3:
        return True
    if connector_count >= 2 and kw_count >= 1:
        return True
    if sentence_count >= 2 and kw_count >= 1 and len(t) >= 50:
        return True
    return False


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class PlanStep:
    id: str
    title: str
    detail: str = ""
    status: str = "pending"  # pending | in_progress | done | failed | skipped
    result: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "result": self.result,
        }


@dataclass
class Plan:
    objective: str
    steps: list

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class Reflection:
    decision: str = "continue"  # continue | complete | stop
    adjustments: list = field(default_factory=list)
    reason: str = ""


# --------------------------------------------------------------------------- #
# LLM helpers
# --------------------------------------------------------------------------- #

_PLANNER = None
_REFLECTOR = None


def _get_planner():
    global _PLANNER
    if _PLANNER is None:
        _PLANNER = build_chat_model(temperature=0.2)
    return _PLANNER


def _get_reflector():
    global _REFLECTOR
    if _REFLECTOR is None:
        _REFLECTOR = build_chat_model(temperature=0.0)
    return _REFLECTOR


def _call_model(model, prompt: str) -> str:
    message = model.invoke(prompt)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")


def _extract_json_object(text: str):
    """Parse the first JSON object/array found in free-form model output."""
    if not text:
        return {}
    cleaned = text.strip()
    cleaned = cleaned.replace(_MARKDOWN_FENCE + "json", "").replace(_MARKDOWN_FENCE, "")
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        return {}
    start = min(starts)
    for end in range(len(cleaned), start, -1):
        candidate = cleaned[start:end]
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return {}


def _normalize_decision(value: str) -> str:
    if value in {"done", "finish", "finished", "end", "success", "succeed"}:
        return "complete"
    if value in {"blocked", "block", "halt", "fail", "failed", "abort"}:
        return "stop"
    return "continue"


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

_PLAN_PROMPT = """你是任务规划器。把用户任务拆解为按顺序执行的子任务，让后续执行者能一步步完成。

要求：
1. 使用与用户任务相同的语言（中文任务则输出中文）。
2. 子任务要具体、可执行、边界清晰、彼此不重叠，且完整覆盖用户需求。
3. 每个子任务尽量小；最多 {max_steps} 个，能少则少。
4. 只输出一个 JSON 对象，不要输出任何其它文字或 Markdown 代码块。

JSON 格式：
{{"objective": "一句话总体目标", "steps": [{{"title": "子任务标题", "detail": "本子任务要做什么，以及完成/验收标准"}}]}}

用户任务：
{task}
"""


_REFLECT_PROMPT = """你是任务执行的反省器。根据总体目标、当前计划、以及刚刚完成的子任务的实际结果，判断下面应该做什么，并在必要时调整后续计划。

只输出一个 JSON 对象，不要输出其它文字。

字段说明：
- decision: "continue"（还有子任务要做，继续）| "complete"（目标已达成，可结束）| "stop"（遇到无法解决的阻塞/失败，应停止）。
- adjustments: 需要对"尚未执行"的子任务做的调整，没有则填 []。每个元素为 {{"action": "add"|"modify"|"remove", "target_index": 目标子任务的1开始序号（modify/remove 需要；add 可省略）, "title": "标题", "detail": "说明"}}。
- reason: 一句话说明判断依据（可引用刚刚的结果或发现的问题）。

规则：
- 不要修改已经完成的子任务。
- 仅当新证据表明原计划需要增删改时，才在 adjustments 给出调整。
- 若刚完成的子任务暴露出新的必要步骤，用 add 追加。
- 若某个未执行子任务已不再必要，用 remove 删除；需要改写时用 modify。

总体目标：
{objective}

当前计划（含状态）：
{plan}

刚刚完成的子任务结果：
{last_result}
"""


# --------------------------------------------------------------------------- #
# Plan generation / reflection
# --------------------------------------------------------------------------- #


async def generate_plan(task: str, max_steps: int | None = None) -> Plan:
    """Ask the planner model once to split the task into ordered sub-tasks."""
    limit = max_steps or PLAN_EXECUTE_MAX_STEPS
    planner = _get_planner()
    prompt = _PLAN_PROMPT.format(task=task, max_steps=limit)
    raw = await asyncio.to_thread(_call_model, planner, prompt)
    data = _extract_json_object(raw)

    if isinstance(data, list):
        objective = task
        items = data
    elif isinstance(data, dict):
        objective = str(data.get("objective") or data.get("goal") or "").strip() or task
        steps_raw = data.get("steps")
        if isinstance(steps_raw, list):
            items = steps_raw
        elif isinstance(steps_raw, dict):
            items = steps_raw.get("steps") or []
        elif data.get("title") or data.get("detail"):
            items = [data]
        else:
            items = []
    else:
        items = []

    steps: list[PlanStep] = []
    for i, item in enumerate(items[:limit], start=1):
        if isinstance(item, str):
            title, detail = item.strip(), ""
        elif isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "").strip()
            detail = str(
                item.get("detail") or item.get("description") or item.get("do") or ""
            ).strip()
        else:
            continue
        if not title:
            continue
        steps.append(PlanStep(id="s" + str(i), title=title, detail=detail))

    if not steps:
        steps = [PlanStep(id="s1", title="完成用户任务", detail=task)]
    return Plan(objective=objective, steps=steps)


async def reflect(plan: Plan, last_result: str) -> Reflection:
    """Ask the reflector to decide next action and possibly adjust the plan."""
    reflector = _get_reflector()
    plan_payload = json.dumps(plan.to_dict(), ensure_ascii=False)
    prompt = _REFLECT_PROMPT.format(
        objective=plan.objective,
        plan=plan_payload,
        last_result=(last_result or "")[:PLAN_EXECUTE_RESULT_MAX_CHARS],
    )
    raw = await asyncio.to_thread(_call_model, reflector, prompt)
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        data = {}

    decision = str(data.get("decision") or "continue").strip().lower()
    if decision not in {"continue", "complete", "stop"}:
        decision = _normalize_decision(decision)

    adjustments = data.get("adjustments") or []
    if isinstance(adjustments, dict):
        adjustments = [adjustments]
    if not isinstance(adjustments, list):
        adjustments = []

    reason = str(data.get("reason") or "").strip()
    return Reflection(decision=decision, adjustments=adjustments, reason=reason)


# --------------------------------------------------------------------------- #
# Plan mutation + instruction rendering
# --------------------------------------------------------------------------- #


def _resolve_pending_index(plan: Plan, target, title: str):
    if isinstance(target, int) and not isinstance(target, bool):
        if 1 <= target <= len(plan.steps) and plan.steps[target - 1].status in {
            "pending",
            "in_progress",
        }:
            return target - 1
        return None
    if isinstance(target, str) and target.isdigit():
        n = int(target)
        if 1 <= n <= len(plan.steps) and plan.steps[n - 1].status in {
            "pending",
            "in_progress",
        }:
            return n - 1
        return None
    hay = title or str(target or "")
    if hay:
        for idx, s in enumerate(plan.steps):
            if s.status in {"pending", "in_progress"} and (
                hay in s.title or s.title in hay
            ):
                return idx
    return None


def apply_reflection(plan: Plan, reflection: Reflection) -> list:
    """Mutate only still-pending steps and report human-readable change notes."""
    notes: list = []
    for adj in reflection.adjustments or []:
        if not isinstance(adj, dict):
            continue
        action = str(adj.get("action") or "").strip().lower()
        title = str(adj.get("title") or "").strip()
        detail = str(adj.get("detail") or adj.get("description") or "").strip()
        target = adj.get("target_index", adj.get("index", adj.get("step_id")))

        if action == "add":
            new_step = PlanStep(
                id="s" + str(len(plan.steps) + 1),
                title=title or "新增步骤",
                detail=detail,
            )
            plan.steps.append(new_step)
            notes.append("新增子任务：" + new_step.title)
            continue

        idx = _resolve_pending_index(plan, target, title)
        if idx is None:
            continue
        step = plan.steps[idx]
        if action in {"modify", "update", "change"}:
            if title:
                step.title = title
            if detail:
                step.detail = detail
            notes.append("调整子任务：" + step.title)
        elif action in {"remove", "delete", "drop"}:
            plan.steps.pop(idx)
            notes.append("移除子任务：" + step.title)
    return notes


def prior_results_text(plan: Plan, limit: int = 1200) -> str:
    parts = []
    for s in plan.steps:
        if s.status == "done" and s.result:
            parts.append("【" + s.title + "】" + _NL + (s.result or "").strip()[:limit])
    return (_NL + _NL).join(parts) if parts else "（暂无已完成步骤）"


def build_step_instruction(plan: Plan, step: PlanStep, index: int, total: int) -> str:
    return f"""【总体目标】
{plan.objective}

【当前子任务】(第 {index}/{total} 步)
标题：{step.title}
要求：{step.detail or "（无额外说明）"}

【已完成步骤的结果】(仅供参考，不要重复执行)
{prior_results_text(plan)}

请只完成“当前子任务”，完成后用简洁的文字报告：做了什么、结果如何、是否遇到阻碍。需要调用工具/检索时，按系统提示正常使用。"""
