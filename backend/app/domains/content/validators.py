from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePath
import re
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from fastapi import UploadFile


PDF_MIME_TYPE = "application/pdf"
NOTEBOOK_MIME_TYPE = "application/x-ipynb+json"
NOTEBOOK_ALLOWED_MIME_TYPES = {
    NOTEBOOK_MIME_TYPE,
    "application/json",
    "application/octet-stream",
}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_FILENAME_LENGTH = 255
_CHUNK_SIZE = 1024 * 1024
MAX_SECTION_NOTES_CHARACTERS = 5000


class InvalidPdfError(ValueError):
    pass


class InvalidSectionAssetError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


class SectionNotesTooLongError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedUpload:
    content: BinaryIO
    file_name: str
    mime_type: str
    file_size: int
    checksum_sha256: str
    asset_kind: str = "processable"
    storage_extension: str = ".pdf"


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
    content_type = _normalized_content_type(upload.content_type)
    if content_type and content_type != PDF_MIME_TYPE:
        raise InvalidPdfError("Uploaded file content type is not application/pdf")
    file_name = sanitize_filename(upload.filename)
    if PurePath(file_name).suffix.lower() != ".pdf":
        raise InvalidPdfError("Uploaded file extension is not .pdf")

    return await _spool_and_validate_pdf_content(upload, max_bytes=max_bytes, file_name=file_name)


async def spool_and_validate_section_asset(
    upload: UploadFile,
    *,
    max_bytes: int,
) -> ValidatedUpload:
    file_name = sanitize_filename(upload.filename)
    suffix = PurePath(file_name).suffix.lower()
    content_type = _normalized_content_type(upload.content_type)

    if suffix == ".pdf":
        if content_type != PDF_MIME_TYPE:
            raise InvalidPdfError("Uploaded file content type is not application/pdf")
        return await _spool_and_validate_pdf_content(
            upload,
            max_bytes=max_bytes,
            file_name=file_name,
        )

    if suffix == ".ipynb":
        if content_type not in NOTEBOOK_ALLOWED_MIME_TYPES:
            raise InvalidSectionAssetError("Notebook upload content type is not allowed")
        return await _spool_and_validate_notebook(
            upload,
            max_bytes=max_bytes,
            file_name=file_name,
        )

    raise InvalidSectionAssetError("Unsupported section asset file type")


async def _spool_and_validate_pdf_content(
    upload: UploadFile,
    *,
    max_bytes: int,
    file_name: str,
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
        file_name=file_name,
        mime_type=PDF_MIME_TYPE,
        file_size=total,
        checksum_sha256=sha256.hexdigest(),
    )


async def _spool_and_validate_notebook(
    upload: UploadFile,
    *,
    max_bytes: int,
    file_name: str,
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
        raise InvalidSectionAssetError("Uploaded file is empty")

    buffer.seek(0)
    try:
        notebook = json.loads(buffer.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        buffer.close()
        raise InvalidSectionAssetError("Notebook upload is not valid JSON") from exc

    if not (
        isinstance(notebook, dict)
        and isinstance(notebook.get("cells"), list)
        and isinstance(notebook.get("metadata"), dict)
    ):
        buffer.close()
        raise InvalidSectionAssetError("Notebook upload is not a valid ipynb document")

    buffer.seek(0)
    return ValidatedUpload(
        content=buffer,
        file_name=file_name,
        mime_type=NOTEBOOK_MIME_TYPE,
        file_size=total,
        checksum_sha256=sha256.hexdigest(),
        asset_kind="attachment",
        storage_extension=".ipynb",
    )


def _normalized_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def normalize_section_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    normalized = notes.replace("\r\n", "\n").replace("\r", "\n").strip()
    if normalized == "":
        return None
    if len(normalized) > MAX_SECTION_NOTES_CHARACTERS:
        raise SectionNotesTooLongError("Section notes exceed the configured limit")
    return normalized
