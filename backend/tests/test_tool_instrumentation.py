import sys
import unittest
from pathlib import Path

from langchain_core.tools import tool


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from settings import AGENT_TOOL_CALL_LIMIT
from tool_instrumentation import instrument_tool
from agent_state import reset_tool_call_guards


class ToolCallLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_instrumented_tools_stop_at_per_turn_limit(self):
        calls = 0

        @tool("budget_probe")
        def budget_probe(value: str) -> str:
            """Return a value while counting real executions."""
            nonlocal calls
            calls += 1
            return value

        instrumented = instrument_tool(budget_probe)
        reset_tool_call_guards()
        try:
            for _ in range(AGENT_TOOL_CALL_LIMIT):
                self.assertEqual(await instrumented.ainvoke({"value": "ok"}), "ok")
            limited = await instrumented.ainvoke({"value": "blocked"})
        finally:
            reset_tool_call_guards()

        self.assertIn("TOOL_CALL_LIMIT_REACHED", limited)
        self.assertEqual(calls, AGENT_TOOL_CALL_LIMIT)


if __name__ == "__main__":
    unittest.main()
