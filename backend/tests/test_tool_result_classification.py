import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from agent_state import consume_tool_events, reset_tool_call_guards
from subagents import SkillAgentRegistry, _loader_tool
from tool_instrumentation import instrument_tool
from tool_result import ERROR_PREFIXES, contains_error_result, is_error_result
from workflow_graph import _validate_step


class ToolResultClassificationTests(unittest.IsolatedAsyncioTestCase):
    def test_all_error_prefixes_have_one_shared_classification(self):
        for prefix in ERROR_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertTrue(is_error_result(f"{prefix} failure"))
                self.assertTrue(contains_error_result(f"step failed: {prefix} failure"))
        self.assertFalse(is_error_result("completed successfully"))
        self.assertFalse(is_error_result({"content": "SKILL_AGENT_ERROR: example"}))

    async def test_unknown_subagent_is_error_event_and_failed_workflow_step(self):
        reset_tool_call_guards()
        tool = instrument_tool(_loader_tool(SkillAgentRegistry(object())))
        output = await tool.ainvoke({"name": "missing"})
        events = consume_tool_events()
        self.assertTrue(output.startswith("SUBAGENT_ERROR:"))
        self.assertEqual(events[-1]["phase"], "error")

        state = {
            "current_step_id": "step-1",
            "results": {"step-1": {"output": output, "tool_events": events}},
            "attempts": {"step-1": 1},
        }
        result = await _validate_step(state)
        self.assertEqual(result["validation_status"], "recover")
        self.assertEqual(result["results"]["step-1"]["status"], "failed")

    async def test_skill_agent_error_in_response_alone_fails_validation(self):
        for prefix in ("SKILL_AGENT_ERROR:", "SUBAGENT_ERROR:"):
            with self.subTest(prefix=prefix):
                state = {
                    "current_step_id": "step-1",
                    "results": {
                        "step-1": {"output": f"Agent reports {prefix} failed", "tool_events": []}
                    },
                    "attempts": {"step-1": 1},
                }
                result = await _validate_step(state)
                self.assertEqual(result["validation_status"], "recover")


if __name__ == "__main__":
    unittest.main()
