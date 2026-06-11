from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from typing import Any, BinaryIO
from urllib.parse import urlsplit, urlunsplit

from app.platform.config import settings
from app.platform.storage.base import (
    ListedObject,
    StorageObjectNotFoundError,
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
            if _looks_like_not_found(str(exc)):
                raise StorageObjectNotFoundError(f"Storage object not found: {key}") from exc
            raise StorageProviderError("Storage provider read failed") from exc

        error = _storage_response_error(response)
        if error is not None:
            if _looks_like_not_found(error):
                raise StorageObjectNotFoundError(f"Storage object not found: {key}")
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

    async def list_objects(self, *, prefix: str, max_objects: int) -> list[ListedObject]:
        # Supabase `.list()` is non-recursive (one "folder" level) + paginated, so walk the prefix tree.
        bucket = await self._bucket()
        results: list[ListedObject] = []
        await self._walk(bucket, prefix.strip("/"), results, max_objects)
        return results

    async def _walk(
        self, bucket: Any, path: str, results: list[ListedObject], max_objects: int
    ) -> None:
        if len(results) >= max_objects:
            return
        offset = 0
        page = 100
        while len(results) < max_objects:
            entries = await self._list_page(bucket, path, limit=page, offset=offset)
            if not entries:
                break
            for entry in entries:
                if len(results) >= max_objects:
                    return
                name = entry.get("name")
                if not name:
                    continue
                full = f"{path}/{name}" if path else name
                if entry.get("id") is None:  # a "folder" placeholder → recurse
                    await self._walk(bucket, full, results, max_objects)
                else:
                    results.append(
                        ListedObject(
                            key=full,
                            created_at=_parse_listed_created_at(entry),
                            size=_listed_size(entry),
                        )
                    )
            if len(entries) < page:
                break
            offset += page

    async def _list_page(
        self, bucket: Any, path: str, *, limit: int, offset: int
    ) -> list[dict]:
        try:
            list_fn = bucket.list
            options = {"limit": limit, "offset": offset}
            if inspect.iscoroutinefunction(list_fn):
                response = await list_fn(path, options)
            else:
                response = await asyncio.to_thread(list_fn, path, options)
            if inspect.isawaitable(response):
                response = await response
        except (TimeoutError, ConnectionError) as exc:
            raise StorageUnavailableError("Storage provider unavailable") from exc
        except Exception as exc:
            raise StorageProviderError("Storage provider list failed") from exc
        if isinstance(response, list):
            return [entry for entry in response if isinstance(entry, dict)]
        return []

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


def _parse_listed_created_at(entry: dict) -> datetime:
    raw = entry.get("created_at") or entry.get("updated_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def _listed_size(entry: dict) -> int:
    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        size = metadata.get("size")
        if isinstance(size, int):
            return size
    return 0


def _looks_like_not_found(text: str) -> bool:
    lowered = text.lower()
    return (
        "not found" in lowered
        or "not_found" in lowered
        or "no such key" in lowered
        or "nosuchkey" in lowered
        or "404" in lowered
    )


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
