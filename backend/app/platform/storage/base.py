from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol


class StorageProviderError(RuntimeError):
    pass


class StorageUnavailableError(StorageProviderError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str


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

    async def delete_object(self, *, key: str) -> None: ...

    async def create_signed_read_url(
        self,
        *,
        key: str,
        expires_in_seconds: int,
    ) -> str: ...
