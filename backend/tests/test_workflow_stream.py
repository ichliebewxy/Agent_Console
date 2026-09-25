import json
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
from workflow_state import initial_workflow_state
from workflow_stream import stream_workflow_events


class WorkflowStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_is_serializable_and_exposed_to_sse(self):
        async def execute(_instruction):
            return {
                "response": "TOOL_ERROR: unable to verify",
                "tool_events": [{"phase": "error", "result": "unable to verify"}],
                "rag_trace": None,
            }

        plan = plan_execute.Plan(
            objective="测试流",
            steps=[
                plan_execute.PlanStep(
                    id="f365b20d-0dd0-4b68-a3d0-a3de2499841f",
                    title="会失败的步骤",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patches = (
                patch("checkpoint_service.WORKFLOW_CHECKPOINT_PATH", root / "checkpoints.sqlite"),
                patch("checkpoint_service._RUN_INDEX_PATH", root / "runs.json"),
                patch("runtime_context.BACKEND_TMP_DIR", root / "workspace"),
                patch("workflow_graph.plan_execute.generate_plan", AsyncMock(return_value=plan)),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                try:
                    await checkpoint_service.initialize_checkpoint_service(execute)
                    events = [
                        event
                        async for event in stream_workflow_events(
                            initial_workflow_state("stream-run", "user", "session", "测试流")
                        )
                    ]
                    json.dumps(events, ensure_ascii=False)
                    waiting = [
                        event
                        for event in events
                        if event.get("type") == "workflow"
                        and event.get("status") == "waiting_user"
                    ]
                    self.assertEqual(len(waiting), 1)
                    self.assertTrue(waiting[0]["interrupts"])
                    self.assertTrue(any(event.get("type") == "plan" for event in events))
                    self.assertTrue(any(event.get("type") == "execute" for event in events))
                finally:
                    await checkpoint_service.close_checkpoint_service()


if __name__ == "__main__":
    unittest.main()
