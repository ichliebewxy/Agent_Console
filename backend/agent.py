"""LangChain main-agent construction, chat execution, and streaming."""
import asyncio
import json
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from agent_prompt import SYSTEM_PROMPT
from agent_state import (
    consume_tool_events,
    get_conversation_history,
    get_last_rag_context,
    reset_tool_call_guards,
)
from artifact_service import list_session_artifacts
from chat_models import build_chat_model
from conversation_storage import ConversationStorage
from core_tools import TOOLS
import memory_service
import plan_execute
from event_stream import set_rag_step_queue, set_tool_step_queue
from runtime_context import bind_runtime_context, session_async_lock
from settings import AGENT_TOOL_CALL_LIMIT, PLAN_EXECUTE_ENABLED
from subagents import build_subagent_tools
from tool_instrumentation import instrument_tools
from workflow_state import initial_workflow_state, plan_payload, public_workflow_state
from workflow_stream import stream_workflow_events
from checkpoint_service import get_run_state, get_workflow, register_run, workflow_config


agent = None
model = None
storage = ConversationStorage()
_INIT_LOCK = asyncio.Lock()
_AGENT_RECURSION_LIMIT = AGENT_TOOL_CALL_LIMIT * 2 + 8


def _create_chat_model(temperature: float = 0.3):
    return build_chat_model(temperature=temperature)


async def init_agent_async():
    """Initialize the LangChain agent and its startup-discovered tool surface."""
    global agent, model
    async with _INIT_LOCK:
        model = _create_chat_model()
        from core_tools import REVIEW_TOOLS
        from mcp_service import get_discovered_mcp_tools
        from skill_service import SKILL_TOOLS
        from search_tool import search_knowledge_base

        mcp_tools = get_discovered_mcp_tools()
        runtime_tools = [
            search_knowledge_base,
            *TOOLS,
            *REVIEW_TOOLS,
            *SKILL_TOOLS,
            *build_subagent_tools(model),
            *mcp_tools,
        ]
        agent = create_agent(
            model=model,
            tools=instrument_tools(runtime_tools),
            system_prompt=SYSTEM_PROMPT,
            name="main_agent",
        )
        print(
            "LangChain 主 Agent 初始化完成；固定工具：知识库、"
            "bash/read_file/write_file/edit_file/glob、review、Skills/Subagent；"
            f"启动发现 MCP({len(mcp_tools)})。"
        )


def summarize_old_messages(chat_model, messages: list) -> str:
    old_conversation = "\n".join(
        f"{'用户' if msg.type == 'human' else 'AI'}: {msg.content}" for msg in messages
    )
    prompt = f"请总结以下对话的关键信息：\n\n{old_conversation}\n总结："
    return chat_model.invoke(prompt).content


def _message_text(msg) -> str:
    """把任意 LangChain 消息的内容安全地压成纯文本。"""
    content = getattr(msg, "content", "")
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


def _serialize_history(messages: list) -> list[dict]:
    """把 LangChain 消息列表转成可持久化、可跨工作流节点传递的轻量历史。"""
    return [
        {"type": getattr(msg, "type", "system"), "content": _message_text(msg)}
        for msg in messages
    ]


