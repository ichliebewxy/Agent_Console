"""Resolve turn-local Skill and Memory context without persisting it in chat history."""

import asyncio

import memory_service
from context_builder import with_memory_context, with_skill_catalog
from memory_scope import resolve_memory_access
from session_resources import SESSION_RESOURCES
from skill_resolver import resolve_skill_names
from skill_service import SKILL_REGISTRY
from langchain_core.messages import SystemMessage
from runtime_context import active_workspace_dir, current_runtime_context, workspace_directory


def build_workspace_context(user_id: str, session_id: str) -> SystemMessage:
    resources = SESSION_RESOURCES.get(user_id, session_id)
    try:
        context = current_runtime_context()
    except RuntimeError:
        context = None
    workspace = active_workspace_dir() if context and (context.user_id, context.session_id) == (user_id, session_id) else workspace_directory(user_id, session_id)
    return SystemMessage(content=(
        f"当前工作目录（bash 的 cwd、相对文件路径的基准）：{workspace}\n"
        f"运行方式：{'已选择本地文件夹，修改直接作用于该目录' if resources.workspace_dir else '未选择文件夹，使用独立会话目录'}。\n"
        f"文件与命令权限：{resources.permission_mode}。"
        "relaxed 允许访问绝对路径和父目录、执行常规本地命令及 shell 组合命令；"
        "restricted 限制在工作目录内且使用命令白名单。"
        "系统破坏类命令仍受限制，外部写操作仍须符合用户请求。\n"
        f"需要交付下载的文件保存到：{workspace / 'deliverables'}。"
    ))


async def build_resource_context(messages: list, query: str, user_id: str, session_id: str) -> list:
    catalog = SKILL_REGISTRY.catalog(names=resolve_skill_names(SKILL_REGISTRY.names, user_id, session_id))
    result = with_skill_catalog(messages, catalog)
    resources = SESSION_RESOURCES.get(user_id, session_id)
    result = [build_workspace_context(user_id, session_id), *result]
    if not memory_service.is_enabled():
        return result
    try:
        access = resolve_memory_access(user_id, session_id, resources)
        memories = await asyncio.to_thread(memory_service.search_scoped_context, query, access)
    except Exception as exc:  # noqa: BLE001 - memory outage must not block chat
        print(f"[memory] 检索当前会话记忆失败，已跳过注入: {exc}")
        return result
    return with_memory_context(result, memories)
