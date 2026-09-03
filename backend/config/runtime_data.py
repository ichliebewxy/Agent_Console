"""Copy legacy indexes into tmp once, without deleting the original data."""
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = PROJECT_ROOT / "tmp"


def migrate_file(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file() and not destination.exists():
        # Exclusive creation makes repeated startups non-destructive.
        try:
            with destination.open("xb") as output, source.open("rb") as original:
                shutil.copyfileobj(original, output)
        except FileExistsError:
            pass
    return destination


def configure_caches() -> None:
    cache_dir = TMP_ROOT / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for variable in ("TMP", "TEMP", "TMPDIR"):
        os.environ[variable] = str(cache_dir)
    os.environ.setdefault("HF_HOME", str(TMP_ROOT / "huggingface"))


def migrate_knowledge() -> None:
    for filename in ("bm25_state.json", "parent_chunks.json"):
        migrate_file(PROJECT_ROOT / "data" / filename, TMP_ROOT / "knowledge" / filename)
    source_dir = PROJECT_ROOT / "data" / "documents"
    if source_dir.is_dir():
        for source in source_dir.iterdir():
            if source.is_file():
                migrate_file(source, TMP_ROOT / "knowledge" / "documents" / source.name)
