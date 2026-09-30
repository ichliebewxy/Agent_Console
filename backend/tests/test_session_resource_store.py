import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from session_resources import SessionResourceStore, validate_resources


class SessionResourceStoreTests(unittest.TestCase):
    def test_round_trip_and_distinct_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionResourceStore(Path(directory) / "resources.json")
            store.put("user", "a", {
                "project_id": "project", "skills": ["pdf"],
                "memory_read_scopes": ["project", "session"],
                "memory_write_scope": "session",
            })
            self.assertEqual(store.get("user", "a").skills, ("pdf",))
            self.assertIsNone(store.get("user", "b").skills)
            self.assertEqual(SessionResourceStore(store.path).get("user", "a").project_id, "project")
            store.delete("user", "a")
            self.assertIsNone(store.get("user", "a").project_id)

    def test_invalid_project_scope_and_duplicate_skills_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_resources({"memory_read_scopes": ["project"]})
        with self.assertRaises(ValueError):
            validate_resources({"skills": ["pdf", "pdf"]})


if __name__ == "__main__":
    unittest.main()
