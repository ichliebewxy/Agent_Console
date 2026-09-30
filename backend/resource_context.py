"""Resolve turn-local Skill and Memory context without persisting it in chat history."""

import asyncio

import memory_service
from context_builder import with_memory_context, with_skill_catalog
from memory_scope import resolve_memory_access
from session_resources import SESSION_RESOURCES
from skill_resolver import resolve_skill_names
from skill_service import SKILL_REGISTRY


async def build_resource_context(messages: list, query: str, user_id: str, session_id: str) -> list:
    catalog = SKILL_REGISTRY.catalog(names=resolve_skill_names(SKILL_REGISTRY.names, user_id, session_id))
    result = with_skill_catalog(messages, catalog)
    if not memory_service.is_enabled():
        return result
    try:
        resources = SESSION_RESOURCES.get(user_id, session_id)
        access = resolve_memory_access(user_id, session_id, resources)
        memories = await asyncio.to_thread(memory_service.search_scoped_context, query, access)
    except Exception as exc:  # noqa: BLE001 - memory outage must not block chat
        print(f"[memory] 检索当前会话记忆失败，已跳过注入: {exc}")
        return result
    return with_memory_context(result, memories)