def _messages_from_history(history: list | None) -> list:
    """把序列化的历史还原为 LangChain 消息列表。"""
    messages = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content", "")
        kind = item.get("type", "ai")
        if kind == "human":
            messages.append(HumanMessage(content=content))
        elif kind == "system":
            messages.append(SystemMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages


def _prepare_messages(user_text: str, user_id: str, session_id: str):
    """加载历史并返回 (完整消息序列, 本轮之前的历史)。

    完整消息序列末尾追加当前用户输入，用于简单问答直接回答。历史单独返回，
    便于序列化后随工作流状态传给规划器与步骤执行器，避免多轮上下文丢失。
    """
    history = storage.load(user_id, session_id)
    get_last_rag_context(clear=True)
    reset_tool_call_guards()
    if len(history) > 50:
        summary = summarize_old_messages(model, history[:40])
        history = [SystemMessage(content=f"之前的对话摘要：\n{summary}")] + history[40:]
    messages = [*history, HumanMessage(content=user_text)]
    return messages, history


def _format_memory_context(memories: list) -> str:
    bullets = "\n".join(f"- {m}" for m in memories)
    return (
        "以下是当前用户相关的长期记忆（若与本轮问题无关可忽略）：\n"
        f"{bullets}"
    )


async def _augment_with_memory(user_text: str, user_id: str, messages: list) -> list:
    """把与当前问题相关的长期记忆注入为一条 system 消息。任何失败都不阻断对话。"""
    if not memory_service.is_enabled():
        return messages
    try:
        memories = await asyncio.to_thread(
            memory_service.search_for_context, user_text, user_id
        )
    except Exception as exc:
        print(f"[memory] 检索长期记忆失败，已跳过注入: {exc}")
        return messages
    if not memories:
        return messages
    return [SystemMessage(content=_format_memory_context(memories)), *messages]


def _schedule_remember(user_id: str, user_message: str, session_id: str) -> None:
    """仅将有跨会话价值的信息异步写入长期记忆。"""
    if (
        not memory_service.is_enabled()
        or not memory_service.is_long_term_memory_candidate(user_message)
    ):
        return

    async def _run():
        try:
            await asyncio.to_thread(
                memory_service.remember_conversation,
                user_id,
                user_message,
                session_id,
            )
        except Exception as exc:
            print(f"[memory] 写入长期记忆失败: {exc}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        pass


def _extract_response(result) -> str:
    if isinstance(result, dict):
        if "output" in result:
            return result["output"]
        if result.get("messages"):
            msg = result["messages"][-1]
            return getattr(msg, "content", str(msg))
    if hasattr(result, "content"):
        return result.content
    return str(result)

def _sse_event(event: dict) -> str:
    newline = chr(10)
    return "data: " + json.dumps(event, ensure_ascii=False) + newline + newline


class _RagStepQueueProxy:
    def __init__(self, queue):
        self._queue = queue

    def put_nowait(self, step):
        self._queue.put_nowait({"type": "rag_step", "step": step})


class _ToolStepQueueProxy:
    def __init__(self, queue):
        self._queue = queue

    def put_nowait(self, step):
        self._queue.put_nowait({"type": "tool_step", "step": step})


def _should_plan_execute(user_text: str) -> bool:
    if not PLAN_EXECUTE_ENABLED:
        return False
    return plan_execute.is_multi_step_task(user_text)


async def execute_workflow_step(instruction: str) -> dict:
    """Execute one graph step and return serializable evidence for validation."""
    reset_tool_call_guards()
    get_last_rag_context(clear=True)
    # 步骤执行必须携带本轮之前的会话历史，否则多轮任务会丢失起点、目的地等
    # 已在上文中确认的信息（该历史由 workflow_graph 在调用前注入 ContextVar）。
    messages = _messages_from_history(get_conversation_history())
    messages.append(HumanMessage(content=instruction))
    result = await agent.ainvoke(
        {"messages": messages},
        config={"recursion_limit": _AGENT_RECURSION_LIMIT},
    )
    rag_context = get_last_rag_context(clear=True)
    return {
        "response": _extract_response(result),
        "tool_events": consume_tool_events(),
        "rag_trace": rag_context.get("rag_trace") if rag_context else None,
    }


def _persist_response(
    user_id: str,
    session_id: str,
    messages: list,
    response: str,
    rag_trace,
    artifacts: list,
    plan: dict | None = None,
    workflow: dict | None = None,
):
    messages.append(AIMessage(content=response))
    metadata = {"rag_trace": rag_trace, "artifacts": artifacts}
    if plan is not None:
        metadata["plan"] = plan
    if workflow is not None:
        metadata["workflow"] = workflow
    extra = [None] * (len(messages) - 1) + [metadata]
    storage.save(user_id, session_id, messages, extra_message_data=extra)


async def chat_with_agent(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
):
    if agent is None:
        raise RuntimeError("主 Agent 尚未初始化，请先等待 init_agent_async() 完成。")
    with bind_runtime_context(user_id, session_id):
        messages, history = _prepare_messages(user_text, user_id, session_id)
        # 记忆只注入本轮调用，不随 messages 一起持久化，避免逐轮累积脏上下文。
        invoke_messages = await _augment_with_memory(user_text, user_id, messages)

        workflow_data = None
        plan_data = None
        if _should_plan_execute(user_text):
            run_id = str(uuid4())
            initial = initial_workflow_state(
                run_id,
                user_id,
                session_id,
                user_text,
                history=_serialize_history(history),
            )
            # Step staging protects individual mutations. Serializing full
            # workflow runs per session also protects the shared visible
            # workspace when two browser tabs submit tasks at once.
            async with session_async_lock(user_id, session_id):
                await register_run(initial)
                await get_workflow().ainvoke(
                    initial,
                    workflow_config(run_id),
                    durability="sync",
                )
            workflow_data = await get_run_state(run_id)
            plan_data = {
                "objective": workflow_data.get("objective", ""),
                "steps": workflow_data.get("steps", []),
                "reflections": [],
            }
            response = workflow_data.get("final_response", "")
            rag_trace = workflow_data.get("rag_trace")
        else:
            output_queue = asyncio.Queue()
            set_rag_step_queue(_RagStepQueueProxy(output_queue))
            set_tool_step_queue(_ToolStepQueueProxy(output_queue))
            try:
                result = await agent.ainvoke(
                    {"messages": invoke_messages},
                    config={"recursion_limit": _AGENT_RECURSION_LIMIT},
                )
                response = _extract_response(result)
            finally:
                set_rag_step_queue(None)
                set_tool_step_queue(None)
            rag_context = get_last_rag_context(clear=True)
            rag_trace = rag_context.get("rag_trace") if rag_context else None
        async with session_async_lock(user_id, session_id):
            artifacts = await asyncio.to_thread(
                list_session_artifacts,
                user_id,
                session_id,
            )
            _persist_response(
                user_id,
                session_id,
                messages,
                response,
                rag_trace,
                artifacts,
                plan=plan_data,
                workflow=workflow_data,
            )
        _schedule_remember(user_id, user_text, session_id)
        return {
            "response": response,
            "rag_trace": rag_trace,
            "artifacts": artifacts,
            "plan": plan_data,
            "workflow": workflow_data,
        }


def _chunk_text(msg: AIMessageChunk) -> str:
    if getattr(msg, "tool_call_chunks", None) and not msg.content:
        return ""
    if isinstance(msg.content, str):
        return msg.content
    if not isinstance(msg.content, list):
        return ""
    text = ""
    for block in msg.content:
        if isinstance(block, str):
            text += block
        elif isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    return text


def _message_stream_id(msg: AIMessageChunk, metadata: dict) -> str | None:
    """Return a stable id for one streamed model message, when available."""
    message_id = getattr(msg, "id", None)
    if message_id:
        return str(message_id)
    graph_step = (metadata or {}).get("langgraph_step")
    return f"graph-step:{graph_step}" if graph_step is not None else None


async def _chat_with_agent_stream_bound(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
):
    if agent is None:
        raise RuntimeError("主 Agent 尚未初始化，请先等待 init_agent_async() 完成。")
    messages, history = _prepare_messages(user_text, user_id, session_id)
    # 记忆只注入本轮调用，不随 messages 一起持久化。
    invoke_messages = await _augment_with_memory(user_text, user_id, messages)

    use_workflow = _should_plan_execute(user_text)
    workflow_data = None
    plan_data = None
    workflow_run_id = str(uuid4()) if use_workflow else None

    output_queue = asyncio.Queue()
    full_response = ""

    class _RagStepProxy:
        def put_nowait(self, step):
            output_queue.put_nowait({"type": "rag_step", "step": step})

    class _ToolStepProxy:
        def put_nowait(self, step):
            output_queue.put_nowait({"type": "tool_step", "step": step})

    async def _agent_worker():
        nonlocal full_response
        active_message_id = None
        try:
            async for msg, metadata in agent.astream(
                {"messages": invoke_messages},
                stream_mode="messages",
                config={"recursion_limit": _AGENT_RECURSION_LIMIT},
            ):
                # Nested specialist model output is implementation detail. Only
                # stream the supervisor's final model node to the user.
                if metadata.get("langgraph_node") != "model":
                    continue
                if isinstance(msg, AIMessageChunk):
                    content = _chunk_text(msg)
                    if content:
                        message_id = _message_stream_id(msg, metadata)
                        if (
                            active_message_id
                            and message_id
                            and message_id != active_message_id
                        ):
                            full_response += "\n\n"
                            await output_queue.put({"type": "content_boundary"})
                        active_message_id = message_id or active_message_id
                        full_response += content
                        await output_queue.put(
                            {
                                "type": "content",
                                "content": content,
                                "message_id": message_id,
                            }
                        )
        except Exception as exc:
            await output_queue.put({"type": "error", "content": str(exc)})
        finally:
            await output_queue.put(None)

    set_rag_step_queue(_RagStepProxy())
    set_tool_step_queue(_ToolStepProxy())

    agent_task = None
    try:
        if use_workflow:
            initial = initial_workflow_state(
                workflow_run_id,
                user_id,
                session_id,
                user_text,
                history=_serialize_history(history),
            )
            async with session_async_lock(user_id, session_id):
                async for event in stream_workflow_events(initial):
                    if event.get("type") == "content":
                        full_response += event.get("content", "")
                    yield _sse_event(event)
            workflow_data = await get_run_state(workflow_run_id)
            plan_data = {
                "objective": workflow_data.get("objective", ""),
                "steps": workflow_data.get("steps", []),
                "reflections": [],
            }
            full_response = workflow_data.get("final_response", "") or full_response
        else:
            agent_task = asyncio.create_task(_agent_worker())
            try:
                while True:
                    event = await output_queue.get()
                    if event is None:
                        break
                    yield _sse_event(event)
            except GeneratorExit:
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
                raise
    finally:
        set_rag_step_queue(None)
        set_tool_step_queue(None)
        if agent_task is not None and not agent_task.done():
            agent_task.cancel()

    if workflow_data is not None:
        rag_trace = workflow_data.get("rag_trace")
    else:
        rag_context = get_last_rag_context(clear=True)
        rag_trace = rag_context.get("rag_trace") if rag_context else None
    if rag_trace:
        payload = json.dumps({"type": "trace", "rag_trace": rag_trace}, ensure_ascii=False)
        yield f"data: {payload}\n\n"
    async with session_async_lock(user_id, session_id):
        artifacts = await asyncio.to_thread(
            list_session_artifacts,
            user_id,
            session_id,
        )
        _persist_response(
            user_id,
            session_id,
            messages,
            full_response,
            rag_trace,
            artifacts,
            plan=plan_data,
            workflow=workflow_data,
        )
    _schedule_remember(user_id, user_text, session_id)
    artifact_payload = json.dumps(
        {"type": "artifacts", "artifacts": artifacts},
        ensure_ascii=False,
    )
    yield f"data: {artifact_payload}\n\n"
    yield "data: [DONE]\n\n"


async def chat_with_agent_stream(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
):
    with bind_runtime_context(user_id, session_id):
        async for event in _chat_with_agent_stream_bound(user_text, user_id, session_id):
            yield event
