import pytest

from backend.services.upload_security import (
    UploadTooLargeError,
    UploadValidationError,
    content_sha256,
    normalize_upload_filename,
    validate_upload_size,
)


def test_normalize_upload_filename_rejects_path_traversal():
    with pytest.raises(UploadValidationError):
        normalize_upload_filename("../secret.txt")


def test_normalize_upload_filename_accepts_supported_extension():
    assert normalize_upload_filename("制度文档.PDF") == "制度文档.PDF"


def test_validate_upload_size_rejects_empty_and_oversized_payloads():
    with pytest.raises(UploadValidationError):
        validate_upload_size(b"")

    with pytest.raises(UploadTooLargeError):
        validate_upload_size(b"abc", max_bytes=2)


def test_content_sha256_is_stable():
    assert content_sha256(b"hello") == content_sha256(b"hello")
    assert content_sha256(b"hello") != content_sha256(b"world")
