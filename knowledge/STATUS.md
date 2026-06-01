# Status

_Last updated: 2026-06-01 15:03 — Session 4.2 transcript parse worker accepted_

## Current focus
Session 4.2 (Worker: Parse VTT/TXT into Segments) is accepted/done. Verification passed for backend/worker build and restart, Alembic `0005`, targeted parser/worker/transcript/storage/DB tests, full backend tests, frontend type-checking, and `git diff --check`.

## Done recently
- Session 4.2: RQ ingestion worker parses VTT/TXT raw transcript objects into immutable `transcript_segments`, records idempotent `parse` jobs in `ingestion_jobs`, and leaves successful transcripts at `parsing`; backend `106 passed`, targeted `37 passed`, frontend type-check passed, and `git diff --check` passed — completed 2026-06-01 15:03
- Session 4.1: assigned lecturer VTT/TXT transcript upload and active transcript read accepted after Docker verification; backend `83 passed`, transcript `11 passed`, frontend type-check passed, and `git diff --check` passed — completed 2026-06-01 00:21
- Session 3.3: student published-section visibility and signed read URL authorization accepted after Docker verification; final closeout rerun passed with backend `72 passed`, content `20 passed`, frontend type-check passed, and `git diff --check` passed — completed 2026-05-31 18:45; reverified 2026-05-31 19:09
- Session 3.2: publish/unpublish and lecturer notes accepted after Docker verification; backend `69 passed`, content `17 passed`, frontend type-check passed, and ADRs 009-011 captured the locked decisions — completed 2026-05-31 14:36
- Session 3.1: file upload/list/replace accepted after Docker verification; backend `65 passed`, content `13 passed`, frontend type-check passed, and codegen now trims generated TypeScript trailing blank EOF lines — completed 2026-05-31 00:06
- Session 2.4: DB-backed module access guard, participant module endpoints, generated module API client, typed module views — completed 2026-05-30 12:24

## In progress
- None.

## Next up
- Session 4.3: chunking should consume completed parse `ingestion_jobs`, not treat `transcripts.status='parsing'` as an action trigger.

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Real Supabase Storage writes, signed read URLs, and transcript raw-object writes are behind `StorageProvider` but not live-tested against Supabase; automated tests use fake storage.
- Replace/upload cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
- Raw transcript files are private and not exposed; future summary/transcript surfaces must continue to avoid exposing raw storage keys.
- Transcript parse recovery is intentionally deferred to Session 4.6: enqueue failure can leave `uploaded`, and mid-parse crash can leave `parsing` plus a `running` job.
