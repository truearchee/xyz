---
type: adr
stage: "4.8"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.8-first-hosted-deploy-staging.md
---

# ADR-040 — Staging compute topology: Fly.io (spec Decision A1)

> Spec label "Decision A1". Locked in the spec §4; recorded here BEFORE code per the
> ADR-before-code rule.

## Linked documents
- Spec: [[specs/stage-04/4.8-first-hosted-deploy-staging]]
- Related: [[adr-041-staging-db-supabase-dual-url]] (DB lives in Supabase, not on Fly), [[adr-042-browser-backend-transport-direct]] (Fly gives direct, non-buffering ingress), [[adr-043-sse-proxy-probe]] (the probe validates Fly's edge does not buffer)

## Context
Stage 4.8 is a **constraint-discovery** deploy whose headline forcing function is "SSE dies under
buffering proxies, and finding that out in Stage 8.3 is expensive." The compute platform must
therefore (a) run the *same* Docker images we run locally — backend API + three separate RQ worker
groups (`ingestion`/default, `embedding`, `ai`) + the Next frontend — so the test is faithful, and
(b) not insert a buffering hop into the streaming path. It must also support a **release-phase
migration** that gates app start and aborts the deploy on non-zero exit (migrations never run on
boot — deliberate locally, fatal if forgotten hosted).

## Decision
- **Fly.io** for all compute. One app (or app-per-role) with **process groups** mapping 1:1 to the
  existing `docker-compose.yml` `command:` split: `api` (uvicorn), `worker` (default/ingestion),
  `embedding_worker`, `ai_worker`, `frontend`. The single baked backend image serves api + all three
  workers (differentiated by command), exactly as compose does today.
- Use Fly's **`release_command`** to run `alembic upgrade head` over the direct DB URL before any
  process group starts; a non-zero exit **aborts** the release.
- The **embedding** process group is sized larger (torch + MiniLM is hundreds of MB resident);
  api/worker/ai stay small. CPU-only torch is already baked (`backend/Dockerfile`).
- **Escape hatch (A2):** if Fly cost/availability blocks, fall back to a VPS + docker-compose + Caddy
  (highest fidelity — same compose file — at the cost of owning the proxy). A3 (Render/Railway) is
  **rejected**: their proxy buffering quirks undercut the SSE-discovery purpose of the stage.

## Consequences
- Frontend `NEXT_PUBLIC_*` is build-time inlined → a **staging-tagged** frontend image is required
  (see ADR-042); the API URL cannot be injected at runtime.
- Fly's default ingress does not buffer `text/event-stream`, which is what ADR-043's probe verifies
  from the staging browser — keeping the SSE de-risk honest rather than assumed.
- Process-group start ordering must respect the release gate: workers crashloop against a schema-less
  DB if they precede the migration; the deploy script asserts the gate.
- Provisioning the Fly app + secrets is a **developer/ops action** ("you provision, I build"); this
  repo carries the `fly.toml`, deploy script, and runbook that make it repeatable.
