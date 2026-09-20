import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import memory_service


class _FakeMemory:
    def __init__(self):
        self.calls = []

    def add(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"results": [{"event": "ADD"}]}


class LongTermMemoryPolicyTests(unittest.TestCase):
    def test_normal_questions_and_current_tasks_are_not_candidates(self):
        self.assertFalse(
            memory_service.is_long_term_memory_candidate("帮我修复这个报错")
        )
        self.assertFalse(
            memory_service.is_long_term_memory_candidate("北京今天天气怎么样？")
        )
        self.assertFalse(
            memory_service.is_long_term_memory_candidate("这次先用 CSV 导出")
        )

    def test_stable_preferences_and_explicit_future_rules_are_candidates(self):
        self.assertTrue(
            memory_service.is_long_term_memory_candidate("我喜欢简洁的回答")
        )
        self.assertTrue(
            memory_service.is_long_term_memory_candidate("以后请都用中文回复")
        )
        self.assertTrue(
            memory_service.is_long_term_memory_candidate(
                "Remember that I prefer Python."
            )
        )

    def test_credentials_are_never_automatic_memory(self):
        self.assertFalse(
            memory_service.is_long_term_memory_candidate("请记住我的 API key 是 abc123")
        )
        self.assertFalse(
            memory_service.is_long_term_memory_candidate("Remember my token is abc123")
        )

    def test_skipped_message_does_not_initialize_mem0(self):
        with patch.object(memory_service, "init_memory") as init_memory:
            result = memory_service.remember_conversation("u", "帮我改这段代码", "s")
        init_memory.assert_not_called()
        self.assertTrue(result["skipped"])

    def test_automatic_memory_uses_only_user_content_and_long_term_metadata(self):
        fake = _FakeMemory()
        with patch.object(memory_service, "init_memory", return_value=fake):
            memory_service.remember_conversation(
                "u",
                "以后请都用中文回复",
                "s",
            )

        messages, kwargs = fake.calls[0]
        self.assertEqual(messages, [{"role": "user", "content": "以后请都用中文回复"}])
        self.assertEqual(kwargs["user_id"], "u")
        self.assertTrue(kwargs["infer"])
        self.assertEqual(
            kwargs["metadata"],
            {"source": "automatic", "scope": "long_term", "session_id": "s"},
        )

    def test_mem0_config_contains_strict_extraction_instructions(self):
        config = memory_service._build_config()
        self.assertIn("When durability is uncertain", config["custom_instructions"])


if __name__ == "__main__":
    unittest.main()
