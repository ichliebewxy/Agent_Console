import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
import routes_sessions
from agent_state import (
    begin_rag_trace_capture,
    get_last_rag_context,
    merge_rag_traces,
    reset_tool_call_guards,
)
from conversation_storage import ConversationStorage
from langchain_core.messages import AIMessage, AIMessageChunk
from search_tool import search_knowledge_base
from tool_instrumentation import instrument_tool


class RagTraceCaptureTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _rag_result(query):
        return {
            "docs": [{"filename": "manual.txt", "page_number": 1, "text": "answer"}],
            "rag_trace": {
                "tool_used": True,
                "tool_name": "search_knowledge_base",
                "query": query,
                "retrieval_stage": "complete",
            },
        }

    async def test_instrumented_sync_tool_returns_trace_across_worker_thread(self):
        begin_rag_trace_capture()
        reset_tool_call_guards()
        tool = instrument_tool(search_knowledge_base)
        with patch("rag_pipeline.run_rag_graph", side_effect=self._rag_result):
            answer = await tool.ainvoke({"query": "cross-thread"})
        context = get_last_rag_context()
        self.assertIn("manual.txt", answer)
        self.assertEqual(context["rag_trace"]["query"], "cross-thread")
        self.assertEqual(len(context["rag_trace"]["tool_call_id"]), 32)

    async def test_trace_reaches_normal_chat_stream_and_restored_history(self):
        tool = instrument_tool(search_knowledge_base)

        class FakeAgent:
            async def ainvoke(self, *_args, **_kwargs):
                await tool.ainvoke({"query": "ordinary"})
                return {"messages": [AIMessage(content="ordinary answer")]}

            async def astream(self, *_args, **_kwargs):
                await tool.ainvoke({"query": "streamed"})
                yield AIMessageChunk(content="stream answer", id="answer"), {
                    "langgraph_node": "model"
                }

        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(routes_sessions, "storage", storage),
                patch.object(agent_module, "agent", FakeAgent()),
                patch.object(agent_module.memory_service, "is_enabled", return_value=False),
                patch.object(agent_module, "_should_plan_execute", return_value=False),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
                patch("rag_pipeline.run_rag_graph", side_effect=self._rag_result),
            ):
                ordinary = await agent_module.chat_with_agent("one", "user", "session")
                events = [
                    event
                    async for event in agent_module.chat_with_agent_stream(
                        "two", "user", "session"
                    )
                ]
                restored = await routes_sessions.get_session_messages("user", "session")

            self.assertEqual(ordinary["rag_trace"]["query"], "ordinary")
            stream_payloads = [
                json.loads(event.removeprefix("data: ").strip())
                for event in events
                if event != "data: [DONE]\n\n"
            ]
            streamed = next(item["rag_trace"] for item in stream_payloads if item["type"] == "trace")
            self.assertEqual(streamed["query"], "streamed")
            self.assertNotEqual(streamed["tool_call_id"], ordinary["rag_trace"]["tool_call_id"])
            self.assertEqual(restored.messages[1].rag_trace.query, "ordinary")
            self.assertEqual(restored.messages[3].rag_trace.query, "streamed")
            self.assertEqual(
                restored.messages[3].rag_trace.tool_call_id, streamed["tool_call_id"]
            )

    async def test_trace_capture_shared_with_child_task_and_workflow_merge(self):
        begin_rag_trace_capture()
        reset_tool_call_guards()
        tool = instrument_tool(search_knowledge_base)
        with patch("rag_pipeline.run_rag_graph", side_effect=self._rag_result):
            await asyncio.create_task(tool.ainvoke({"query": "child-task"}))
        current = get_last_rag_context()["rag_trace"]
        previous = {
            "tool_used": True,
            "tool_name": "search_knowledge_base",
            "tool_call_id": "previous-id",
            "query": "previous",
        }
        merged = merge_rag_traces(previous, current)
        self.assertEqual([item["rag_trace"]["query"] for item in merged["tool_calls"]], ["previous", "child-task"])
        self.assertEqual(merged["query"], "child-task")


if __name__ == "__main__":
    unittest.main()
