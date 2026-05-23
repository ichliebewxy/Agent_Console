from __future__ import annotations

import hashlib
from pathlib import PurePosixPath, PureWindowsPath


DEFAULT_ALLOWED_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
)
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class UploadValidationError(ValueError):
    pass


class UploadTooLargeError(UploadValidationError):
    pass


def normalize_upload_filename(
    filename: str | None,
    allowed_extensions: tuple[str, ...] = DEFAULT_ALLOWED_EXTENSIONS,
) -> str:
    raw = (filename or "").strip()
    if not raw:
        raise UploadValidationError("文件名不能为空")

    posix_name = PurePosixPath(raw).name
    windows_name = PureWindowsPath(raw).name
    if raw != posix_name or raw != windows_name:
        raise UploadValidationError("文件名不能包含路径")

    if raw in {".", ".."} or any(ord(char) < 32 for char in raw):
        raise UploadValidationError("文件名包含非法字符")

    suffix = PurePosixPath(raw).suffix.lower()
    if suffix not in allowed_extensions:
        raise UploadValidationError(f"不支持的文件格式。仅支持: {', '.join(allowed_extensions)}")

    return raw


def validate_upload_size(content: bytes, max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
    if not content:
        raise UploadValidationError("上传文件不能为空")
    if len(content) > max_bytes:
        raise UploadTooLargeError(f"文件大小不能超过 {max_bytes // (1024 * 1024)}MB")


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
