import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from runtime_context import session_files_dir, workflow_step_dir
from workspace_transaction import (
    _write_json,
    begin_step_transaction,
    commit_step_transaction,
    recover_workspace_transactions,
    rollback_step_transaction,
)


class WorkspaceTransactionTests(unittest.TestCase):
    def test_commit_rollback_and_recovery_reuse_staging(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "runtime_context.BACKEND_TMP_DIR", Path(directory)
        ):
            session = session_files_dir("user", "session")
            (session / "result.txt").write_text("before", encoding="utf-8")

            started = begin_step_transaction("user", "session", "run-1", "step-1")
            step_root = workflow_step_dir("user", "session", "run-1", "step-1")
            (step_root / "staging" / "result.txt").write_text("after", encoding="utf-8")

            receipt = commit_step_transaction("user", "session", "run-1", "step-1")
            self.assertEqual(
                (session_files_dir("user", "session") / "result.txt").read_text(encoding="utf-8"),
                "after",
            )
            self.assertEqual(receipt["status"], "committed")

            rollback_step_transaction("user", "session", "run-1", "step-1")
            self.assertEqual(
                (session_files_dir("user", "session") / "result.txt").read_text(encoding="utf-8"),
                "before",
            )

            recovered = begin_step_transaction("user", "session", "run-1", "step-1")
            self.assertEqual(recovered["snapshot_id"], started["snapshot_id"])
            self.assertEqual(
                (step_root / "staging" / "result.txt").read_text(encoding="utf-8"),
                "after",
            )

    def test_copy_failure_never_exposes_partial_version_and_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "runtime_context.BACKEND_TMP_DIR", Path(directory)
        ):
            session = session_files_dir("user", "session")
            (session / "a.txt").write_text("old a", encoding="utf-8")
            (session / "b.txt").write_text("old b", encoding="utf-8")
            begin_step_transaction("user", "session", "run-1", "step-1")
            step_root = workflow_step_dir("user", "session", "run-1", "step-1")
            (step_root / "staging" / "a.txt").write_text("new a", encoding="utf-8")
            (step_root / "staging" / "b.txt").write_text("new b", encoding="utf-8")

            import workspace_transaction

            original_copy = workspace_transaction._copy_tree_contents

            def fail_in_version_copy(source, destination, *, skip_reserved):
                if destination.parent.name == ".versions":
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "a.txt").write_text("new a", encoding="utf-8")
                    visible_during_copy = session_files_dir("user", "session")
                    self.assertEqual(visible_during_copy, session)
                    self.assertEqual(
                        (visible_during_copy / "b.txt").read_text(encoding="utf-8"),
                        "old b",
                    )
                    raise OSError("disk full after first file")
                return original_copy(source, destination, skip_reserved=skip_reserved)

            with patch.object(
                workspace_transaction, "_copy_tree_contents", side_effect=fail_in_version_copy
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    commit_step_transaction("user", "session", "run-1", "step-1")

            visible = session_files_dir("user", "session")
            self.assertEqual(visible, session)
            self.assertEqual((visible / "a.txt").read_text(encoding="utf-8"), "old a")
            self.assertEqual((visible / "b.txt").read_text(encoding="utf-8"), "old b")
            self.assertEqual(json.loads((step_root / "transaction.json").read_text())["status"], "begun")

            commit_step_transaction("user", "session", "run-1", "step-1")
            visible = session_files_dir("user", "session")
            self.assertEqual((visible / "a.txt").read_text(encoding="utf-8"), "new a")
            self.assertEqual((visible / "b.txt").read_text(encoding="utf-8"), "new b")

    def test_startup_recovers_both_sides_of_manifest_switch(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "runtime_context.BACKEND_TMP_DIR", Path(directory)
        ):
            session = session_files_dir("user", "session")
            (session / "result.txt").write_text("old", encoding="utf-8")
            begin_step_transaction("user", "session", "run-1", "step-1")
            step_root = workflow_step_dir("user", "session", "run-1", "step-1")
            metadata_path = step_root / "transaction.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            version = "a" * 32
            candidate = session / ".versions" / version
            candidate.mkdir(parents=True)
            (candidate / "result.txt").write_text("partial", encoding="utf-8")
            metadata.update({"status": "committing", "candidate_version": version,
                             "pending_receipt": {"status": "committed"}})
            _write_json(metadata_path, metadata)

            recover_workspace_transactions()
            self.assertFalse(candidate.exists())
            self.assertEqual((session_files_dir("user", "session") / "result.txt").read_text(), "old")
            self.assertEqual(json.loads(metadata_path.read_text())["status"], "begun")

            candidate.mkdir(parents=True)
            (candidate / "result.txt").write_text("new", encoding="utf-8")
            _write_json(metadata_path, metadata)
            _write_json(session / ".active_version.json", {"version": version})
            recover_workspace_transactions()
            self.assertEqual((session_files_dir("user", "session") / "result.txt").read_text(), "new")
            self.assertEqual(json.loads(metadata_path.read_text())["status"], "committed")

    def test_manifest_switch_succeeds_with_old_file_open_on_windows(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "runtime_context.BACKEND_TMP_DIR", Path(directory)
        ):
            session = session_files_dir("user", "session")
            (session / "result.txt").write_text("before", encoding="utf-8")
            begin_step_transaction("user", "session", "run-1", "step-1")
            step_root = workflow_step_dir("user", "session", "run-1", "step-1")
            (step_root / "staging" / "result.txt").write_text("after", encoding="utf-8")
            with (session / "result.txt").open("r", encoding="utf-8") as old_handle:
                commit_step_transaction("user", "session", "run-1", "step-1")
                self.assertEqual(old_handle.read(), "before")
                self.assertEqual(
                    (session_files_dir("user", "session") / "result.txt").read_text(), "after"
                )


if __name__ == "__main__":
    unittest.main()
