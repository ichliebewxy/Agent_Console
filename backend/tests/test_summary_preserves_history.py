import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
import routes_sessions
from conversation_storage import ConversationStorage
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage


class SummaryHistoryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _seed(storage):
        history = [
            message
            for index in range(26)
            for message in (
                HumanMessage(content=f"question {index}"),
                AIMessage(content=f"answer {index}"),
            )
        ]
        artifact = {
            "path": "source.txt",
            "name": "source.txt",
            "size": 7,
            "updated_at": "2026-01-01T00:00:00",
            "mime_type": "text/plain",
            "download_url": "/artifacts/source.txt",
        }
        storage.save("user", "session", history, extra_message_data=[{"artifacts": [artifact]}])
        return artifact

    async def test_normal_chat_summarizes_context_without_replacing_originals(self):
        class FakeModel:
            def __init__(self):
                self.prompts = []

            def invoke(self, prompt):
                self.prompts.append(prompt)
                return SimpleNamespace(content="concise summary")

        class FakeAgent:
            def __init__(self):
                self.contexts = []

            async def ainvoke(self, request, **_kwargs):
                self.contexts.append(request["messages"])
                return {"messages": [AIMessage(content="new answer")]}

        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            artifact = self._seed(storage)
            model = FakeModel()
            agent = FakeAgent()
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(routes_sessions, "storage", storage),
                patch.object(agent_module, "model", model),
                patch.object(agent_module, "agent", agent),
                patch.object(agent_module.memory_service, "is_enabled", return_value=False),
                patch.object(agent_module, "_should_plan_execute", return_value=False),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
            ):
                await agent_module.chat_with_agent("new question", "user", "session")
                response = await routes_sessions.get_session_messages("user", "session")

            self.assertEqual(len(response.messages), 54)
            self.assertEqual(response.messages[0].content, "question 0")
            self.assertEqual(response.messages[0].artifacts[0].model_dump(), artifact)
            self.assertEqual(response.messages[-2].content, "new question")
            self.assertEqual(response.messages[-1].content, "new answer")
            self.assertEqual(len(agent.contexts[0]), 14)
            self.assertEqual(agent.contexts[0][0].type, "system")
            self.assertIn("concise summary", agent.contexts[0][0].content)
            self.assertEqual(storage.load_context_summary("user", "session")["covered_count"], 40)
            self.assertEqual(len(model.prompts), 1)

    async def test_stream_and_workflow_keep_raw_history(self):
        class FakeModel:
            def invoke(self, _prompt):
                return SimpleNamespace(content="summary")

        class FakeAgent:
            async def astream(self, *_args, **_kwargs):
                yield AIMessageChunk(content="stream answer", id="answer"), {"langgraph_node": "model"}

        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            self._seed(storage)
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(agent_module, "model", FakeModel()),
                patch.object(agent_module, "agent", FakeAgent()),
                patch.object(agent_module.memory_service, "is_enabled", return_value=False),
                patch.object(agent_module, "_should_plan_execute", return_value=False),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
            ):
                events = [
                    event
                    async for event in agent_module.chat_with_agent_stream(
                        "stream question", "user", "session"
                    )
                ]
            self.assertEqual(events[-1], "data: [DONE]\n\n")
            self.assertEqual(len(storage.load("user", "session")), 54)
            self.assertEqual(storage.load("user", "session")[0].content, "question 0")

            captured = {}

            class FakeWorkflow:
                async def ainvoke(self, initial, *_args, **_kwargs):
                    captured["history"] = initial["history"]

            with (
                patch.object(agent_module, "storage", storage),
                patch.object(agent_module, "model", FakeModel()),
                patch.object(agent_module, "agent", object()),
                patch.object(agent_module.memory_service, "is_enabled", return_value=False),
                patch.object(agent_module, "_should_plan_execute", return_value=True),
                patch.object(agent_module, "register_run", new=AsyncMock()),
                patch.object(agent_module, "get_workflow", return_value=FakeWorkflow()),
                patch.object(
                    agent_module,
                    "get_run_state",
                    new=AsyncMock(return_value={"final_response": "workflow answer", "steps": []}),
                ),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
            ):
                await agent_module.chat_with_agent("workflow question", "user", "session")

            self.assertEqual(len(storage.load("user", "session")), 56)
            self.assertEqual(storage.load("user", "session")[0].content, "question 0")
            self.assertEqual(captured["history"][0]["type"], "system")
            self.assertEqual(len(captured["history"]), 13)


if __name__ == "__main__":
    unittest.main()
