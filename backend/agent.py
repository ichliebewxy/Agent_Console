"""LangChain main-agent construction, chat execution, and streaming."""
import asyncio
import json

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from artifact_service import list_session_artifacts
from agent_prompt import SYSTEM_PROMPT
from conversation_storage import ConversationStorage
from core_tools import TOOLS
from runtime_context import bind_runtime_context, session_async_lock
from settings import AGENT_TOOL_CALL_LIMIT, CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL
from subagents import build_subagent_tools
from tool_instrumentation import instrument_tools
from tools import (
    get_last_rag_context,
    reset_tool_call_guards,
    set_rag_step_queue,
    set_tool_step_queue,
)


agent = None
model = None
storage = ConversationStorage()
_INIT_LOCK = asyncio.Lock()
_AGENT_RECURSION_LIMIT = AGENT_TOOL_CALL_LIMIT * 2 + 8


def _create_chat_model(temperature: float = 0.3):
    return init_chat_model(
        model=CHAT_MODEL,
        model_provider="deepseek",
        api_key=CHAT_API_KEY,
        base_url=CHAT_BASE_URL,
        temperature=temperature,
        stream_usage=True,
    )


async def init_agent_async():
    """Initialize the LangChain agent and its startup-discovered tool surface."""
    global agent, model
    async with _INIT_LOCK:
        model = _create_chat_model()
        from core_tools import REVIEW_TOOLS
        from mcp_service import get_discovered_mcp_tools
        from skill_service import SKILL_TOOLS
        from tools import search_knowledge_base

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


def _prepare_messages(user_text: str, user_id: str, session_id: str) -> list:
    messages = storage.load(user_id, session_id)
    get_last_rag_context(clear=True)
    reset_tool_call_guards()
    if len(messages) > 50:
        summary = summarize_old_messages(model, messages[:40])
        messages = [SystemMessage(content=f"之前的对话摘要：\n{summary}")] + messages[40:]
    messages.append(HumanMessage(content=user_text))
    return messages


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


def _persist_response(
    user_id: str,
    session_id: str,
    messages: list,
    response: str,
    rag_trace,
    artifacts: list,
):
    messages.append(AIMessage(content=response))
    extra = [None] * (len(messages) - 1) + [
        {"rag_trace": rag_trace, "artifacts": artifacts}
    ]
    storage.save(user_id, session_id, messages, extra_message_data=extra)


async def chat_with_agent(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
):
    if agent is None:
        raise RuntimeError("主 Agent 尚未初始化，请先等待 init_agent_async() 完成。")
    with bind_runtime_context(user_id, session_id):
        messages = _prepare_messages(user_text, user_id, session_id)
        result = await agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": _AGENT_RECURSION_LIMIT},
        )
        response = _extract_response(result)
        rag_context = get_last_rag_context(clear=True)
        rag_trace = rag_context.get("rag_trace") if rag_context else None
        async with session_async_lock(user_id, session_id):
            artifacts = await asyncio.to_thread(
                list_session_artifacts,
                user_id,
                session_id,
            )
            _persist_response(user_id, session_id, messages, response, rag_trace, artifacts)
        return {"response": response, "rag_trace": rag_trace, "artifacts": artifacts}


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
    messages = _prepare_messages(user_text, user_id, session_id)
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
                {"messages": messages},
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
    agent_task = asyncio.create_task(_agent_worker())
    try:
        while True:
            event = await output_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
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
        if not agent_task.done():
            agent_task.cancel()

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
        )
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
