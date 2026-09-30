import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
import goal_mode
import workflow_graph
from conversation_storage import ConversationStorage
from goal_mode import (
    MAX_AGENT_CYCLES,
    AgentCircuitOpen,
    AgentCycleLimitMiddleware,
    GoalEvaluation,
    agent_cycle_budget,
    cycles_used,
    prepare_goal_request,
)
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from subagents import SkillAgentRegistry


class GoalModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_langchain_agent_counts_a_model_round(self):
        worker = create_agent(
            model=FakeListChatModel(responses=["done"]),
            tools=[],
            middleware=[AgentCycleLimitMiddleware()],
        )
        with agent_cycle_budget():
            result = await worker.ainvoke(
                {"messages": [{"role": "user", "content": "start"}]}
            )
            self.assertEqual(cycles_used(), 1)
        self.assertEqual(result["messages"][-1].content, "done")

    def test_cycle_limit_counts_model_calls_and_fuses_before_call_101(self):
        middleware = AgentCycleLimitMiddleware()
        called = []

        def handler(_request):
            called.append(True)

        with agent_cycle_budget():
            for _ in range(MAX_AGENT_CYCLES):
                middleware.wrap_model_call(object(), handler)
            self.assertEqual(cycles_used(), 100)
            with self.assertRaises(AgentCircuitOpen):
                middleware.wrap_model_call(object(), handler)
        self.assertEqual(len(called), 100)

    async def test_async_agent_calls_share_the_same_100_round_budget(self):
        middleware = AgentCycleLimitMiddleware()
        called = []

        async def handler(_request):
            called.append(True)

        with agent_cycle_budget():
            for _ in range(MAX_AGENT_CYCLES):
                await middleware.awrap_model_call(object(), handler)
            with self.assertRaises(AgentCircuitOpen):
                await middleware.awrap_model_call(object(), handler)
        self.assertEqual(len(called), 100)

    async def test_workflow_and_subagent_propagate_circuit_breaker(self):
        async def fail(_instruction):
            raise AgentCircuitOpen()

        state = {
            "user_id": "u",
            "session_id": "s",
            "run_id": "r",
            "current_step_id": "step-1",
            "attempts": {},
            "history": [],
        }
        with (
            patch.object(workflow_graph, "_build_instruction", return_value="do it"),
            self.assertRaises(AgentCircuitOpen),
        ):
            await workflow_graph._make_execute_node(fail)(state)

        class FailingAgent:
            async def ainvoke(self, *_args, **_kwargs):
                raise AgentCircuitOpen()

        registry = SkillAgentRegistry(object())
        with patch.object(registry, "_get_agent", return_value=FailingAgent()):
            with self.assertRaises(AgentCircuitOpen):
                await registry.run("task")

    def test_goal_commands_are_scoped_to_session_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "history.json")
            storage = ConversationStorage(path)
            directive = prepare_goal_request("/goal 测试退出码为 0", storage, "u", "s")

            self.assertEqual(directive.action, "run")
            self.assertEqual(directive.prompt, "测试退出码为 0")
            self.assertEqual(
                ConversationStorage(path).load_goal_state("u", "s")["status"], "active"
            )
            self.assertIsNone(storage.load_goal_state("u", "other"))
            self.assertIn(
                "测试退出码为 0",
                prepare_goal_request("/goal", storage, "u", "s").response,
            )
            self.assertEqual(
                prepare_goal_request("/goal clear", storage, "u", "s").action, "clear"
            )
            self.assertIsNone(storage.load_goal_state("u", "s"))

    async def test_goal_continues_until_independent_evaluator_accepts(self):
        class FakeAgent:
            def __init__(self):
                self.calls = 0

            async def ainvoke(self, request, **_kwargs):
                self.calls += 1
                return {
                    "messages": [
                        *request["messages"],
                        AIMessage(content=f"answer {self.calls}"),
                    ]
                }

        verdicts = iter(
            [
                GoalEvaluation(False, "还缺少验证结果"),
                GoalEvaluation(True, "已看到验证结果"),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            fake_agent = FakeAgent()
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(agent_module, "agent", fake_agent),
                patch.object(agent_module, "model", object()),
                patch.object(
                    goal_mode,
                    "evaluate_goal",
                    new=AsyncMock(side_effect=lambda *_: next(verdicts)),
                ),
                patch.object(
                    agent_module.memory_service, "is_enabled", return_value=False
                ),
                patch.object(agent_module, "_should_plan_execute", return_value=True),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
            ):
                result = await agent_module.chat_with_agent("/goal 完成任务", "u", "s")

            self.assertEqual(result["response"], "answer 2")
            self.assertEqual(fake_agent.calls, 2)
            self.assertEqual(storage.load_goal_state("u", "s")["status"], "completed")
            self.assertEqual(storage.load_goal_state("u", "s")["iterations"], 2)
            self.assertEqual(storage.load("u", "s")[0].content, "/goal 完成任务")

    async def test_goal_fuses_after_100_agent_rounds_even_without_tools(self):
        class FakeAgent:
            calls = 0

            async def ainvoke(self, _request, **_kwargs):
                self.calls += 1
                return {"messages": [AIMessage(content="尚未完成")]}

        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            fake_agent = FakeAgent()
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(agent_module, "agent", fake_agent),
                patch.object(agent_module, "model", object()),
                patch.object(
                    goal_mode,
                    "evaluate_goal",
                    new=AsyncMock(return_value=GoalEvaluation(False, "未完成")),
                ),
                patch.object(
                    agent_module.memory_service, "is_enabled", return_value=False
                ),
                patch.object(agent_module, "_should_plan_execute", return_value=False),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
            ):
                result = await agent_module.chat_with_agent(
                    "/goal 永远无法完成", "u", "s"
                )

            self.assertEqual(fake_agent.calls, 100)
            self.assertIn("AGENT_CIRCUIT_OPEN", result["response"])
            self.assertEqual(storage.load_goal_state("u", "s")["status"], "fused")

    async def test_stream_goal_command_returns_without_agent_call(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(agent_module, "agent", object()),
            ):
                events = [
                    event
                    async for event in agent_module.chat_with_agent_stream(
                        "/goal", "u", "s"
                    )
                ]
            self.assertEqual(events[-1], "data: [DONE]\n\n")
            self.assertIn("没有 Goal", json.loads(events[0][6:])["content"])

    async def test_stream_goal_continues_and_persists_final_response(self):
        class FakeAgent:
            calls = 0

            async def ainvoke(self, request, **_kwargs):
                self.calls += 1
                return {
                    "messages": [
                        *request["messages"],
                        AIMessage(content=f"stream answer {self.calls}"),
                    ]
                }

        verdicts = iter(
            [
                GoalEvaluation(False, "继续"),
                GoalEvaluation(True, "完成"),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            storage = ConversationStorage(str(Path(directory) / "history.json"))
            fake_agent = FakeAgent()
            with (
                patch.object(agent_module, "storage", storage),
                patch.object(agent_module, "agent", fake_agent),
                patch.object(agent_module, "model", object()),
                patch.object(
                    goal_mode,
                    "evaluate_goal",
                    new=AsyncMock(side_effect=lambda *_: next(verdicts)),
                ),
                patch.object(
                    agent_module.memory_service, "is_enabled", return_value=False
                ),
                patch.object(agent_module, "_should_plan_execute", return_value=False),
                patch.object(agent_module, "list_session_artifacts", return_value=[]),
            ):
                events = [
                    event
                    async for event in agent_module.chat_with_agent_stream(
                        "/goal 完成任务", "u", "s"
                    )
                ]

            self.assertEqual(fake_agent.calls, 2)
            self.assertEqual(storage.load("u", "s")[-1].content, "stream answer 2")
            self.assertTrue(any('"type": "plan_step"' in event for event in events))
            self.assertEqual(events[-1], "data: [DONE]\n\n")


if __name__ == "__main__":
    unittest.main()
