import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routes_sessions
from conversation_storage import ConversationStorage
from session_resources import SessionResourceStore


class SessionResourceRouteTests(unittest.TestCase):
    def test_http_round_trip_and_unknown_skill_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            app = FastAPI()
            app.include_router(routes_sessions.router)
            client = TestClient(app)
            url = "/sessions/user/one/resources"
            with patch.object(routes_sessions, "SESSION_RESOURCES", store):
                response = client.put(url, json={
                    "project_id": "crm",
                    "skills": ["pdf"],
                    "memory_read_scopes": ["project", "session"],
                    "memory_write_scope": "session",
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(client.get(url).json()["skills"], ["pdf"])
                invalid = client.put(url, json={"skills": ["missing-skill"]})
                self.assertEqual(invalid.status_code, 422)

    def test_delete_resource_only_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            history = ConversationStorage(str(Path(directory) / "history.json"))
            app = FastAPI()
            app.include_router(routes_sessions.router)
            client = TestClient(app)
            url = "/sessions/user/unused"
            with patch.object(routes_sessions, "SESSION_RESOURCES", store), \
                 patch.object(routes_sessions, "storage", history), \
                 patch.object(routes_sessions.memory_service, "delete_all") as delete_memories, \
                 patch.object(routes_sessions, "delete_session_files"), \
                 patch.object(routes_sessions, "delete_session_runs"):
                self.assertEqual(client.delete(url).status_code, 404)
                self.assertEqual(client.put(url + "/resources", json={"skills": []}).status_code, 200)
                self.assertTrue(store.contains("user", "unused"))
                listed = client.get("/sessions/user")
                self.assertEqual(listed.status_code, 200)
                self.assertEqual([row["session_id"] for row in listed.json()["sessions"]], ["unused"])
                self.assertEqual(client.delete(url).status_code, 200)
                self.assertFalse(store.contains("user", "unused"))
                self.assertEqual(client.get("/sessions/user").json()["sessions"], [])
                delete_memories.assert_called_once()
                self.assertEqual(client.delete(url).status_code, 404)


if __name__ == "__main__":
    unittest.main()
