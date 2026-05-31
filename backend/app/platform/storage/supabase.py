from __future__ import annotations

import asyncio
import inspect
from typing import Any, BinaryIO

from app.platform.config import settings
from app.platform.storage.base import (
    StorageProviderError,
    StorageUnavailableError,
    StoredObject,
)
from app.platform.supabase_client import get_supabase_admin_client


class SupabaseStorageProvider:
    def __init__(self, *, bucket_name: str) -> None:
        self.bucket_name = bucket_name

    async def _bucket(self) -> Any:
        client = await get_supabase_admin_client()
        return client.storage.from_(self.bucket_name)

    async def put_object(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str,
        content_length: int,
        metadata: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredObject:
        try:
            content.seek(0)
            data = await asyncio.to_thread(content.read)
            bucket = await self._bucket()
            await bucket.upload(
                key,
                data,
                {
                    "content-type": content_type,
                    "upsert": "true" if overwrite else "false",
                    "metadata": metadata or {},
                },
            )
        except (TimeoutError, ConnectionError) as exc:
            raise StorageUnavailableError("Storage provider unavailable") from exc
        except Exception as exc:
            raise StorageProviderError("Storage provider upload failed") from exc

        return StoredObject(key=key, size=content_length, content_type=content_type)

    async def delete_object(self, *, key: str) -> None:
        try:
            bucket = await self._bucket()
            await bucket.remove([key])
        except Exception:
            return

    async def create_signed_read_url(
        self,
        *,
        key: str,
        expires_in_seconds: int,
    ) -> str:
        try:
            bucket = await self._bucket()
            create_signed_url = bucket.create_signed_url
            if inspect.iscoroutinefunction(create_signed_url):
                response = await create_signed_url(key, expires_in_seconds)
            else:
                response = await asyncio.to_thread(
                    create_signed_url,
                    key,
                    expires_in_seconds,
                )
            if inspect.isawaitable(response):
                response = await response
        except (TimeoutError, ConnectionError) as exc:
            raise StorageUnavailableError("Storage provider unavailable") from exc
        except Exception as exc:
            raise StorageProviderError("Storage provider signed URL failed") from exc

        if isinstance(response, dict):
            signed_url = response.get("signedURL") or response.get("signed_url")
            if signed_url:
                return str(signed_url)
        signed_url = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
        if signed_url:
            return str(signed_url)
        raise StorageProviderError("Storage provider signed URL response was invalid")


_storage_provider: SupabaseStorageProvider | None = None


async def get_storage_provider() -> SupabaseStorageProvider:
    global _storage_provider
    if _storage_provider is None:
        _storage_provider = SupabaseStorageProvider(
            bucket_name=settings.SUPABASE_STORAGE_BUCKET,
        )
    return _storage_provider
