from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.storage import supabase as supabase_storage
from app.platform.storage.base import StorageProviderError, StorageUnavailableError


class _FakeStorage:
    def __init__(self, bucket) -> None:
        self.bucket = bucket

    def from_(self, bucket_name: str):
        assert bucket_name == "transcripts"
        return self.bucket


def _patch_supabase_client(monkeypatch: pytest.MonkeyPatch, bucket) -> None:
    async def fake_client():
        return SimpleNamespace(storage=_FakeStorage(bucket))

    monkeypatch.setattr(supabase_storage, "get_supabase_admin_client", fake_client)


@pytest.mark.anyio
async def test_supabase_delete_object_raises_when_remove_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingBucket:
        def __init__(self) -> None:
            self.remove_calls: list[list[str]] = []

        async def remove(self, keys: list[str]):
            self.remove_calls.append(keys)
            raise RuntimeError("supabase delete failed")

    bucket = FailingBucket()
    _patch_supabase_client(monkeypatch, bucket)
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    with pytest.raises(StorageProviderError):
        await provider.delete_object(key="modules/section/transcripts/file.vtt")

    assert bucket.remove_calls == [["modules/section/transcripts/file.vtt"]]


@pytest.mark.anyio
async def test_supabase_get_object_returns_downloaded_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bucket:
        def __init__(self) -> None:
            self.download_calls: list[str] = []

        async def download(self, key: str):
            self.download_calls.append(key)
            return b"WEBVTT\n"

    bucket = Bucket()
    _patch_supabase_client(monkeypatch, bucket)
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    assert await provider.get_object(key="modules/section/transcripts/file.vtt") == b"WEBVTT\n"
    assert bucket.download_calls == ["modules/section/transcripts/file.vtt"]


@pytest.mark.anyio
async def test_supabase_get_object_raises_unavailable_for_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bucket:
        async def download(self, key: str):
            raise ConnectionError("down")

    _patch_supabase_client(monkeypatch, Bucket())
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    with pytest.raises(StorageUnavailableError):
        await provider.get_object(key="modules/section/transcripts/file.vtt")


@pytest.mark.anyio
async def test_supabase_delete_object_raises_when_remove_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ErrorBucket:
        def __init__(self) -> None:
            self.remove_calls: list[list[str]] = []

        async def remove(self, keys: list[str]):
            self.remove_calls.append(keys)
            return {"statusCode": 500, "message": "delete failed"}

    bucket = ErrorBucket()
    _patch_supabase_client(monkeypatch, bucket)
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    with pytest.raises(StorageProviderError):
        await provider.delete_object(key="modules/section/transcripts/file.vtt")

    assert bucket.remove_calls == [["modules/section/transcripts/file.vtt"]]


@pytest.mark.anyio
async def test_supabase_signed_url_rewrites_internal_origin_to_public_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bucket:
        async def create_signed_url(self, key: str, expires_in_seconds: int):
            assert key == "modules/section/transcripts/file.vtt"
            assert expires_in_seconds == 300
            return {
                "signedURL": (
                    "http://host.docker.internal:54321/storage/v1/object/sign/"
                    "transcripts/modules/section/transcripts/file.vtt"
                    "?token=abc.def&download=1"
                )
            }

    monkeypatch.setenv("SUPABASE_URL", "http://host.docker.internal:54321")
    monkeypatch.setenv("SUPABASE_PUBLIC_URL", "http://127.0.0.1:54321")
    _patch_supabase_client(monkeypatch, Bucket())
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    signed_url = await provider.create_signed_read_url(
        key="modules/section/transcripts/file.vtt",
        expires_in_seconds=300,
    )

    assert signed_url == (
        "http://127.0.0.1:54321/storage/v1/object/sign/"
        "transcripts/modules/section/transcripts/file.vtt"
        "?token=abc.def&download=1"
    )


@pytest.mark.anyio
async def test_supabase_signed_url_remains_unchanged_without_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bucket:
        async def create_signed_url(self, key: str, expires_in_seconds: int):
            return SimpleNamespace(
                signed_url=(
                    "http://host.docker.internal:54321/storage/v1/object/sign/"
                    "transcripts/modules/section/transcripts/file.vtt?token=abc.def"
                )
            )

    monkeypatch.setenv("SUPABASE_URL", "http://host.docker.internal:54321")
    monkeypatch.delenv("SUPABASE_PUBLIC_URL", raising=False)
    _patch_supabase_client(monkeypatch, Bucket())
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    signed_url = await provider.create_signed_read_url(
        key="modules/section/transcripts/file.vtt",
        expires_in_seconds=300,
    )

    assert signed_url == (
        "http://host.docker.internal:54321/storage/v1/object/sign/"
        "transcripts/modules/section/transcripts/file.vtt?token=abc.def"
    )


@pytest.mark.anyio
async def test_supabase_signed_url_remains_unchanged_when_public_url_matches_internal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bucket:
        async def create_signed_url(self, key: str, expires_in_seconds: int):
            return {
                "signedURL": (
                    "http://host.docker.internal:54321/storage/v1/object/sign/"
                    "transcripts/modules/section/transcripts/file.vtt?token=abc.def"
                )
            }

    monkeypatch.setenv("SUPABASE_URL", "http://host.docker.internal:54321")
    monkeypatch.setenv("SUPABASE_PUBLIC_URL", "http://host.docker.internal:54321")
    _patch_supabase_client(monkeypatch, Bucket())
    provider = supabase_storage.SupabaseStorageProvider(bucket_name="transcripts")

    signed_url = await provider.create_signed_read_url(
        key="modules/section/transcripts/file.vtt",
        expires_in_seconds=300,
    )

    assert signed_url == (
        "http://host.docker.internal:54321/storage/v1/object/sign/"
        "transcripts/modules/section/transcripts/file.vtt?token=abc.def"
    )
