import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
import plan_execute
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from workflow_state import initial_workflow_state


class ConversationContextTests(unittest.TestCase):
    """跨轮上下文必须被带进 planner 与步骤执行器，不能在工作流里丢失。"""

    def test_initial_workflow_state_carries_history(self):
        history = [{"type": "human", "content": "从未来城去甜品店"}]
        state = initial_workflow_state("run", "u", "s", "规划路线", history=history)
        self.assertEqual(state["history"], history)

    def test_initial_workflow_state_defaults_history_to_empty(self):
        state = initial_workflow_state("run", "u", "s", "规划路线")
        self.assertEqual(state["history"], [])

    def test_plan_history_is_rendered_for_the_planner(self):
        text = plan_execute._format_history(
            [
                {"type": "human", "content": "从未来城去甜品店"},
                {"type": "ai", "content": "已定位未来城校区"},
                {"type": "system", "content": "之前的对话摘要"},
            ]
        )
        self.assertIn("用户：从未来城去甜品店", text)
        self.assertIn("AI：已定位未来城校区", text)
        self.assertIn("系统：之前的对话摘要", text)

    def test_plan_history_empty_is_explicit(self):
        self.assertEqual(plan_execute._format_history([]), "（无）")

    def test_history_serialize_round_trip(self):
        messages = [
            HumanMessage(content="用户问题"),
            AIMessage(content="助手回答"),
            SystemMessage(content="摘要"),
        ]
        restored = agent_module._messages_from_history(
            agent_module._serialize_history(messages)
        )
        self.assertEqual([m.type for m in restored], ["human", "ai", "system"])
        self.assertEqual(
            [m.content for m in restored], ["用户问题", "助手回答", "摘要"]
        )

    def test_prepare_messages_reuses_the_same_session_history(self):
        history = [HumanMessage(content="我们在做 A 项目"), AIMessage(content="已了解")]
        with patch.object(agent_module.storage, "load", return_value=history) as load:
            messages, previous = agent_module._prepare_messages(
                "继续刚才的工作", "u", "session-1"
            )

        load.assert_called_once_with("u", "session-1")
        self.assertEqual(previous, history)
        self.assertEqual(
            [message.content for message in messages],
            [
                "我们在做 A 项目",
                "已了解",
                "继续刚才的工作",
            ],
        )


if __name__ == "__main__":
    unittest.main()
