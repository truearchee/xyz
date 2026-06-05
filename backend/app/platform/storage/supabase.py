from __future__ import annotations

import asyncio
import inspect
from typing import Any, BinaryIO
from urllib.parse import urlsplit, urlunsplit

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

    async def get_object(self, *, key: str) -> bytes:
        try:
            bucket = await self._bucket()
            download = bucket.download
            if inspect.iscoroutinefunction(download):
                response = await download(key)
            else:
                response = await asyncio.to_thread(download, key)
            if inspect.isawaitable(response):
                response = await response
        except (TimeoutError, ConnectionError) as exc:
            raise StorageUnavailableError("Storage provider unavailable") from exc
        except Exception as exc:
            raise StorageProviderError("Storage provider read failed") from exc

        error = _storage_response_error(response)
        if error is not None:
            raise StorageProviderError(f"Storage provider read failed: {error}")
        return _storage_response_bytes(response)

    async def delete_object(self, *, key: str) -> None:
        try:
            bucket = await self._bucket()
            remove = bucket.remove
            if inspect.iscoroutinefunction(remove):
                response = await remove([key])
            else:
                response = await asyncio.to_thread(remove, [key])
            if inspect.isawaitable(response):
                response = await response
        except (TimeoutError, ConnectionError) as exc:
            raise StorageUnavailableError("Storage provider unavailable") from exc
        except Exception as exc:
            raise StorageProviderError("Storage provider delete failed") from exc

        error = _storage_response_error(response)
        if error is not None:
            raise StorageProviderError(f"Storage provider delete failed: {error}")

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
                return _rewrite_signed_url_origin(str(signed_url))
        signed_url = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
        if signed_url:
            return _rewrite_signed_url_origin(str(signed_url))
        raise StorageProviderError("Storage provider signed URL response was invalid")


_storage_provider: SupabaseStorageProvider | None = None


async def get_storage_provider() -> SupabaseStorageProvider:
    global _storage_provider
    if _storage_provider is None:
        _storage_provider = SupabaseStorageProvider(
            bucket_name=settings.SUPABASE_STORAGE_BUCKET,
        )
    return _storage_provider


def _storage_response_error(response: Any) -> str | None:
    if isinstance(response, dict):
        error = response.get("error")
        if error:
            return str(error)
        status_code = response.get("statusCode") or response.get("status_code")
        if isinstance(status_code, int) and status_code >= 400:
            return str(response.get("message") or status_code)
    error = getattr(response, "error", None)
    if error:
        return str(error)
    status_code = getattr(response, "status_code", None) or getattr(response, "statusCode", None)
    if isinstance(status_code, int) and status_code >= 400:
        return str(getattr(response, "message", status_code))
    return None


def _rewrite_signed_url_origin(signed_url: str) -> str:
    internal_url = settings.SUPABASE_URL.rstrip("/")
    public_url = settings.SUPABASE_PUBLIC_URL.rstrip("/")
    if public_url == internal_url:
        return signed_url

    parsed_signed_url = urlsplit(signed_url)
    parsed_internal_url = urlsplit(internal_url)
    parsed_public_url = urlsplit(public_url)
    if (
        parsed_signed_url.scheme,
        parsed_signed_url.netloc,
    ) != (
        parsed_internal_url.scheme,
        parsed_internal_url.netloc,
    ):
        return signed_url

    return urlunsplit(
        (
            parsed_public_url.scheme,
            parsed_public_url.netloc,
            parsed_signed_url.path,
            parsed_signed_url.query,
            parsed_signed_url.fragment,
        )
    )


def _storage_response_bytes(response: Any) -> bytes:
    if isinstance(response, bytes):
        return response
    if isinstance(response, bytearray):
        return bytes(response)
    if isinstance(response, memoryview):
        return response.tobytes()
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, bytes):
            return data
        if isinstance(data, bytearray):
            return bytes(data)
        if isinstance(data, memoryview):
            return data.tobytes()
    data = getattr(response, "data", None)
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    raise StorageProviderError("Storage provider read response was invalid")
