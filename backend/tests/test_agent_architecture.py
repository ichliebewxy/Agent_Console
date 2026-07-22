import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
from subagents import SkillAgentRegistry


class AgentArchitectureTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_agent_owns_direct_core_tools_and_skill_gateway(self):
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
                "get_current_weather",
                "search_knowledge_base",
                "bash",
                "delegate_to_skill_agent",
            },
        )
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
                "list_workspace_files",
                "read_workspace_file",
                "write_workspace_file",
                "bash",
            },
        )
        self.assertIn("opencli", captured["system_prompt"])


if __name__ == "__main__":
    unittest.main()
