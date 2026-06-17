---
title: Stage 7b/7c — Glossary practice (Flashcards + Multiple-Choice)
status: fully-verified
updated: 2026-06-17
---

# Stage 7b/7c — Glossary practice (report)

Flashcards (7b) + Multiple-Choice (7c) over the student's already-saved terms. **No AI runs during
practice** (rule 15): MCQ samples distractors from the student's other in-scope terms; correctness is
on option identity.

## What was built

### Migration 0031 (`backend/alembic/versions/0031_glossary_practice.py`, down_revision `0030`)
`glossary_review_state` (per-entry Leitner box, denormalized student/subject for due scans),
`glossary_practice_sessions` (the entity `glossary_practice_completed` keys off; one active per mode via
partial-unique), `glossary_practice_answers` (one card/question per row; MCQ option identities
snapshotted in `distractor_entry_ids`). Round-trips. **Leaner than the Slice-6 four-table set** — no
AI-generated shareable question artifact, so a card maps 1:1 to an answer slot. No shared-CHECK edits.

### Models + engine
3 models registered in `__init__.py`. `domains/glossary/practice_service.py`:
- **Flashcards:** hardcoded Leitner `BOX_INTERVALS=[0,1,3,7,16,35]` days; `known` → box+1, streak+1;
  `not_known` → box reset; review state created lazily (`ON CONFLICT` on the per-entry unique).
- **MCQ (definition→term):** 4 options (1 correct + 3 distractors sampled from the student's OTHER
  in-scope generated terms); correctness on identity; **≥4-term minimum** (else 409
  `insufficient_terms`); "Don't know?" → `not_known`. Options shuffled per-card with a stable seed
  (`session.id:display_order`) so reload renders the identical question, position unpredictable.
- **Session lifecycle** mirrors quiz attempts: `start` (resume one-active-per-mode, build the deck,
  cap 20) → `answer` (grade + update review state; idempotent re-submit) → `complete` (counts +
  **`glossary_practice_completed` in the same txn**, idempotent re-complete). For `all` scope the event
  `module_id` = the first card's subject (deterministic; `student_activity_events.module_id` is NOT NULL).

### Endpoints (`api/routers/glossary.py`)
`GET …/practice/availability`, `POST …/practice/start`, `GET …/practice/{id}`,
`POST …/practice/{id}/answer`, `POST …/practice/{id}/complete`. Student-authed, owner-scoped 404.

### Thin UI (`frontend/src/features/glossary/`)
`PracticePage` (scope course/all + mode + availability + start/result), `FlashcardsSession` (flip card,
**keyboard ← / → AND on-screen rating row**, progress `n/total`, "study again" re-queues),
`MultipleChoiceSession` (**reuses the Stage 5 `mcq.tsx` components unchanged** — definition as question,
terms as options — + a "Don't know?" control). Route `/student/glossary/practice`; "Practice" link on
the glossary page. Client regenerated (`api.glossary.practice.*`); wrapper wired.

## Verification (evidence)
```
docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q
# 498 passed, 138 warnings in 138.35s   (492 after 7a; +6 practice tests)

# migration 0031 round-trip (base→head→base→head): test_db_spine::test_migration_round_trip — passed
# dev DB xyz_lms migrated to head 0031; dev-reseed pin bumped 0030→0031

cd frontend && npx tsc --noEmit   # exit 0

docker compose run --rm -e LLM_PROVIDER=k2think -e LLM_PROVIDER_BASE_URL=https://api.k2think.ai \
  -v "$PWD/backend:/app" -T backend python scripts/gate7_glossary_smoke.py
# PASS: response model echo MBZUAI-IFM/K2-Think-v2 == expected MBZUAI-IFM/K2-Think-v2;
# route cerebras; status_code 200; parseable BriefSummary definition; arabic-script present;
# finish_reason='length'

PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781717252-stage7 \
  npx playwright test tests/e2e/7-glossary.spec.ts --workers=1
# 1 passed (19.3s)

PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781717291-full \
  npx playwright test --workers=1
# 14 passed (3.2m)
```
New tests: `tests/test_glossary_practice.py` (flashcard known-advances/not-known-resets + completion
event + module_id; MCQ <4 unavailable + 409; MCQ correct/wrong/don't-know + counts; resume same session;
idempotent complete single event; practice personal-scoping 404).

## NOT done — remaining for Stage 7
- **7d** quiz-highlight. It is now unblocked because Stage 6 is closed.
- Low-priority follow-up: the real-provider glossary smoke returned `finish_reason='length'`; raise the
  glossary definition prompt `max_tokens` so real definitions do not truncate mid-sentence.

## Modified prior sessions
- **Stage 5.5** — `dev_reseed.py`: `EXPECTED_ALEMBIC_VERSION` `0030`→`0031`.
- **Stage 5** — `tests/conftest.py`: `TRUNCATE_TABLES` += the 3 practice tables.

## Linked documents
- Spec: [[specs/stage-07/7-glossary]] · 7a report: [[steps/stage-07/7a-glossary-foundation]]
- Findings: [[steps/findings-stage-07]]
- Decisions: [[decisions/adr-047-glossary-subject-folder-separation]], [[decisions/adr-048-glossary-definition-cache-collapse]]

## Change history
- 2026-06-17 — 7b/7c backend engine + UI built + verified (498 backend / 6 practice tests / migration
  0031 round-trip; frontend `tsc` exit 0). Live browser gate pending.
- 2026-06-17 21:40 — Stage 7 core gate closed: real-provider smoke passed with model echo
  `MBZUAI-IFM/K2-Think-v2` (route `cerebras`, `finish_reason='length'` follow-up opened), Stage 7
  browser gate passed, and full active E2E suite passed 14/14.
