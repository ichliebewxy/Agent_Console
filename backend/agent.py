"""Agent construction, chat execution, and streaming."""
import asyncio
import json

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from agent_prompt import SYSTEM_PROMPT
from conversation_storage import ConversationStorage
from mcp_service import load_mcp_tools
from settings import CHAT_API_KEY, CHAT_BASE_URL, CHAT_MODEL
from tool_instrumentation import instrument_tools
from tools import (
    get_current_weather,
    get_last_rag_context,
    reset_tool_call_guards,
    search_knowledge_base,
    set_rag_step_queue,
    set_tool_step_queue,
)

agent = None
model = None
mcp_client = None
mcp_tool_count = 0
last_mcp_init_error = ""
storage = ConversationStorage()


def _create_chat_model(temperature: float = 0.3):
    return init_chat_model(
        model=CHAT_MODEL,
        model_provider="deepseek",
        api_key=CHAT_API_KEY,
        base_url=CHAT_BASE_URL,
        temperature=temperature,
        stream_usage=True,
    )


async def init_agent_async(record_init_failure: bool = True):
    global agent, model, mcp_client, mcp_tool_count, last_mcp_init_error
    print("正在初始化 DashScope MCP 地图工具...")
    model = _create_chat_model()
    mcp_result = await load_mcp_tools(record_init_failure=record_init_failure)
    mcp_client = mcp_result.client
    mcp_tool_count = mcp_result.tool_count
    last_mcp_init_error = mcp_result.error

    all_tools = instrument_tools([get_current_weather, search_knowledge_base] + mcp_result.tools)
    agent = create_agent(model=model, tools=all_tools, system_prompt=SYSTEM_PROMPT)
    if mcp_tool_count > 0:
        print(f"Agent 初始化完成，MCP 工具已加载 {mcp_tool_count} 个。")
    else:
        print("Agent 初始化完成，但 MCP 未加载到工具；已仅启用本地工具。")


async def retry_mcp_init_async() -> dict:
    await init_agent_async(record_init_failure=False)
    if mcp_tool_count <= 0:
        detail = f" 最近错误：{last_mcp_init_error}" if last_mcp_init_error else ""
        raise RuntimeError(
            "MCP 初始化仍未获取到可用工具，请检查 DASHSCOPE_MCP_API_KEY、网络或 MCP endpoint。"
            + detail
        )
    return {"mcp_tool_count": mcp_tool_count}


def summarize_old_messages(chat_model, messages: list) -> str:
    old_conversation = "\n".join(
        f"{'用户' if msg.type == 'human' else 'AI'}: {msg.content}"
        for msg in messages
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


def _persist_response(user_id: str, session_id: str, messages: list, response: str, rag_trace):
    messages.append(AIMessage(content=response))
    extra = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra)


def chat_with_agent(user_text: str, user_id: str = "default_user", session_id: str = "default_session"):
    if agent is None:
        raise RuntimeError("Agent 尚未初始化，请先调用并等待 init_agent_async() 完成。")
    messages = _prepare_messages(user_text, user_id, session_id)
    result = agent.invoke({"messages": messages}, config={"recursion_limit": 50})
    response = _extract_response(result)
    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None
    _persist_response(user_id, session_id, messages, response, rag_trace)
    return {"response": response, "rag_trace": rag_trace}


def _chunk_text(msg: AIMessageChunk) -> str:
    if getattr(msg, "tool_call_chunks", None):
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


async def chat_with_agent_stream(user_text: str, user_id: str = "default_user", session_id: str = "default_session"):
    if agent is None:
        raise RuntimeError("Agent 尚未初始化，请先调用并等待 init_agent_async() 完成。")
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
        try:
            async for msg, _metadata in agent.astream(
                {"messages": messages},
                stream_mode="messages",
                config={"recursion_limit": 50},
            ):
                if isinstance(msg, AIMessageChunk):
                    content = _chunk_text(msg)
                    if content:
                        full_response += content
                        await output_queue.put({"type": "content", "content": content})
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
    yield "data: [DONE]\n\n"
    _persist_response(user_id, session_id, messages, full_response, rag_trace)
