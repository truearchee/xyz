from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol


class StorageProviderError(RuntimeError):
    pass


class StorageUnavailableError(StorageProviderError):
    pass


class StorageObjectNotFoundError(StorageProviderError):
    """The requested object key does not exist in the bucket (404).

    Distinct from ``StorageUnavailableError`` (transient) — a missing raw transcript file is a
    terminal ``storage_missing`` condition (Stage 4.6 failure taxonomy), the same condition
    reconciliation reports; it must not be buried under a generic parse failure.
    """

    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str


@dataclass(frozen=True)
class ListedObject:
    """A bucket object as seen by storage reconciliation (Stage 4.6c). ``created_at`` drives the
    orphan grace window — an object younger than the window is indistinguishable from an in-flight upload."""

    key: str
    created_at: datetime
    size: int


class StorageProvider(Protocol):
    async def put_object(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str,
        content_length: int,
        metadata: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredObject: ...

    async def get_object(self, *, key: str) -> bytes: ...

    async def delete_object(self, *, key: str) -> None: ...

    async def list_objects(
        self,
        *,
        prefix: str,
        max_objects: int,
    ) -> list["ListedObject"]: ...

    async def create_signed_read_url(
        self,
        *,
        key: str,
        expires_in_seconds: int,
    ) -> str: ...
