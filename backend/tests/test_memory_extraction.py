import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import memory_extraction


class MemoryExtractionTests(unittest.TestCase):
    def test_parses_only_four_supported_categories(self):
        result = memory_extraction._parse_facts(json.dumps({"memories": [
            {"type": "feedback", "memory": "用户希望先给结论"},
            {"type": "temporary", "memory": "今天吃面"},
        ]}, ensure_ascii=False))
        self.assertEqual(result, [{"type": "feedback", "memory": "用户希望先给结论"}])

    def test_has_memory_writes_since_filters_recent_duplicate(self):
        current = [
            {"id": "old", "memory": "用户喜欢中文回复"},
            {"id": "new", "memory": "用户偏好简洁的回答"},
        ]
        self.assertTrue(memory_extraction.hasMemoryWritesSince(
            {"old"}, current, "用户偏好简洁的回答"
        ))
        self.assertFalse(memory_extraction.hasMemoryWritesSince(
            {"old"}, current, "用户长期使用 Python"
        ))

    def test_extracts_one_new_file_and_skips_existing_and_own_write(self):
        records = [{"id": "existing", "memory": "用户喜欢中文回复"}]

        def add(text, user_id, metadata=None, infer=False):
            self.assertEqual(user_id, "user-a")
            self.assertFalse(infer)
            self.assertIn(metadata["type"], memory_extraction.MEMORY_TYPES)
            record = {"id": "new-1", "memory": text}
            records.append(record)
            return {"results": [{"event": "ADD", "id": "new-1"}]}

        facts = [
            {"type": "preference", "memory": "用户喜欢中文回复"},
            {"type": "feedback", "memory": "用户希望回答先给结论"},
            {"type": "feedback", "memory": "用户希望回答先给结论"},
        ]
        with tempfile.TemporaryDirectory() as tmp, \
            patch.object(memory_extraction, "EXTRACTION_DIR", Path(tmp)), \
            patch.object(memory_extraction.memory_service, "get_all", side_effect=lambda *a, **k: list(records)), \
            patch.object(memory_extraction.memory_service, "add_memory", side_effect=add), \
            patch.object(memory_extraction, "_model_facts", return_value=facts):
            written = memory_extraction.extractMemories("user-a", "session-a", "反馈", [])
            files = list(Path(tmp).rglob("*.json"))
            self.assertEqual(len(written), 1)
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text(encoding="utf-8"))["type"], "feedback")


if __name__ == "__main__":
    unittest.main()
