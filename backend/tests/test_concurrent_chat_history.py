import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
from conversation_storage import ConversationStorage
from langchain_core.messages import AIMessage, AIMessageChunk


class ConcurrentChatHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_normal_turns_keep_both_questions_and_answers(self):
        seen_contexts = []

        class FakeAgent:
            async def ainvoke(self, request, **_kwargs):
                seen_contexts.append([message.content for message in request["messages"]])
                await asyncio.sleep(0.05)
                question = request["messages"][-1].content
                return {"messages": [AIMessage(content=f"reply: {question}")]}

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(agent_module, "storage", ConversationStorage(str(Path(directory) / "history.json"))),
            patch.object(agent_module, "agent", FakeAgent()),
            patch.object(agent_module.memory_service, "is_enabled", return_value=False),
            patch.object(agent_module, "_should_plan_execute", return_value=False),
            patch.object(agent_module, "list_session_artifacts", return_value=[]),
        ):
            await asyncio.gather(
                agent_module.chat_with_agent("first", "user", "shared"),
                agent_module.chat_with_agent("second", "user", "shared"),
            )
            history = agent_module.storage.load("user", "shared")

        self.assertEqual(
            [message.content for message in history],
            ["first", "reply: first", "second", "reply: second"],
        )
        self.assertIn("relaxed", seen_contexts[1][0])
        self.assertIn("Skill", seen_contexts[1][1])
        self.assertEqual(seen_contexts[1][2:], ["first", "reply: first", "second"])

    async def test_two_streamed_turns_keep_both_questions_and_answers(self):
        class FakeAgent:
            async def astream(self, request, **_kwargs):
                await asyncio.sleep(0.05)
                question = request["messages"][-1].content
                yield AIMessageChunk(content=f"reply: {question}", id=question), {
                    "langgraph_node": "model"
                }

        async def collect(question):
            return [
                event
                async for event in agent_module.chat_with_agent_stream(
                    question, "user", "shared"
                )
            ]

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(agent_module, "storage", ConversationStorage(str(Path(directory) / "history.json"))),
            patch.object(agent_module, "agent", FakeAgent()),
            patch.object(agent_module.memory_service, "is_enabled", return_value=False),
            patch.object(agent_module, "_should_plan_execute", return_value=False),
            patch.object(agent_module, "list_session_artifacts", return_value=[]),
        ):
            streams = await asyncio.gather(collect("first"), collect("second"))
            history = agent_module.storage.load("user", "shared")

        self.assertTrue(all(events[-1] == "data: [DONE]\n\n" for events in streams))
        self.assertEqual(
            [message.content for message in history],
            ["first", "reply: first", "second", "reply: second"],
        )


if __name__ == "__main__":
    unittest.main()
