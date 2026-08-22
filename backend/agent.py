"""LangChain main-agent construction, chat execution, and streaming."""
import asyncio
import json

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from agent_prompt import SYSTEM_PROMPT
from agent_state import get_last_rag_context, reset_tool_call_guards
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


def _prepare_messages(user_text: str, user_id: str, session_id: str) -> list:
    messages = storage.load(user_id, session_id)
    get_last_rag_context(clear=True)
    reset_tool_call_guards()
    if len(messages) > 50:
        summary = summarize_old_messages(model, messages[:40])
        messages = [SystemMessage(content=f"之前的对话摘要：\n{summary}")] + messages[40:]
    messages.append(HumanMessage(content=user_text))
    return messages


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


def _schedule_remember(user_id: str, user_message: str, assistant_message: str, session_id: str) -> None:
    """后台异步把一轮对话蒸馏并写入长期记忆，不阻塞响应返回。"""
    if not memory_service.is_enabled():
        return

    async def _run():
        try:
            await asyncio.to_thread(
                memory_service.remember_conversation,
                user_id,
                user_message,
                assistant_message,
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


def _drain_output_queue(queue: asyncio.Queue) -> list:
    drained = []
    while True:
        try:
            drained.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return drained


async def _execute_plan_step(instruction: str) -> str:
    reset_tool_call_guards()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=instruction)]},
        config={"recursion_limit": _AGENT_RECURSION_LIMIT},
    )
    return _extract_response(result)


async def _plan_execute_stream_events(user_text: str, plan, output_queue: asyncio.Queue):
    "Yield plan / execute / reflect / content events for one plan-and-execute turn."
    from settings import PLAN_EXECUTE_MAX_STEPS

    def _plan_event():
        steps = []
        for s in plan.steps:
            item = s.to_dict()
            if item.get("result"):
                item["result"] = item["result"][:200]
            steps.append(item)
        return {"type": "plan", "objective": plan.objective, "steps": steps}

    yield _plan_event()
    yield {
        "type": "plan_step",
        "step": {
            "icon": "📋",
            "phase": "plan",
            "label": "规划完成：拆分为 " + str(len(plan.steps)) + " 个子任务",
            "detail": plan.objective,
        },
    }

    newline = chr(10)
    index = 0
    executed = 0
    max_steps = PLAN_EXECUTE_MAX_STEPS
    while index < len(plan.steps) and executed < max_steps:
        step = plan.steps[index]
        if step.status != "pending":
            index += 1
            continue
        step.status = "in_progress"
        yield {
            "type": "plan_step",
            "step": {
                "icon": "▶",
                "phase": "execute",
                "label": "执行 " + str(index + 1) + "/" + str(len(plan.steps)) + "：" + step.title,
                "detail": step.detail or "",
            },
        }
        yield {
            "type": "execute",
            "step_id": step.id,
            "status": "in_progress",
            "title": step.title,
            "index": index,
            "total": len(plan.steps),
        }

        instruction = plan_execute.build_step_instruction(
            plan, step, index + 1, len(plan.steps)
        )
        try:
            result = await _execute_plan_step(instruction)
            step.status = "done"
        except Exception as exc:
            result = "（执行出错：" + str(exc) + "）"
            step.status = "failed"
        step.result = result
        executed += 1

        for event in _drain_output_queue(output_queue):
            yield event

        if index > 0:
            yield {"type": "content_boundary"}
        header = "### 步骤 " + str(index + 1) + "：" + step.title + newline
        yield {"type": "content", "content": header + str(result or "") + newline}
        yield {
            "type": "execute",
            "step_id": step.id,
            "status": step.status,
            "title": step.title,
            "index": index,
            "total": len(plan.steps),
            "result": str(result or "")[:200],
        }

        yield {
            "type": "plan_step",
            "step": {"icon": "🔄", "phase": "reflect", "label": "反省与计划调整", "detail": ""},
        }
        reflection = None
        try:
            reflection = await plan_execute.reflect(plan, step.result or "")
        except Exception as exc:
            print("[plan] 反省失败，按原计划继续: " + str(exc))
        if reflection is not None:
            notes = plan_execute.apply_reflection(plan, reflection)
            yield {
                "type": "reflect",
                "decision": reflection.decision,
                "reason": reflection.reason,
                "adjusted": bool(notes),
            }
            if notes:
                yield _plan_event()
            if reflection.decision == "complete":
                break
            if reflection.decision == "stop":
                break

        index += 1

    yield {
        "type": "plan_step",
        "step": {"icon": "✅", "phase": "complete", "label": "计划执行结束", "detail": ""},
    }
    yield _plan_event()


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
        messages = await _augment_with_memory(user_text, user_id, messages)

        output_queue = asyncio.Queue()
        plan = None
        if _should_plan_execute(user_text):
            try:
                plan = await plan_execute.generate_plan(user_text)
            except Exception as exc:
                print("[plan] 规划失败，退回到直接执行: " + str(exc))
                plan = None

        set_rag_step_queue(_RagStepQueueProxy(output_queue))
        set_tool_step_queue(_ToolStepQueueProxy(output_queue))
        try:
            if plan is not None and getattr(plan, "steps", None):
                response = ""
                async for event in _plan_execute_stream_events(user_text, plan, output_queue):
                    if event.get("type") == "content":
                        response += event.get("content", "")
            else:
                result = await agent.ainvoke(
                    {"messages": messages},
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
            _persist_response(user_id, session_id, messages, response, rag_trace, artifacts)
        _schedule_remember(user_id, user_text, response, session_id)
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
    messages = await _augment_with_memory(user_text, user_id, messages)

    plan = None
    if _should_plan_execute(user_text):
        yield _sse_event(
            {
                "type": "plan_step",
                "step": {"icon": "🧭", "phase": "plan", "label": "正在规划任务拆解", "detail": ""},
            }
        )
        try:
            plan = await plan_execute.generate_plan(user_text)
        except Exception as exc:
            print("[plan] 规划失败，退回到直接执行: " + str(exc))
            yield _sse_event(
                {
                    "type": "plan_step",
                    "step": {"icon": "↩", "phase": "plan", "label": "规划未成功，改为直接执行", "detail": str(exc)[:200]},
                }
            )
            plan = None

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

    agent_task = None
    try:
        if plan is not None and getattr(plan, "steps", None):
            async for event in _plan_execute_stream_events(user_text, plan, output_queue):
                if event.get("type") == "content":
                    full_response += event.get("content", "")
                yield _sse_event(event)
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
    _schedule_remember(user_id, user_text, full_response, session_id)
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
