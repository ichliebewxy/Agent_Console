import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import skill_resolver
from runtime_context import bind_runtime_context
from session_resources import SessionResourceStore
from skill_bindings import SkillBindingStore
from skill_service import SKILL_REGISTRY, load_skill, read_skill_resource


class SkillBindingTests(unittest.TestCase):
    def test_skill_catalog_and_content_are_isolated_per_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = SessionResourceStore(root / "resources.json")
            resources.put("user", "a", {"skills": ["pdf"]})
            resources.put("user", "b", {"skills": []})
            bindings = SkillBindingStore(root / "bindings.json")
            with patch.object(skill_resolver, "SESSION_RESOURCES", resources), patch.object(skill_resolver, "SKILL_BINDINGS", bindings):
                with bind_runtime_context("user", "a"):
                    self.assertEqual(skill_resolver.visible_skill_names(SKILL_REGISTRY.names), ("pdf",))
                    self.assertIn("Loaded skill", load_skill.invoke({"name": "pdf"}))
                    self.assertIn("SKILL_ERROR", read_skill_resource.invoke({"skill_name": "opencli", "relative_path": "SKILL.md"}))
                with bind_runtime_context("user", "b"):
                    self.assertEqual(skill_resolver.visible_skill_names(SKILL_REGISTRY.names), ())
                    self.assertIn("SKILL_ERROR", load_skill.invoke({"name": "pdf"}))

    def test_user_project_session_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = SessionResourceStore(root / "resources.json")
            bindings = SkillBindingStore(root / "bindings.json")
            bindings.put("user", None, {"pdf": False})
            bindings.put("user", "project", {"pdf": True, "opencli": False})
            resources.put("user", "session", {"project_id": "project"})
            with patch.object(skill_resolver, "SESSION_RESOURCES", resources), patch.object(skill_resolver, "SKILL_BINDINGS", bindings):
                with bind_runtime_context("user", "session"):
                    names = skill_resolver.visible_skill_names(SKILL_REGISTRY.names)
                    self.assertIn("pdf", names)
                    self.assertNotIn("opencli", names)
            resources.put("user", "session", {"project_id": "project", "skills": ["opencli"]})
            with patch.object(skill_resolver, "SESSION_RESOURCES", resources), patch.object(skill_resolver, "SKILL_BINDINGS", bindings):
                with bind_runtime_context("user", "session"):
                    self.assertEqual(skill_resolver.visible_skill_names(SKILL_REGISTRY.names), ("opencli",))


if __name__ == "__main__":
    unittest.main()
