from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePath
import re
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from fastapi import UploadFile


PDF_MIME_TYPE = "application/pdf"
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_FILENAME_LENGTH = 255
_CHUNK_SIZE = 1024 * 1024


class InvalidPdfError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    content: BinaryIO
    file_name: str
    mime_type: str
    file_size: int
    checksum_sha256: str


def sanitize_filename(file_name: str | None) -> str:
    candidate = PurePath(file_name or "upload.pdf").name
    candidate = _CONTROL_CHARS.sub("", candidate).strip()
    if not candidate:
        candidate = "upload.pdf"
    if len(candidate) > _MAX_FILENAME_LENGTH:
        if "." in candidate:
            stem, suffix = candidate.rsplit(".", 1)
            max_stem = max(1, _MAX_FILENAME_LENGTH - len(suffix) - 1)
            candidate = f"{stem[:max_stem]}.{suffix}"
        else:
            candidate = candidate[:_MAX_FILENAME_LENGTH]
    return candidate


async def spool_and_validate_pdf(
    upload: UploadFile,
    *,
    max_bytes: int,
) -> ValidatedUpload:
    buffer = SpooledTemporaryFile(max_size=max_bytes)
    total = 0
    sha256 = hashlib.sha256()

    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            buffer.close()
            raise UploadTooLargeError("Uploaded file exceeds the configured size limit")
        sha256.update(chunk)
        buffer.write(chunk)

    if total <= 0:
        buffer.close()
        raise InvalidPdfError("Uploaded file is empty")

    buffer.seek(0)
    if buffer.read(5) != b"%PDF-":
        buffer.close()
        raise InvalidPdfError("Uploaded file is not a PDF")

    buffer.seek(0)
    return ValidatedUpload(
        content=buffer,
        file_name=sanitize_filename(upload.filename),
        mime_type=PDF_MIME_TYPE,
        file_size=total,
        checksum_sha256=sha256.hexdigest(),
    )
