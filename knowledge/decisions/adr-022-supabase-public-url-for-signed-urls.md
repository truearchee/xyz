---
type: adr
stage: 04
status: accepted
created: 2026-06-03
updated: 2026-06-03 20:05
related-session: knowledge/specs/stage-04/4.3.5a-client-edge-tracer-bullet.md
---

# ADR-022 - Supabase Public URL for Signed URLs

## Linked documents
- Spec: [[specs/stage-04/4.3.5a-client-edge-tracer-bullet]]
- Report: [[4.3.5a-client-edge-tracer-final-report]]
- Fixture report: [[archive/stage-04/4.3.5a/4.3.5a-e2e-fixtures]]

## Decision
Backend services keep using `SUPABASE_URL` as the internal Supabase API base URL. Storage signed URLs returned to browsers may use an optional `SUPABASE_PUBLIC_URL` as their origin.

When `SUPABASE_PUBLIC_URL` is unset, it defaults to `SUPABASE_URL`. When it differs, the storage provider rewrites only the signed URL origin from `SUPABASE_URL` to `SUPABASE_PUBLIC_URL`. The path, query string, token, and fragment are preserved exactly.

## Rationale
Local Dockerized backend services can reach local Supabase through `host.docker.internal`, but the host browser cannot resolve that hostname. The browser can reach local Supabase at `127.0.0.1`. Signed URLs are bearer URLs intended for browser consumption, so their origin must be browser-openable while the backend can still call Supabase through its container-reachable URL.

## Consequences
This does not change storage-key generation, bucket privacy, JWT issuer validation, JWKS configuration, uploads, or downloads performed by the backend. Production behavior remains unchanged unless `SUPABASE_PUBLIC_URL` is explicitly set.
