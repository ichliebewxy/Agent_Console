import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from bash_tool import BASH_TOOLS, bash, review_bash_command
from local_runtime_service import _local_environment, run_local_command
from runtime_context import bind_runtime_context, session_files_dir
from skill_service import SKILL_TOOLS
from workspace_tools import WORKSPACE_TOOLS


class LocalRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_runs_in_session_tmp_and_generates_file(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_root = Path(directory).resolve()
            with patch("runtime_context.BACKEND_TMP_DIR", tmp_root):
                with bind_runtime_context("local-user", "local-session"):
                    command = (
                        f'"{sys.executable}" -c '
                        '"from pathlib import Path; '
                        "Path('result.txt').write_text('local ok', encoding='utf-8')"
                        '"'
                    )
                    result = await run_local_command(command)
                    generated = session_files_dir() / "result.txt"

            self.assertIn("LOCAL_RUNTIME_EXIT_CODE=0", result)
            self.assertIn("result.txt", result)
            self.assertEqual(generated.read_text(encoding="utf-8"), "local ok")
            self.assertEqual(generated.parent.parent, tmp_root)

    async def test_timeout_returns_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("runtime_context.BACKEND_TMP_DIR", Path(directory).resolve()),
                patch("local_runtime_service.LOCAL_RUN_TIMEOUT", 1),
                patch("local_runtime_service.record_tool_failure", return_value={}),
            ):
                with bind_runtime_context("timeout-user", "timeout-session"):
                    command = f'"{sys.executable}" -c "import time; time.sleep(5)"'
                    result = await run_local_command(command)
            self.assertIn("Execution timed out", result)

    def test_environment_hides_common_secrets_and_redirects_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            with patch.dict(
                os.environ,
                {"DEMO_API_KEY": "secret", "DEMO_TOKEN": "secret", "KEEP_ME": "yes"},
            ):
                environment = _local_environment(workspace)
            self.assertNotIn("DEMO_API_KEY", environment)
            self.assertNotIn("DEMO_TOKEN", environment)
            self.assertEqual(environment["KEEP_ME"], "yes")
            self.assertEqual(environment["TEMP"], str(workspace))

    def test_bash_review_has_deny_priority_and_is_the_only_execution_tool(self):
        self.assertEqual(review_bash_command("python -c \"print(1)\"").behavior, "allow")
        self.assertEqual(review_bash_command("python -c \"print(1)\" && shutdown /s").behavior, "deny")
        self.assertEqual(review_bash_command("python -c \"open('C:/secret.txt')\"").behavior, "deny")
        tool_names = {
            tool.name
            for tool in [*SKILL_TOOLS, *WORKSPACE_TOOLS, *BASH_TOOLS]
        }
        self.assertEqual(
            tool_names,
            {
                "load_skill",
                "read_skill_resource",
                "list_workspace_files",
                "read_workspace_file",
                "write_workspace_file",
                "bash",
            },
        )

    async def test_shell_chain_is_rejected_before_process_start(self):
        with (
            patch("bash_tool.run_local_command", new=AsyncMock()) as runtime,
            patch("bash_tool.record_bash_audit"),
            bind_runtime_context("chain-user", "chain-session"),
        ):
            result = await bash.ainvoke({"command": "echo ok & whoami"})
        self.assertTrue(str(result).startswith("PERMISSION_DENIED:"))
        runtime.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
