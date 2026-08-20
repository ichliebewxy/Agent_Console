import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from artifact_service import (
    _signing_key,
    artifact_access_token,
    list_session_artifacts,
    resolve_session_artifact,
)
from api import router as api_router
from routes_artifacts import router as artifacts_router
from runtime_context import delete_session_files, session_files_dir
from schemas import ChatRequest


class ArtifactTests(unittest.TestCase):
    def test_session_isolation_listing_and_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("runtime_context.BACKEND_TMP_DIR", Path(directory).resolve()),
                patch("artifact_service.ARTIFACT_SIGNING_KEY", "unit-test-key"),
            ):
                _signing_key.cache_clear()
                first_root = session_files_dir("user-a", "session-a")
                second_root = session_files_dir("user-a", "session-b")
                self.assertNotEqual(first_root, second_root)
                deliverables = first_root / "deliverables"
                (deliverables / "reports").mkdir(parents=True)
                (deliverables / "reports" / "answer.txt").write_text(
                    "download me",
                    encoding="utf-8",
                )
                (deliverables / ".cache").mkdir(parents=True)
                (deliverables / ".cache" / "intermediate.bin").write_bytes(b"cache")
                # Intermediate/working files outside deliverables/ are not delivered.
                (first_root / "scratch").mkdir()
                (first_root / "scratch" / "draft.log").write_text("draft", encoding="utf-8")
                (first_root / "work.ipynb").write_text("source", encoding="utf-8")

                rows = list_session_artifacts("user-a", "session-a")
                self.assertEqual([row["path"] for row in rows], ["reports/answer.txt"])
                self.assertIn("/artifacts/reports/answer.txt", rows[0]["download_url"])
                self.assertIn("?token=", rows[0]["download_url"])
                self.assertEqual(
                    resolve_session_artifact(
                        "user-a",
                        "session-a",
                        "reports/answer.txt",
                    ).read_text(encoding="utf-8"),
                    "download me",
                )
                with self.assertRaises(ValueError):
                    resolve_session_artifact("user-a", "session-a", "../outside.txt")

                app = FastAPI()
                app.include_router(artifacts_router)
                client = TestClient(app)
                token = artifact_access_token("user-a", "session-a")
                self.assertEqual(
                    client.get("/sessions/user-a/session-a/artifacts").status_code,
                    404,
                )
                listing = client.get(
                    "/sessions/user-a/session-a/artifacts",
                    params={"token": token},
                )
                self.assertEqual(listing.status_code, 200)
                download = client.get(
                    "/sessions/user-a/session-a/artifacts/reports/answer.txt",
                    params={"token": token},
                )
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download.content, b"download me")
                (second_root / "keep.txt").write_text("keep", encoding="utf-8")
                delete_session_files("user-a", "session-a")
                self.assertFalse(first_root.exists())
                self.assertTrue((second_root / "keep.txt").is_file())
                _signing_key.cache_clear()

    def test_chat_identity_rejects_null_empty_and_path_characters(self):
        for invalid in (None, "", "../other", "with/slash"):
            with self.assertRaises(ValidationError):
                ChatRequest(message="hello", user_id=invalid, session_id="session-a")

    def test_runtime_record_routes_are_not_exposed(self):
        paths = {route.path for route in api_router.routes}
        self.assertNotIn("/tool-failures", paths)
        self.assertNotIn("/bash-audit", paths)


if __name__ == "__main__":
    unittest.main()
