import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent
import routes_runs
import routes_sessions
import session_resources
from artifact_service import artifact_access_token, list_session_artifacts, open_session_artifact, verify_artifact_access
from bash_tool import review_bash_command
from core_tools import edit_file, glob, read_file, write_file
from fastapi import FastAPI
from fastapi.testclient import TestClient
from local_runtime_service import run_local_command
from runtime_context import active_workspace_dir, bind_runtime_context, delete_session_files, session_files_dir
from session_resources import SessionResourceStore, validate_resources
from workspace_tools import read_workspace_file


class WorkspaceSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "项目 with spaces"
        self.project.mkdir()
        self.store = SessionResourceStore(self.root / "resources.json")
        for target, value in (
            ("session_resources.SESSION_RESOURCES", self.store),
            ("routes_sessions.SESSION_RESOURCES", self.store),
            ("routes_runs.SESSION_RESOURCES", self.store),
            ("agent.SESSION_RESOURCES", self.store),
            ("runtime_context.BACKEND_TMP_DIR", self.root / "sessions"),
            ("artifact_service.ARTIFACT_SIGNING_KEY", "workspace-test-key"),
        ):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client_app = FastAPI()
        self.client_app.include_router(routes_sessions.router)
        self.client_app.include_router(routes_runs.router)
        self.client = TestClient(self.client_app)

    def select(self, session="selected", mode="relaxed"):
        return self.store.put("user", session, {"workspace_dir": str(self.project), "permission_mode": mode})

    async def test_selected_folder_is_used_by_commands_and_both_file_tool_sets(self):
        self.select()
        with bind_runtime_context("user", "selected"):
            self.assertEqual(active_workspace_dir(), self.project)
            result = await run_local_command(f'"{sys.executable}" -c "from pathlib import Path; print(Path.cwd())"')
            self.assertIn(str(self.project), result)
            self.assertIn("LOCAL_RUNTIME_EXIT_CODE=0", result)
            await write_file.ainvoke({"path": "source.txt", "content": "before"})
            self.assertEqual(await read_workspace_file.ainvoke({"path": "source.txt"}), "before")
            await edit_file.ainvoke({"path": "source.txt", "old_text": "before", "new_text": "after"})
            self.assertEqual(await glob.ainvoke({"pattern": "*.txt"}), "source.txt")
        self.assertEqual((self.project / "source.txt").read_text(encoding="utf-8"), "after")
        self.assertIsNone(SessionResourceStore(self.store.path).get("user", "other").workspace_dir)

    async def test_folderless_and_cleared_folder_use_separate_managed_directories(self):
        self.select()
        self.store.put("user", "selected", {"workspace_dir": None})
        with bind_runtime_context("user", "selected"):
            selected_root = active_workspace_dir()
            self.assertEqual(selected_root, session_files_dir())
            self.assertNotEqual(selected_root, self.project)
        with bind_runtime_context("user", "other"):
            self.assertNotEqual(active_workspace_dir(), selected_root)
            result = await run_local_command("echo first && echo second")
            self.assertIn("LOCAL_RUNTIME_EXIT_CODE=0", result)
            self.assertIn("second", result)

    async def test_relaxed_paths_and_commands_and_restricted_mode(self):
        self.select()
        outside = self.root / "outside.txt"
        with bind_runtime_context("user", "selected"):
            await write_file.ainvoke({"path": str(outside), "content": "external"})
            self.assertEqual(await read_file.ainvoke({"path": "../outside.txt"}), "external")
            self.assertEqual(review_bash_command("whoami").behavior, "allow")
            self.assertEqual(review_bash_command(f'type "{outside}"').behavior, "allow")
            self.assertEqual(review_bash_command("echo first && echo second").behavior, "allow")
            self.assertEqual(review_bash_command("shutdown /s").behavior, "deny")
            self.assertEqual(review_bash_command("opencli reddit reply --id 1").behavior, "deny")
        self.select(mode="restricted")
        with bind_runtime_context("user", "selected"):
            result = await read_file.ainvoke({"path": str(outside)})
            self.assertTrue(result.startswith("TOOL_ERROR:"))
            self.assertEqual(review_bash_command("whoami").behavior, "deny")
            self.assertEqual(review_bash_command("echo first && echo second").behavior, "deny")
        self.assertEqual(outside.read_text(encoding="utf-8"), "external")

    def test_folder_browser_and_resource_api_accept_selection_and_null(self):
        url = "/sessions/user/selected/resources"
        response = self.client.put(url, json={"workspace_dir": str(self.project)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["permission_mode"], "relaxed")
        self.assertEqual(self.client.get(url).json()["workspace_dir"], str(self.project))
        listing = self.client.get("/workspace/folders", params={"path": str(self.root)})
        self.assertEqual(listing.status_code, 200)
        self.assertIn(str(self.project), [item["path"] for item in listing.json()["directories"]])
        self.assertEqual(self.client.get("/workspace/folders", params={"path": "relative"}).status_code, 422)
        self.assertEqual(self.client.put(url, json={"workspace_dir": str(self.root / "missing")}).status_code, 422)
        self.assertEqual(self.client.put(url, json={"workspace_dir": "relative"}).status_code, 422)
        self.assertEqual(self.client.put(url, json={"permission_mode": "anything"}).status_code, 422)
        self.assertIsNone(self.client.put(url, json={"workspace_dir": None}).json()["workspace_dir"])

    def test_existing_resource_records_gain_folderless_relaxed_defaults(self):
        self.store.path.write_text(json.dumps({"user\u0000old": {"skills": []}}), encoding="utf-8")
        resources = self.store.get("user", "old")
        self.assertIsNone(resources.workspace_dir)
        self.assertEqual(resources.permission_mode, "relaxed")
        self.assertIsNone(validate_resources({"workspace_dir": "  "}).workspace_dir)

    def test_missing_selected_folder_is_reported_and_can_be_cleared(self):
        self.select()
        self.project.rmdir()
        self.assertEqual(self.store.get("user", "selected").workspace_dir, str(self.project))
        with bind_runtime_context("user", "selected"), self.assertRaisesRegex(ValueError, "重新选择"):
            active_workspace_dir()
        self.store.put("user", "selected", {"workspace_dir": None})

    def test_artifacts_use_selected_folder_and_links_are_scoped_to_it(self):
        self.select()
        deliverables = self.project / "deliverables"
        deliverables.mkdir()
        (deliverables / "result.txt").write_text("result", encoding="utf-8")
        token = artifact_access_token("user", "selected")
        self.assertEqual(list_session_artifacts("user", "selected")[0]["path"], "result.txt")
        handle, _, _ = open_session_artifact("user", "selected", "result.txt")
        with handle:
            self.assertEqual(handle.read(), b"result")
        with self.assertRaises(ValueError):
            open_session_artifact("user", "selected", "../outside.txt")
        self.store.put("user", "selected", {"workspace_dir": None})
        self.assertFalse(verify_artifact_access("user", "selected", token))

    def test_deleting_session_files_preserves_selected_project(self):
        self.select()
        marker = self.project / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with bind_runtime_context("user", "selected"):
            managed = session_files_dir()
        delete_session_files("user", "selected")
        self.assertFalse(managed.exists())
        self.assertTrue(marker.exists())

    def test_selected_project_uses_direct_agent_and_cannot_resume_managed_workflow(self):
        self.select()
        with bind_runtime_context("user", "selected"), patch.object(agent.plan_execute, "is_multi_step_task", return_value=True):
            self.assertFalse(agent._should_plan_execute("multi-step task"))
        state = {"user_id": "user", "session_id": "selected"}
        with patch.object(routes_runs, "get_run_state", new=AsyncMock(return_value=state)), patch.object(routes_runs, "resume_run", new=AsyncMock()) as resume:
            response = self.client.post("/runs/run/resume", json={"action": "retry"})
            self.assertEqual(response.status_code, 409)
            resume.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
