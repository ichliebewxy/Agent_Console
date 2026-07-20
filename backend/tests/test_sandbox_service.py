import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from runtime_context import bind_runtime_context
from sandbox_service import SANDBOX_TOOLS, _docker_args, _workspace_limit_error, run_in_sandbox
from settings import SANDBOX_GID, SANDBOX_UID
from skill_service import SKILL_TOOLS
from workspace_tools import WORKSPACE_TOOLS


class SandboxConfigurationTests(unittest.TestCase):
    def test_docker_command_enforces_isolation_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            args = _docker_args("agent-sbx-test", workspace, "python demo.py")

        rendered = " ".join(str(value) for value in args)
        self.assertIn("--network none", rendered)
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop ALL", rendered)
        self.assertIn("--security-opt no-new-privileges", rendered)
        self.assertIn(f"--user {max(1, SANDBOX_UID)}:{max(1, SANDBOX_GID)}", rendered)
        self.assertIn(f"{workspace}:/workspace:rw", args)
        self.assertIn("--memory-swap", args)
        self.assertIn("--pids-limit", args)
        self.assertIn("--pull never", rendered)
        self.assertIn("fsize=", rendered)
        self.assertEqual(args[-3:], ["/bin/sh", "-lc", "python demo.py"])

    def test_workspace_quota_detects_total_size_and_file_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "large.bin").write_bytes(b"x" * (2 * 1024 * 1024))
            with patch("sandbox_service.SANDBOX_WORKSPACE_MAX_MB", 1):
                self.assertIn("Workspace size limit exceeded", _workspace_limit_error(root))

    def test_skills_agent_owns_only_skill_workspace_and_sandbox_tools(self):
        tool_names = {
            tool.name
            for tool in [*SKILL_TOOLS, *WORKSPACE_TOOLS, *SANDBOX_TOOLS]
        }
        self.assertEqual(
            tool_names,
            {
                "load_skill",
                "read_skill_resource",
                "list_workspace_files",
                "read_workspace_file",
                "write_workspace_file",
                "sandbox_status",
                "run_in_sandbox",
            },
        )


class SandboxCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_kills_process_and_removes_container(self):
        class FakeProcess:
            stdout = object()
            stderr = object()
            def __init__(self):
                self.killed = False
                self.returncode = None

            async def wait(self):
                if self.killed:
                    return self.returncode
                await asyncio.Future()

            def kill(self):
                self.killed = True
                self.returncode = -9

        async def force_timeout(awaitable, *, timeout):
            awaitable.close()
            raise asyncio.TimeoutError

        process = FakeProcess()
        cleanup = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("runtime_context.AGENT_WORKSPACE_DIR", Path(directory).resolve()),
                patch("sandbox_service.shutil.which", return_value="docker"),
                patch(
                    "sandbox_service.asyncio.create_subprocess_exec",
                    new=AsyncMock(return_value=process),
                ),
                patch("sandbox_service.asyncio.wait_for", side_effect=force_timeout),
                patch("sandbox_service._drain", new=AsyncMock(return_value=b"")),
                patch("sandbox_service._docker_cleanup", new=cleanup),
                patch("sandbox_service.record_tool_failure", return_value={}),
            ):
                with bind_runtime_context("timeout-user", "timeout-session"):
                    result = await run_in_sandbox.ainvoke({"command": "sleep 999"})

        self.assertTrue(process.killed)
        cleanup.assert_awaited_once()
        self.assertIn("Execution timed out", result)

    async def test_cancellation_kills_process_and_removes_container_once(self):
        class FakeProcess:
            stdout = object()
            stderr = object()

            def __init__(self):
                self.killed = False
                self.returncode = None

            async def wait(self):
                if self.killed:
                    return self.returncode
                await asyncio.Future()

            def kill(self):
                self.killed = True
                self.returncode = -9

        process = FakeProcess()
        cleanup = AsyncMock()
        started = asyncio.Event()

        async def create_process(*args, **kwargs):
            started.set()
            return process

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("runtime_context.AGENT_WORKSPACE_DIR", Path(directory).resolve()),
                patch("sandbox_service.shutil.which", return_value="docker"),
                patch(
                    "sandbox_service.asyncio.create_subprocess_exec",
                    side_effect=create_process,
                ),
                patch("sandbox_service._drain", new=AsyncMock(return_value=b"")),
                patch("sandbox_service._docker_cleanup", new=cleanup),
            ):
                with bind_runtime_context("cancel-user", "cancel-session"):
                    task = asyncio.create_task(
                        run_in_sandbox.ainvoke({"command": "sleep 999"})
                    )
                    await started.wait()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

        self.assertTrue(process.killed)
        cleanup.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
