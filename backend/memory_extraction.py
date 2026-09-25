"""Post-turn stop hook and independent extractMemories worker."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

import memory_service
from chat_models import build_chat_model
from settings import MEM0_DIR, MEM0_MODEL

MEMORY_TYPES = {"profile", "preference", "project", "feedback"}
EXTRACTION_DIR = MEM0_DIR / "extractions"
_jobs: dict[str, dict] = {}
_user_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _normalized(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)


def _same_fact(left: str, right: str) -> bool:
    a, b = _normalized(left), _normalized(right)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 12 and SequenceMatcher(None, a, b).ratio() >= 0.88)


def hasMemoryWritesSince(before: set[str], current: list[dict], fact: str) -> bool:
    """Filter facts written after this extraction began, including our own writes."""
    return any(
        str(item.get("id", "")) not in before
        and _same_fact(fact, item.get("memory", ""))
        for item in current
    )


def _parse_facts(content) -> list[dict]:
    text = content if isinstance(content, str) else str(content)
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    data = json.loads(text)
    facts = data.get("memories", []) if isinstance(data, dict) else []
    if not isinstance(facts, list):
        return []
    result = []
    for item in facts[:8]:
        if not isinstance(item, dict):
            continue
        category, fact = item.get("type"), item.get("memory")
        if category in MEMORY_TYPES and isinstance(fact, str) and fact.strip():
            result.append({"type": category, "memory": fact.strip()[:500]})
    return result


def _model_facts(user_message: str, conversation: list[dict], existing: list[dict]) -> list[dict]:
    context = [
        {"role": item.get("type"), "content": str(item.get("content", ""))[:3000]}
        for item in conversation[-12:]
        if item.get("type") in {"human", "ai"}
    ]
    known = [item.get("memory", "") for item in existing if item.get("memory")]
    prompt = (
        "你是独立的 extractMemories 代理。只从本轮最后一条用户消息中提取跨会话有价值的事实；"
        "历史和主 Agent 回复仅用于理解指代，不能作为事实来源。重点看用户反馈、纠正、个人信息。"
        "与现有记忆语义相同则跳过；临时任务、提问、助手推断、密码和令牌一律跳过。"
        "仅返回 JSON：{\"memories\":[{\"type\":\"profile|preference|project|feedback\",\"memory\":\"简明事实\"}]}。"
        "profile 是稳定身份或背景；preference 是持久偏好；project 是长期项目或目标；"
        "feedback 是对助手工作方式可复用的纠正。没有新增内容返回空数组。\n"
        + json.dumps(
            {"conversation": context, "current_user_message": user_message[:6000], "existing_memories": known[:150]},
            ensure_ascii=False,
        )
    )
    response = build_chat_model(MEM0_MODEL, temperature=0).invoke(prompt)
    return _parse_facts(response.content)


def _user_directory(user_id: str) -> Path:
    return EXTRACTION_DIR / hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def _write_file(user_id: str, session_id: str, memory_id: str, category: str, fact: str) -> None:
    directory = _user_directory(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid4().hex}.json"
    payload = {
        "id": memory_id,
        "type": category,
        "memory": fact,
        "user_id": user_id,
        "session_id": session_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def sync_extraction_file(memory_id: str, text: str | None = None) -> None:
    """Keep the per-memory file aligned with edits and deletions in mem0."""
    if not EXTRACTION_DIR.exists():
        return
    for path in EXTRACTION_DIR.glob("*/*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if str(payload.get("id")) != memory_id:
                continue
            if text is None:
                path.unlink()
            else:
                payload["memory"] = text
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(path)
        except (OSError, ValueError):
            continue


def clear_extraction_files(user_id: str) -> None:
    directory = _user_directory(user_id)
    if not directory.exists():
        return
    for path in directory.glob("*.json"):
        path.unlink()
    directory.rmdir()


def extractMemories(user_id: str, session_id: str, user_message: str, conversation: list[dict]) -> list[dict]:
    """Run outside the query loop using the main agent's saved turn record."""
    with _registry_lock:
        user_lock = _user_locks.setdefault(user_id, threading.Lock())
    with user_lock:
        existing = memory_service.get_all(user_id, top_k=1000)
        before = {str(item.get("id", "")) for item in existing}
        facts = _model_facts(user_message, conversation, existing)
        written = []
        for fact in facts:
            text = fact["memory"]
            current = memory_service.get_all(user_id, top_k=1000)
            if hasMemoryWritesSince(before, current, text) or any(
                _same_fact(text, item.get("memory", "")) for item in current
            ):
                continue
            if memory_service._SENSITIVE_MEMORY_RE.search(text):
                continue
            metadata = {"source": "extractMemories", "scope": "long_term", "type": fact["type"], "session_id": session_id}
            result = memory_service.add_memory(text, user_id, metadata=metadata, infer=False)
            for item in result.get("results", []):
                if item.get("event") == "ADD":
                    memory_id = str(item.get("id", ""))
                    _write_file(user_id, session_id, memory_id, fact["type"], text)
                    written.append({"id": memory_id, **fact})
                    break
        return written


def stopHook(user_id: str, session_id: str, user_message: str, conversation: list[dict]) -> str | None:
    """Called only after the final response is persisted and tool calls have ended."""
    if not memory_service.is_enabled():
        return None
    job_id = uuid4().hex
    _jobs[job_id] = {"user_id": user_id, "status": "running", "memories": []}

    async def _run():
        try:
            memories = await asyncio.to_thread(
                extractMemories, user_id, session_id, user_message, conversation
            )
            _jobs[job_id].update(status="completed", memories=memories)
        except Exception as exc:  # noqa: BLE001 - background failure must not break chat
            print(f"[memory] extractMemories failed: {exc}")
            _jobs[job_id].update(status="failed", memories=[])

    asyncio.create_task(_run())
    return job_id


def job_status(job_id: str, user_id: str) -> dict | None:
    job = _jobs.get(job_id)
    if not job or job["user_id"] != user_id:
        return None
    return {"status": job["status"], "memories": job["memories"]}
