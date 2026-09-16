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
    begin_step_transaction,
    commit_step_transaction,
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
            self.assertEqual((session / "result.txt").read_text(encoding="utf-8"), "after")
            self.assertEqual(receipt["status"], "committed")

            rollback_step_transaction("user", "session", "run-1", "step-1")
            self.assertEqual((session / "result.txt").read_text(encoding="utf-8"), "before")

            recovered = begin_step_transaction("user", "session", "run-1", "step-1")
            self.assertEqual(recovered["snapshot_id"], started["snapshot_id"])
            self.assertEqual(
                (step_root / "staging" / "result.txt").read_text(encoding="utf-8"),
                "after",
            )


if __name__ == "__main__":
    unittest.main()
