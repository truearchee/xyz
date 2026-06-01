from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import re
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from fastapi import UploadFile


TRANSCRIPT_VTT_MIME_TYPE = "text/vtt"
TRANSCRIPT_TXT_MIME_TYPE = "text/plain"
_CHUNK_SIZE = 1024 * 1024
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
_MAX_SAFE_FILENAME_LENGTH = 200
_MAX_DISPLAY_FILENAME_LENGTH = 255


class InvalidTranscriptError(ValueError):
    pass


class TranscriptUploadTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedTranscriptUpload:
    content: BinaryIO
    original_file_name: str
    safe_file_name: str
    effective_mime_type: str
    size_bytes: int
    sha256: str


def sanitize_display_filename(file_name: str | None, *, fallback: str = "transcript.txt") -> str:
    candidate = _CONTROL_CHARS.sub("", file_name or "").strip()
    if not candidate:
        candidate = fallback
    if len(candidate) > _MAX_DISPLAY_FILENAME_LENGTH:
        candidate = candidate[:_MAX_DISPLAY_FILENAME_LENGTH]
    return candidate


def sanitize_storage_filename(file_name: str | None, *, extension: str) -> str:
    normalized = (file_name or "").replace("\\", "/")
    candidate = PurePosixPath(normalized).name
    candidate = _CONTROL_CHARS.sub("", candidate)
    candidate = _WHITESPACE.sub(" ", candidate).strip()
    if candidate in {"", ".", ".."}:
        candidate = f"transcript.{extension}"

    desired_suffix = f".{extension}"
    if not candidate.lower().endswith(desired_suffix):
        stem = candidate.rsplit(".", 1)[0] if "." in candidate else candidate
        candidate = f"{stem}.{extension}"
    if candidate[: -len(desired_suffix)].strip(" .") == "":
        candidate = f"transcript.{extension}"

    if len(candidate) > _MAX_SAFE_FILENAME_LENGTH:
        stem = candidate[: -len(desired_suffix)]
        max_stem = max(1, _MAX_SAFE_FILENAME_LENGTH - len(desired_suffix))
        candidate = f"{stem[:max_stem]}{desired_suffix}"
    return candidate


def _extension_from_filename(file_name: str | None) -> str:
    normalized = (file_name or "").replace("\\", "/")
    suffix = PurePosixPath(normalized).suffix.lower().lstrip(".")
    if suffix not in {"vtt", "txt"}:
        raise InvalidTranscriptError("Transcript file must be .vtt or .txt")
    return suffix


def _validate_content(*, extension: str, data: bytes) -> str:
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidTranscriptError("Transcript file must be valid UTF-8") from exc

    if extension == "vtt":
        if not decoded.lstrip().startswith("WEBVTT"):
            raise InvalidTranscriptError("VTT transcript must start with WEBVTT")
        return TRANSCRIPT_VTT_MIME_TYPE

    if decoded.strip() == "":
        raise InvalidTranscriptError("Transcript file is empty")
    return TRANSCRIPT_TXT_MIME_TYPE


async def spool_and_validate_transcript(
    upload: UploadFile,
    *,
    max_bytes: int,
) -> ValidatedTranscriptUpload:
    extension = _extension_from_filename(upload.filename)
    display_name = sanitize_display_filename(
        upload.filename,
        fallback=f"transcript.{extension}",
    )
    safe_name = sanitize_storage_filename(upload.filename, extension=extension)
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
            raise TranscriptUploadTooLargeError(
                "Uploaded transcript exceeds the configured size limit"
            )
        sha256.update(chunk)
        buffer.write(chunk)

    if total <= 0:
        buffer.close()
        raise InvalidTranscriptError("Transcript file is empty")

    buffer.seek(0)
    data = buffer.read()
    effective_mime_type = _validate_content(extension=extension, data=data)
    buffer.seek(0)
    return ValidatedTranscriptUpload(
        content=buffer,
        original_file_name=display_name,
        safe_file_name=safe_name,
        effective_mime_type=effective_mime_type,
        size_bytes=total,
        sha256=sha256.hexdigest(),
    )
