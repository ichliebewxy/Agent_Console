import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import memory_service
import resource_context
import skill_resolver
from langchain_core.messages import HumanMessage
from memory_scope import resolve_memory_access
from runtime_context import bind_runtime_context
from session_resources import SessionResources, SessionResourceStore
from skill_bindings import SkillBindingStore


class MemoryScopeTests(unittest.TestCase):
    def test_namespace_isolated_and_user_memory_shared(self):
        resources = SessionResources(project_id="p", memory_read_scopes=("user", "project", "session"))
        a = resolve_memory_access("user", "a", resources)
        b = resolve_memory_access("user", "b", resources)
        other = resolve_memory_access("other", "a", resources)
        self.assertEqual(a.reads[0], b.reads[0])
        self.assertEqual(a.reads[1], b.reads[1])
        self.assertNotEqual(a.reads[2], b.reads[2])
        self.assertNotEqual(a.reads[1], other.reads[1])

    def test_search_calls_only_authorized_namespaces(self):
        access = resolve_memory_access("user", "a", SessionResources(memory_read_scopes=("session",)))
        with patch.object(memory_service, "search_for_context", return_value=["fact"]) as search:
            result = memory_service.search_scoped_context("query", access)
        self.assertEqual(result, [("session", "fact")])
        self.assertEqual(search.call_args.args[1], access.reads[0][1])

    def test_turn_context_is_rebuilt_for_each_session_without_mutating_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SessionResourceStore(root / "resources.json")
            store.put("user", "a", {"skills": ["pdf"], "memory_read_scopes": ["session"]})
            store.put("user", "b", {"skills": [], "memory_read_scopes": ["session"]})
            bindings = SkillBindingStore(root / "bindings.json")
            history = [HumanMessage(content="question")]

            def search(query, access):
                return [("session", access.reads[0][1])]

            with patch.object(resource_context, "SESSION_RESOURCES", store), \
                 patch.object(skill_resolver, "SESSION_RESOURCES", store), \
                 patch.object(skill_resolver, "SKILL_BINDINGS", bindings), \
                 patch.object(resource_context.memory_service, "is_enabled", return_value=True), \
                 patch.object(resource_context.memory_service, "search_scoped_context", side_effect=search):
                with bind_runtime_context("user", "a"):
                    a = asyncio.run(resource_context.build_resource_context(history, "question", "user", "a"))
                with bind_runtime_context("user", "b"):
                    b = asyncio.run(resource_context.build_resource_context(history, "question", "user", "b"))
            self.assertEqual(len(history), 1)
            self.assertIn("pdf", a[2].content)
            self.assertNotIn("- pdf:", b[2].content)
            self.assertNotEqual(a[0].content, b[0].content)


if __name__ == "__main__":
    unittest.main()
