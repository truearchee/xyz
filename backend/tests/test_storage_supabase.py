from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.platform.storage import supabase as supabase_storage
from app.platform.storage.base import StorageProviderError


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
