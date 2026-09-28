"""Atomic active-version pointer for document ingestion and retrieval."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "document_versions.sqlite3"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def version_chunk_prefix(filename: str, version: str) -> str:
    return f"v{version}::" if version else f"{filename}::"


def _like_prefix(prefix: str) -> str:
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return _quote(escaped + "%")


def version_filter(filename: str, version: str) -> str:
    return (
        f"(filename == {_quote(filename)} and "
        f"chunk_id like {_like_prefix(version_chunk_prefix(filename, version))})"
    )


class DocumentVersionStore:
    """The pointer changes only after all stores contain a complete new version."""

    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = path

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS active_documents "
                    "(filename TEXT PRIMARY KEY, version TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS pending_document_cleanup "
                    "(filename TEXT NOT NULL, version TEXT NOT NULL, "
                    "PRIMARY KEY (filename, version))"
                )
                yield connection
        finally:
            connection.close()

    def prepare(self, filename: str) -> str:
        """Register a legacy pointer before any new rows become searchable."""
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO active_documents (filename, version) VALUES (?, '')",
                (filename,),
            )
            row = connection.execute(
                "SELECT version FROM active_documents WHERE filename = ?", (filename,)
            ).fetchone()
            return row[0]

    def activate(self, filename: str, version: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE active_documents SET version = ? WHERE filename = ?",
                (version, filename),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Document version pointer was not prepared")

    def active_version(self, filename: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version FROM active_documents WHERE filename = ?", (filename,)
            ).fetchone()
            return row[0] if row else None

    def remove(self, filename: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM active_documents WHERE filename = ?", (filename,))
            connection.execute("DELETE FROM pending_document_cleanup WHERE filename = ?", (filename,))

    def mark_cleanup(self, filename: str, version: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO pending_document_cleanup (filename, version) VALUES (?, ?)",
                (filename, version),
            )

    def clear_cleanup(self, filename: str, version: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM pending_document_cleanup WHERE filename = ? AND version = ?",
                (filename, version),
            )

    def pending_cleanup(self, filename: str) -> list[str]:
        with self._connect() as connection:
            return [
                row[0] for row in connection.execute(
                    "SELECT version FROM pending_document_cleanup WHERE filename = ?",
                    (filename,),
                )
            ]

    def active_filter(self) -> str:
        with self._connect() as connection:
            rows = connection.execute("SELECT filename, version FROM active_documents").fetchall()
        return " and ".join(
            f"(filename != {_quote(filename)} or "
            f"chunk_id like {_like_prefix(version_chunk_prefix(filename, version))})"
            for filename, version in rows
        )
