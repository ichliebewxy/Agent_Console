"""Browse folders on the host where the agent service runs."""
import os
from pathlib import Path
from string import ascii_uppercase

from settings import PROJECT_ROOT


def list_local_folders(path: str | None = None) -> dict:
    if path is not None and ("\x00" in path or len(path) > 4096):
        raise ValueError("无效的文件夹路径。")
    root = Path(path).expanduser() if path else PROJECT_ROOT
    if not root.is_absolute():
        raise ValueError("请填写绝对路径。")
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("文件夹不存在或无法访问。")
    directories = []
    with os.scandir(root) as entries:
        for entry in entries:
            try:
                if entry.is_dir():
                    directories.append({"name": entry.name, "path": str(Path(entry.path).resolve())})
            except OSError:
                continue
    directories.sort(key=lambda row: row["name"].casefold())
    roots = [str(Path(f"{letter}:/")) for letter in ascii_uppercase if Path(f"{letter}:/").is_dir()] if os.name == "nt" else ["/"]
    return {
        "path": str(root),
        "parent": str(root.parent) if root.parent != root else None,
        "roots": roots,
        "directories": directories[:1000],
        "truncated": len(directories) > 1000,
    }
