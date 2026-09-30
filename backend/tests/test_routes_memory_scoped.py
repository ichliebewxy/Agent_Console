import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import routes_memory
from schemas import MemoryAddRequest, MemoryUpdateRequest
from session_resources import SessionResourceStore


class ScopedMemoryRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_http_route_uses_scoped_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            store.put("user", "one", {"memory_read_scopes": ["session"]})
            app = FastAPI()
            app.include_router(routes_memory.router)
            with patch.object(routes_memory, "SESSION_RESOURCES", store), \
                 patch.object(routes_memory.memory_service, "get_all", return_value=[]):
                response = TestClient(app).get("/memory/session/user/one/session")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["memories"], [])

    async def test_read_and_write_use_only_configured_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            store.put("user", "one", {"memory_read_scopes": ["session"]})
            with patch.object(routes_memory, "SESSION_RESOURCES", store), \
                 patch.object(routes_memory.memory_service, "get_all", return_value=[{"id": "m1", "memory": "fact"}]) as get_all, \
                 patch.object(routes_memory.memory_service, "add_memory", return_value={"results": []}) as add:
                listed = await routes_memory.list_session_memories("user", "one", "session")
                await routes_memory.add_session_memory("user", "one", "session", MemoryAddRequest(memory="new"))
            self.assertEqual(listed.memories[0].memory, "fact")
            self.assertEqual(get_all.call_args.args[0], add.call_args.args[1])
            self.assertNotEqual(get_all.call_args.args[0], "user")

    async def test_disabled_scope_and_foreign_memory_id_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            store.put("user", "one", {"memory_read_scopes": ["session"]})
            with patch.object(routes_memory, "SESSION_RESOURCES", store):
                with self.assertRaises(HTTPException) as disabled:
                    await routes_memory.list_session_memories("user", "one", "user")
                self.assertEqual(disabled.exception.status_code, 403)
                with patch.object(routes_memory.memory_service, "get_memory", return_value={"id": "foreign", "user_id": "other"}), \
                     patch.object(routes_memory.memory_service, "update_memory") as update:
                    with self.assertRaises(HTTPException) as foreign:
                        await routes_memory.update_session_memory(
                            "user", "one", "session", "foreign", MemoryUpdateRequest(memory="changed")
                        )
                    self.assertEqual(foreign.exception.status_code, 404)
                    update.assert_not_called()

    async def test_edits_scoped_memory_by_id_without_list_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            store.put("user", "one", {"memory_read_scopes": ["session"]})
            namespace = routes_memory.resolve_memory_access("user", "one", store.get("user", "one")).reads[0][1]
            with patch.object(routes_memory, "SESSION_RESOURCES", store), \
                 patch.object(routes_memory.memory_service, "get_memory", return_value={"id": "old", "user_id": namespace}) as get, \
                 patch.object(routes_memory.memory_service, "get_all") as get_all, \
                 patch.object(routes_memory.memory_service, "update_memory") as update, \
                 patch.object(routes_memory, "sync_extraction_file"):
                await routes_memory.update_session_memory(
                    "user", "one", "session", "old", MemoryUpdateRequest(memory="changed")
                )
            get.assert_called_once_with("old")
            get_all.assert_not_called()
            update.assert_called_once_with("old", "changed")


if __name__ == "__main__":
    unittest.main()
