import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as agent_module
from core_tools import edit_file, read_file, write_file
from runtime_context import session_files_dir


class SessionFileLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_chat_can_write_edit_and_read_files(self):
        class FileWorkflow:
            async def ainvoke(self, *_args, **_kwargs):
                self.write_result = await write_file.ainvoke(
                    {"path": "report.txt", "content": "draft"}
                )
                self.edit_result = await edit_file.ainvoke(
                    {"path": "report.txt", "old_text": "draft", "new_text": "final"}
                )
                self.read_result = await read_file.ainvoke({"path": "report.txt"})

        workflow = FileWorkflow()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("runtime_context.BACKEND_TMP_DIR", Path(directory)),
            patch.object(agent_module, "agent", object()),
            patch.object(agent_module.memory_service, "is_enabled", return_value=False),
            patch.object(agent_module.storage, "load", return_value=[]),
            patch.object(agent_module, "_should_plan_execute", return_value=True),
            patch.object(agent_module, "register_run", new=AsyncMock()),
            patch.object(agent_module, "get_workflow", return_value=workflow),
            patch.object(
                agent_module,
                "get_run_state",
                new=AsyncMock(return_value={"final_response": "done", "steps": []}),
            ),
            patch.object(agent_module, "list_session_artifacts", return_value=[]),
            patch.object(agent_module, "_persist_response"),
        ):
            result = await asyncio.wait_for(
                agent_module.chat_with_agent("plan and edit", "user", "session"),
                timeout=3,
            )
            content = (session_files_dir("user", "session") / "report.txt").read_text()

        self.assertEqual(result["response"], "done")
        self.assertIn("Wrote", workflow.write_result)
        self.assertIn("Edited", workflow.edit_result)
        self.assertEqual(workflow.read_result, "final")
        self.assertEqual(content, "final")

    async def test_different_session_workflows_run_concurrently(self):
        first_entered = asyncio.Event()
        second_entered = asyncio.Event()

        class ConcurrentWorkflow:
            async def ainvoke(self, *_args, **_kwargs):
                from runtime_context import current_runtime_context

                session = current_runtime_context().session_id
                if session == "first":
                    first_entered.set()
                    await asyncio.wait_for(second_entered.wait(), timeout=3)
                else:
                    second_entered.set()
                    await asyncio.wait_for(first_entered.wait(), timeout=3)
                await write_file.ainvoke({"path": "result.txt", "content": session})

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("runtime_context.BACKEND_TMP_DIR", Path(directory)),
            patch.object(agent_module, "agent", object()),
            patch.object(agent_module.memory_service, "is_enabled", return_value=False),
            patch.object(agent_module.storage, "load", return_value=[]),
            patch.object(agent_module, "_should_plan_execute", return_value=True),
            patch.object(agent_module, "register_run", new=AsyncMock()),
            patch.object(agent_module, "get_workflow", return_value=ConcurrentWorkflow()),
            patch.object(
                agent_module,
                "get_run_state",
                new=AsyncMock(return_value={"final_response": "done", "steps": []}),
            ),
            patch.object(agent_module, "list_session_artifacts", return_value=[]),
            patch.object(agent_module, "_persist_response"),
        ):
            results = await asyncio.wait_for(
                asyncio.gather(
                    agent_module.chat_with_agent("task", "user", "first"),
                    agent_module.chat_with_agent("task", "user", "second"),
                ),
                timeout=4,
            )
            contents = [
                (session_files_dir("user", session) / "result.txt").read_text()
                for session in ("first", "second")
            ]

        self.assertEqual([item["response"] for item in results], ["done", "done"])
        self.assertEqual(contents, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
