import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import plan_execute
from workflow_graph import build_workflow_graph
from workflow_state import initial_workflow_state


class WorkflowGraphTests(unittest.IsolatedAsyncioTestCase):
    def _patch_runtime(self, *, decision="complete"):
        plan = plan_execute.Plan(
            objective="生成结果",
            steps=[plan_execute.PlanStep(id="5abec013-67cb-44f7-a10c-0be25b14f5c7", title="执行")],
        )
        return (
            patch("workflow_graph.plan_execute.generate_plan", AsyncMock(return_value=plan)),
            patch(
                "workflow_graph.plan_execute.reflect",
                AsyncMock(return_value=plan_execute.Reflection(decision=decision, reason="完成")),
            ),
            patch(
                "workflow_graph.begin_step_transaction",
                return_value={"snapshot_id": "snapshot-1"},
            ),
            patch(
                "workflow_graph.commit_step_transaction",
                return_value={"operation_key": "commit-1", "status": "committed"},
            ),
            patch(
                "workflow_graph.rollback_step_transaction",
                return_value={"operation_key": "rollback-1", "status": "rolled_back"},
            ),
        )

    async def test_successful_run_commits_and_completes(self):
        async def execute(_instruction):
            return {"response": "执行成功", "tool_events": [], "rag_trace": None}

        graph = build_workflow_graph(InMemorySaver(), execute)
        config = {"configurable": {"thread_id": "run-success"}}
        patches = self._patch_runtime()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await graph.ainvoke(
                initial_workflow_state("run-success", "user", "session", "完成任务"),
                config,
            )

        self.assertEqual(result["run_status"], "completed")
        self.assertIn("执行成功", result["final_response"])
        self.assertEqual(result["last_committed_step_id"], result["step_order"][0])
        self.assertIn("commit-1", result["effect_receipts"])

    async def test_failed_step_interrupts_then_resumes(self):
        calls = 0

        async def execute(_instruction):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {
                    "response": "TOOL_ERROR: bad input",
                    "tool_events": [{"phase": "error", "result": "bad input"}],
                    "rag_trace": None,
                }
            return {"response": "恢复成功", "tool_events": [], "rag_trace": None}

        graph = build_workflow_graph(InMemorySaver(), execute)
        config = {"configurable": {"thread_id": "run-recovery"}}
        patches = self._patch_runtime()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            first = await graph.ainvoke(
                initial_workflow_state("run-recovery", "user", "session", "完成任务"),
                config,
            )
            snapshot = await graph.aget_state(config)
            resumed = await graph.ainvoke(Command(resume={"action": "retry"}), config)

        self.assertEqual(first["run_status"], "waiting_user")
        self.assertTrue(any(task.interrupts for task in snapshot.tasks))
        self.assertEqual(resumed["run_status"], "completed")
        self.assertIn("恢复成功", resumed["final_response"])
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
