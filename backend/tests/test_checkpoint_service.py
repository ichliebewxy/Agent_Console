import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import checkpoint_service
import plan_execute
from runtime_context import active_workspace_dir, session_files_dir
from workflow_state import initial_workflow_state


class CheckpointServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_interrupt_resume_history_and_rollback(self):
        calls = 0

        async def execute(_instruction):
            nonlocal calls
            calls += 1
            workspace = active_workspace_dir()
            (workspace / "evidence.txt").write_text(
                f"attempt-{calls}", encoding="utf-8"
            )
            if calls == 1:
                return {
                    "response": "TOOL_ERROR: verify failed",
                    "tool_events": [{"phase": "error", "result": "verify failed"}],
                    "rag_trace": None,
                }
            return {"response": "恢复成功", "tool_events": [], "rag_trace": None}

        plan = plan_execute.Plan(
            objective="生成可恢复的结果",
            steps=[
                plan_execute.PlanStep(
                    id="09f77570-e3c2-4426-a281-cabb46712e74",
                    title="写入证据",
                )
            ],
        )
        reflection = plan_execute.Reflection(decision="complete", reason="已经完成")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "checkpoint-test-run"
            config = checkpoint_service.workflow_config(run_id)
            patches = (
                patch("checkpoint_service.WORKFLOW_CHECKPOINT_PATH", root / "checkpoints.sqlite"),
                patch("checkpoint_service._RUN_INDEX_PATH", root / "runs.json"),
                patch("runtime_context.BACKEND_TMP_DIR", root / "workspace"),
                patch("workflow_graph.plan_execute.generate_plan", AsyncMock(return_value=plan)),
                patch("workflow_graph.plan_execute.reflect", AsyncMock(return_value=reflection)),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                try:
                    await checkpoint_service.initialize_checkpoint_service(execute)
                    initial = initial_workflow_state(run_id, "user", "session", "执行任务")
                    await checkpoint_service.register_run(initial)
                    await checkpoint_service.get_workflow().ainvoke(initial, config, durability="sync")

                    interrupted = await checkpoint_service.get_run_state(run_id)
                    self.assertEqual(interrupted["run_status"], "waiting_user")
                    self.assertTrue(interrupted["interrupts"])
                    self.assertEqual(
                        (session_files_dir("user", "session") / "evidence.txt").exists(),
                        False,
                    )

                    recovered = await checkpoint_service.resume_run(run_id, {"action": "retry"})
                    self.assertEqual(recovered["run_status"], "completed")
                    self.assertIn("恢复成功", recovered["final_response"])
                    self.assertEqual(
                        (session_files_dir("user", "session") / "evidence.txt").read_text(encoding="utf-8"),
                        "attempt-2",
                    )
                    with self.assertRaises(ValueError):
                        await checkpoint_service.resume_run(run_id, {"action": "retry"})

                    history = await checkpoint_service.get_run_history(run_id)
                    self.assertGreater(len(history), 3)
                    final_checkpoint_id = history[0]["checkpoint_id"]
                    committed = next(
                        item
                        for item in history
                        if item.get("last_committed_step_id") and item.get("checkpoint_id")
                    )
                    forked = await checkpoint_service.fork_run(
                        run_id,
                        committed["checkpoint_id"],
                        {"final_response": "从历史检查点恢复"},
                    )
                    self.assertEqual(forked["final_response"], "从历史检查点恢复")
                    self.assertEqual(
                        (session_files_dir("user", "session") / "evidence.txt").read_text(encoding="utf-8"),
                        "attempt-2",
                    )
                    final_fork = await checkpoint_service.fork_run(
                        run_id,
                        final_checkpoint_id,
                    )
                    self.assertEqual(final_fork["run_status"], "completed")
                    self.assertEqual(calls, 2)
                finally:
                    await checkpoint_service.close_checkpoint_service()


if __name__ == "__main__":
    unittest.main()
