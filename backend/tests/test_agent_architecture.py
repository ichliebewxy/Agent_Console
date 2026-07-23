import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
from langchain_core.messages import AIMessageChunk
from subagents import SkillAgentRegistry


class AgentArchitectureTests(unittest.IsolatedAsyncioTestCase):
    def test_stream_message_id_groups_chunks_by_model_message(self):
        first = AIMessageChunk(content="first", id="model-message-1")
        second = AIMessageChunk(content="second", id="model-message-2")

        self.assertEqual(
            agent_module._message_stream_id(first, {"langgraph_step": 1}),
            "model-message-1",
        )
        self.assertEqual(
            agent_module._message_stream_id(second, {"langgraph_step": 2}),
            "model-message-2",
        )
        self.assertEqual(
            agent_module._chunk_text(
                SimpleNamespace(content="准备调用工具", tool_call_chunks=[{"name": "demo"}])
            ),
            "准备调用工具",
        )

    async def test_stream_emits_boundary_between_model_messages(self):
        class FakeAgent:
            async def astream(self, *args, **kwargs):
                yield AIMessageChunk(content="第一段", id="message-1"), {"langgraph_node": "model"}
                yield AIMessageChunk(content="第二段", id="message-2"), {"langgraph_node": "model"}

        with (
            patch.object(agent_module, "agent", FakeAgent()),
            patch.object(agent_module.storage, "load", return_value=[]),
            patch.object(agent_module, "list_session_artifacts", return_value=[]),
            patch.object(agent_module, "_persist_response") as persist,
        ):
            raw_events = [
                event
                async for event in agent_module._chat_with_agent_stream_bound(
                    "hello",
                    "user",
                    "session",
                )
            ]

        payloads = [
            json.loads(event.removeprefix("data: ").strip())
            for event in raw_events
            if event != "data: [DONE]\n\n"
        ]
        self.assertEqual(
            [payload["type"] for payload in payloads[:3]],
            ["content", "content_boundary", "content"],
        )
        self.assertEqual(persist.call_args.args[3], "第一段\n\n第二段")

    async def test_main_agent_owns_langchain_core_tools_and_skill_gateway(self):
        captured = {}

        def fake_create_agent(**kwargs):
            captured.update(kwargs)
            return object()

        with (
            patch("agent._create_chat_model", return_value=object()),
            patch("agent.create_agent", side_effect=fake_create_agent),
            patch("agent.instrument_tools", side_effect=lambda tools: tools),
            patch("mcp_service.get_discovered_mcp_tools", return_value=[]),
        ):
            await agent_module.init_agent_async()

        self.assertEqual(
            {tool.name for tool in captured["tools"]},
            {
                "search_knowledge_base",
                "bash",
                "read_file",
                "write_file",
                "edit_file",
                "glob",
                "review",
                "load_skill",
                "read_skill_resource",
                "load_subagent",
                "delegate_to_skill_agent",
            },
        )
        self.assertNotIn("get_current_weather", {tool.name for tool in captured["tools"]})
        self.assertIn("OpenCLI", captured["system_prompt"])

    async def test_skills_agent_selects_skills_and_uses_same_reviewed_bash(self):
        captured = {}

        def fake_create_agent(**kwargs):
            captured.update(kwargs)
            return object()

        registry = SkillAgentRegistry(object())
        with (
            patch("subagents.create_agent", side_effect=fake_create_agent),
            patch("subagents.instrument_tools", side_effect=lambda tools: tools),
        ):
            await registry._get_agent()

        self.assertEqual(
            {tool.name for tool in captured["tools"]},
            {
                "load_skill",
                "read_skill_resource",
                "bash",
                "read_file",
                "write_file",
                "edit_file",
                "glob",
                "review",
            },
        )
        self.assertIn("opencli", captured["system_prompt"])


if __name__ == "__main__":
    unittest.main()
