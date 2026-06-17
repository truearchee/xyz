---
type: session-spec
stage: "06"
session: "6"
slug: complete-quiz-modes
status: approved        # draft → approved → in-progress → done → superseded
created: 2026-06-17
updated: 2026-06-17
owner: developer
plan: knowledge/plans/stage-06/6a-pool-foundation.md   # per-sub-session plans, first = 6a
report: ""              # per-sub-session reports under knowledge/steps/stage-06/
---

# Stage 6 — Complete Quiz Modes — Spec v2.1

> **Filed verbatim** from the developer's Spec v2.1 document (`.context/attachments/EFIbm3/`),
> reformatted only with this frontmatter + Linked-documents header per `dev-workflow.md`. Body preserved.

## Linked documents
- Spec (this, overview): [[specs/stage-06/6-complete-quiz-modes]]
- Sub-session specs: [[specs/stage-06/6a-pool-foundation]] (others filed as each sub-session opens)
- Sub-session plans: [[plans/stage-06/6a-pool-foundation]]
- Reports: filed under `knowledge/steps/stage-06/` as each sub-session closes
- Owner decisions D1–D4 confirmed 2026-06-17 (all spec-recommended path); see [[plans/stage-06/6a-pool-foundation]] §Locked decisions.

> Written from `knowledge/roadmap.md` v3.1 (Stage 6) + Design Plan §2.4.
> Prerequisite stages 5 and 5.5 are complete. Stage 7 (Glossary) is being built **in parallel** — read the coordination section before touching anything shared.

---

## Changelog v2 → v2.1 (read this first)

v2.1 does not change the architecture. It closes gaps where v2 promised a behavior with no data model or contract to implement it on. Every change below either (a) makes an existing promise buildable, or (b) names a failure/seam path v2 left implicit.

```
1. DATA MODEL ADDED (the big one). v2 promised recency bias, exhaustion
   recycling, "mistake stays in the bank," and prefix-flip-at-2 — but defined
   no per-student exposure store and no stable mistake identity for the pooled
   model. Added the durable PoolQuestion entity, a QuizQuestion.sourcePoolQuestionId
   linkage, exposure-via-the-linkage, and a concrete MistakeRecord upsert key.
   This single addition makes prereq #3, the sampling rules, and the retake
   mechanics actually implementable. (See "Data model" + hardened prereq #3.)
2. SNAPSHOT-AT-ASSEMBLY made explicit. Sampled questions are copied + shuffled
   into the attempt at assembly; pool invalidation/regeneration never mutates an
   in-progress or completed attempt. Protects score integrity (the 4.6 atomic-
   swap principle, applied to quizzes).
3. POOL-GENERATION FAILURE CONTRACT added. v2 covered stale-pool regen but not
   "generation fails while N students wait." Defined: validator-reject / 5xx →
   bounded RQ retry (rule 15) → terminal fail → waiters see a failure state +
   an idempotent retry that re-enqueues under the one-active lock. Multi-section:
   a terminally-failed section names itself; the quiz never hangs forever.
4. SECTION ELIGIBILITY pinned. Quiz scope includes ONLY lecture/lab sections
   with a completed detailed summary. Assignment/supplementary sections are
   NEVER quiz-eligible and are excluded SILENTLY — not surfaced as "processing"
   (which would dead-end Decision #3). Matches Slice 1/2.
5. ATOMIC counters. MistakeRecord create/update is an ON-CONFLICT upsert;
   retake_correct_count increment is atomic and idempotent (keyed to the
   StudentAnswer), so double-submit can't corrupt "flips at 2."
6. EVENT GRANULARITY resolved. Stage 6 emits BOTH completed_quiz (always) AND
   perfect_quiz_score (when 100%) in the SAME transaction as the score — because
   Slice 8/10 enumerate perfect_quiz_score as a stored eventType and require
   reproducibility-from-events (rule 7). Defined the event metadata shape.
7. DEFAULTS pinned to Slice 3 numbers as configuration seed (post-class 10;
   recap/exam-prep 5 per in-scope section; pool target ≈ 2–3× per-SECTION count;
   spread ≈ even). "No magic numbers" without stated defaults invites divergence.
8. POOL RESOLUTION clarified. QuizDefinition stores SCOPE; the pool is resolved
   at attempt time by (section, current model, current promptVersion). A prompt
   bump transparently moves new attempts to a fresh pool; old snapshots are
   untouched.
9. 6a DONE-CRITERIA hardened. The 6a gate now proves sampling correctness
   (recency bias, cross-section spread, exhaustion-recycle with NO generation)
   and the MistakeRecord upsert identity — not only the one-active lock.
10. NEW OWNER DECISION #4: post-class retrofit sequencing. The retrofit touches
    a shipped, FULLY VERIFIED surface (Stage 5 post-class). Recommended default
    moves it to LAST (after new modes prove the pool model), not into the 6a
    foundation. Your call — see Product decisions.
```

---

## Status

NOT STARTED. **Hard prerequisite: Stage 5.5** (and Stage 5).

---

## Goal

Complete the quiz system: add the three remaining quiz modes (**recap**, **exam-prep**, **mistakes-bank**) on top of the Stage 5 post-class engine, add **retake reinforcement**, and resolve the **AI capacity problem** with a reusable, per-section question pool — so exam-week demand never becomes an 18-minute generation queue.

---

## Hard prerequisites (block the stage from starting)

```
1. Stages 5 and 5.5 are FULLY VERIFIED — browser gates passed, not merely
   BACKEND VERIFIED. Stage 6 builds directly on the quiz engine, the event
   spine, and the schedule metadata; a half-closed prerequisite is a blocker
   (permanent acceptance rule).

2. The Stage 5 MistakeRecord schema is present and populated by real attempts:
   retake_correct_count, show_in_retake_prefix, source_quiz_definition_id,
   source_question_snapshot. Stage 6 reads ALL of these.

3. POOL-COMPATIBLE SCHEMA — now stated concretely so the agent can actually
   check it. "Pool-compatible" means a question can live in a durable, reusable
   store independent of any single attempt, AND a sampled attempt-question can
   point back to its durable source. Concretely, Stage 6 needs (or must add, if
   Stage 5 stopped at per-attempt questions per Slice 3):
     - a durable PoolQuestion entity (see Data model), and
     - a nullable QuizQuestion.sourcePoolQuestionId on the per-attempt question.
   If Stage 5 stored questions per-attempt ONLY with no durable store and no
   back-reference (the expected Slice 3 baseline), that is NOT a STOP — it is
   the planned 6a foundation work. STOP and escalate (rule 10) ONLY if the
   Stage 5 schema actively PRECLUDES adding the durable store additively (e.g.
   a non-nullable constraint or a model assumption that makes the back-reference
   impossible without rewriting shipped tables). Reconcile against the ACTUAL
   Stage 5 schema, not this spec — code wins over docs.

4. The Stage 5.5 week→sections resolution query in platform/query is live and
   tested. Recap and exam-prep both resolve their scope through it.

5. The Stage 5 pagination envelope exists and is the standard for new lists.
```

---

## Parallel development — coordination with Stage 7 (read this first)

Stage 7 (Glossary) is in flight at the same time. It **reuses** several things Stage 6 also touches: the shared AI rate limiter (rule 15), the `ai` RQ queue/worker, the flat-file PromptRegistry, the Stage 5 pagination envelope, the Stage 5 quiz UI components (Glossary's Learn/Test reuses them), and the **cache-key-with-promptVersion** discipline (Glossary's definition cache and our question pool follow the same invalidation pattern). To prevent collisions:

```
DO NOT modify the shared contracts. The Redis limiter, the PromptRegistry
  interface, the `ai` queue/worker shape, and the pagination envelope are
  shared infrastructure. If Stage 6 seems to need a change to any of them,
  STOP and write a findings note (rule 10) so it can be coordinated.

NEW PROMPTS ONLY. Quiz-generation prompts are NEW flat files under /prompts
  (e.g. prompts/quiz_generation/...). Never edit summary or glossary prompts.
  New prompt files declare model, backend, max_tokens, and reasoning level
  consistent with what Stage 4.5 established for the reasoning route.

DOMAINS STAY ISOLATED (rule 8). The quiz domain never imports glossary code and
  vice versa. Cross-domain reads, if any, go through platform/query.

SHARED QUIZ COMPONENTS ARE SHARED. The Stage 5 question card, answer-option
  states, and feedback states are reused by Stage 7. Do not fork, rename, or
  restructure them. If Stage 6 genuinely needs a change, flag it so Stage 7 can
  absorb it too.

MIGRATIONS WILL INTERLEAVE. Both stages add migrations. Keep Stage 6 migrations
  additive, confined to the quiz domain, and within Stage 6's reserved Alembic
  migration-number block (roadmap parallelization mechanics). Expect a numbering
  coordination at merge; raise an imminent clash rather than renumbering silently.

RULE 14 STILL BINDS. Whichever stage closes second re-runs the FULL active E2E
  suite, including the other stage's gates. Both agents keep the suite green.
```

If anything here appears to require editing Stage 7's territory, pause and check — do not proceed.

---

## Design input

Per the v3.1 two-input rule, each 6.x spec is written from **this roadmap + Design Plan §2.4 together**, locked before implementation.

Read, before building UI:
- **Design Plan §2.4, remaining portions** — quiz **mode selector** (2×2 card grid), **recap/exam-prep scope selector modal**, **retake mistake-prefix banner**.
- The **lecturer-side `AssessmentScope` creation form** and the **"generating your quiz" waiting state** (both flagged in the design-plan v1.1 review). Spec the waiting state honestly against the capacity model below — the first request for a not-yet-generated section can take real seconds; it gets a real progress state, never an infinite spinner.
- `knowledge/design-system.md` (the shipped 4.9 system) is the component authority. Compose existing primitives — **Card, Modal, Button, Badge, Table, Progress/Step indicators, Empty State, Toast**. If a screen needs a component the system lacks, that's a finding, not an improvisation.

---

## The capacity decision (ADR required) — RESOLVED: reusable per-section pool

The roadmap's exam-week math: 30 students each starting a 6-section recap = 180 reasoning-model calls ≈ 18 minutes of queue at 10 RPM. **TPM/RPM binds; this UX is unacceptable.** Resolution, taken here and matching the roadmap's stated mechanism ("generate per section into a pool; sample fresh combinations per attempt"):

**Questions are generated once per SECTION, stored, and reused for every student, every mode, and every attempt that touches that section. AI generation never runs twice for the same section + prompt version.**

### Two layers — keep them distinct

```
LAYER 1 — the SECTION POOL (the durable, reusable store):
  - One pool per (section, model, promptVersion). promptVersion in the key means
    a changed quiz prompt produces a fresh pool — same discipline as Stage 7's
    definition cache. Do NOT key the pool by scope or by student.
  - Generated in ONE AI call (rule 15 — one call per generation, never per
    question), from that section's DETAILED SUMMARY only — never raw transcript
    (exclusion). Because generation is per section, it always fits the model
    budget; there is no multi-summary aggregation at generation time.
  - The pool holds MORE questions than one quiz needs. Pool size is a setting,
    expressed relative to the PER-SECTION sample count, target ≈ 2–3× the
    per-section question count (NOT 2–3× a multi-section quiz's total; the pool
    is per section). NOT hardcoded — see "no magic numbers."
  - Validated by the Stage 5 OutputValidator (structure, exactly one correct
    option, etc.) before storage. Reuse Stage 5's function/tool-calling path.

LAYER 2 — the QUIZ (a QuizDefinition = the retake-able unit a student attempts):
  - post-class  → QuizDefinition per section
  - recap       → QuizDefinition per (module, canonical sorted in-scope section set)
  - exam-prep   → QuizDefinition per lecturer AssessmentScope
  - A QuizDefinition does NOT own questions. It stores SCOPE (which sections).
    Each ATTEMPT is assembled by SAMPLING from the section pools of its in-scope
    sections, resolving each section's pool at attempt time by
    (section, current model, current promptVersion).
  - QuizDefinitions are SHARED across students (deduplicated by their canonical
    key). Attempts, scores, and MistakeRecords are PER STUDENT against that
    shared QuizDefinition.
```

### How sampling works (this is how "retakes get new questions" survives reuse)

```
- Each attempt samples a quiz-length combination from the relevant pool(s),
  biased toward questions THIS student has not recently seen (exposure is
  derived from the student's prior QuizQuestion rows whose sourcePoolQuestionId
  is set — see Data model; no separate ledger required at MVP scale).
- Multi-section quizzes (recap, exam-prep) sample a SPREAD across the in-scope
  sections (default: roughly even coverage per section) — not all from one
  lecture. Exact distribution is a setting.
- SNAPSHOT-AT-ASSEMBLY: the sampled pool questions (and their options) are copied
  into the attempt's QuizQuestion / AnswerOption rows and shuffled THERE (Stage 5
  shuffle rule — correctness on option identity, never display letter). The
  attempt now owns an immutable snapshot. Consequence: pool invalidation or
  regeneration NEVER mutates an in-progress or completed attempt, and scores stay
  reproducible. (This is the 4.6 atomic-swap principle applied to quizzes.)
- Pool exhausted for a student (seen everything): recycle oldest-seen first.
  NO new AI call on exhaustion. Pool top-up is a post-MVP trigger, not Stage 6.
```

### When does generation happen, and who waits?

```
- LAZY by default: the first request touching a section with no fresh pool
  triggers that section's generation; that one student sees the waiting state.
  Everyone after reuses it. By exam time, most section pools already exist from
  earlier post-class use, so recap/exam-prep are usually instant.
- ONE-ACTIVE LOCK per (section, model, promptVersion) — the migration-0007
  partial-unique pattern + a job idempotency key. If many students hit the same
  ungenerated section at once (exam-week thundering herd), EXACTLY ONE
  generation job runs; the rest attach to it and show the same waiting state.
  No double generation, no double spend.
- WAITING STATE = the 4.5d backoff polling model (no 60-second hard timeout;
  limiter queueing + reasoning-model latency routinely exceed it). The client
  polls the generation job's status by its idempotency key until ready / failed.
- EXAM-PREP PRE-WARM (recommended — see Product decision #1): when a lecturer
  CREATES an AssessmentScope, pre-generate that scope's section pools then, so
  no student ever waits on a known exam. Bounded and IDEMPOTENT: pre-warm SKIPS
  any section that already has a fresh pool (reuse applies to pre-warm too), and
  enqueues at BACKGROUND priority (rule 15 — interactive headroom is preserved).
- A multi-section quiz whose pools aren't all ready shows ONE "preparing your
  quiz" state until every needed section pool exists, then assembles and starts.
```

### Pool-generation failure contract (NEW — do not leave this implicit)

```
- Invalid output (OutputValidator reject) or provider 5xx → bounded RQ retry,
  exactly as rule 15 specifies (RQ retries reserved for 5xx / invalid-output;
  in-call 429 backoff stays inside the limiter, not an RQ retry).
- Retries exhausted → the generation job is TERMINALLY failed. Every student
  attached to the one-active lock sees a clean FAILURE state (no stack traces),
  with a retry affordance that RE-ENQUEUES under the same one-active lock and
  idempotency key (so the herd still generates at most once).
- MULTI-SECTION: if one in-scope section's pool terminally fails, the quiz must
  NAME which section failed and offer retry for it — it must NOT hang forever in
  "preparing." (This is the failure twin of Decision #3's "wait for all ready.")
```

### Stale-pool invalidation

A pool carries the source checksum/hash of the summary it was built from (mirror Stage 4.6's stale-summary detection via `sourceTranscriptChecksum`). When a section's transcript is replaced/superseded, **only that section's pool** is marked stale and regenerates on next request; other sections in a span reuse their pools. No mixed old/new content in a live pool. In-progress/completed attempts are unaffected (snapshot-at-assembly, above).

### Reconciling with Stage 5's wording

Stage 5 said "pool per QuizDefinition." Stage 6 refines this to **pool per section, sampled by QuizDefinition** — because "per section" is what the capacity note specifies and is the cost-optimal, reuse-maximal unit. For a post-class QuizDefinition (1:1 with a section) the two phrasings coincide; for recap/exam-prep, the QuizDefinition samples across several section pools. The ADR records this relationship explicitly so the wording difference never causes confusion later.

**The capacity win:** the exam-week example drops from ~180 calls to **~6 (one per section)**, shared across all 30 students — and fewer still where post-class already generated the pool.

**ADR-0xx records:** per-section pool keyed by (section, model, promptVersion); one-call generation from the detailed summary; QuizDefinition-as-scope sampling with cross-section spread; per-attempt sampling + recency bias + snapshot-at-assembly; one-active generation lock + idempotency; lazy generation + optional exam-prep pre-warm; the pool-generation failure contract; stale-pool invalidation; the Stage 5 reconciliation above; and the post-class retrofit (below).

---

## Data model (NEW — additive; reconcile against the actual Stage 5 schema)

Field names follow slice conventions; the agent maps them to the real Stage 5 tables. All Stage 6 tables are additive and confined to the quiz domain.

```
SectionQuestionPool        — the durable, reusable store (Layer 1)
  - id
  - moduleSectionId        FK → ModuleSection (lecture/lab only)
  - model                  the resolved model identifier (matches AIRequestLog.modelId)
  - promptVersion
  - sourceSummaryChecksum  the detailed-summary hash the pool was built from (stale detection)
  - status                 generating | ready | failed
  - createdAt / updatedAt
  CONSTRAINTS:
    - unique active pool per (moduleSectionId, model, promptVersion)
    - one-active partial-unique on in-flight generation (migration-0007 pattern)
      keyed by (moduleSectionId, model, promptVersion) — enforces the herd lock

PoolQuestion               — a durable, validated question inside a pool
  - id
  - poolId                 FK → SectionQuestionPool
  - questionText
  - explanation
  - options                canonical options with isCorrect (exactly one true);
                           stored in a canonical order — shuffle happens at sampling
  - createdAt

QuizQuestion (Stage 5, per attempt) — ADD ONE NULLABLE COLUMN:
  - sourcePoolQuestionId   FK → PoolQuestion, NULLABLE
      • set when sourceType = new_generated (a snapshot of a sampled PoolQuestion)
      • NULL when sourceType = mistake_review (carries sourceMistakeRecordId instead)
      • NULL for pre-retrofit post-class rows (treated as "unseen" by exposure — fine)

EXPOSURE (no new table at MVP scale):
  A student has "seen" a PoolQuestion iff they have a QuizQuestion row, in one of
  their own attempts, with that sourcePoolQuestionId. Recency = MAX(createdAt) of
  those rows. Recency bias and exhaustion-recycle read this. If query cost ever
  bites, denormalize into a StudentQuestionExposure table later (post-MVP trigger,
  not Stage 6).

MistakeRecord (Stage 5) — UPSERT IDENTITY pinned:
  Stable key = (studentId, sourceQuizDefinitionId, sourcePoolQuestionId)
    • create-or-update is an ON-CONFLICT upsert on this key, so re-missing the
      SAME pooled question in the SAME QuizDefinition updates one record rather
      than duplicating it (this is what makes "stays in the bank / flips at 2"
      coherent under reuse).
    • For pre-retrofit / null-pool questions, fall back to the Stage 5 identity
      (e.g. sourceQuestionId) so existing data and the post-class gate are
      unaffected.
    • source_question_snapshot + answer_options_snapshot remain VERBATIM, so a
      mistake survives the section pool later changing.
```

---

## Backend scope

**Quiz modes (v2 carried):** `recap_period`, `exam_prep`, `mistakes_bank`.

**Scope resolution & section eligibility (NEW — pin this; it gates several modes):**
```
- A section is QUIZ-ELIGIBLE iff it is a lecture or lab section (Slice 1) AND it
  has a COMPLETED detailed summary (Slice 2 — summaries exist only for lecture/lab).
- assignment and supplementary sections are NEVER quiz-eligible. They are
  excluded from scope SILENTLY — never surfaced as "still processing," which
  would dead-end Decision #3.
- For STUDENTS, eligibility is further filtered to PUBLISHED + ASSIGNED sections
  (Authorization, below). The canonical recap key (sorted section ids) is
  computed AFTER this filter — so the shared QuizDefinition reflects only
  includable sections.
- "Still processing" (Decision #3) applies ONLY to eligible-but-not-yet-ready
  lecture/lab summaries, never to structurally-ineligible section types.
```

**Recap (student-driven):**
- Student selects a span — weeks / date range within one module — via the scope selector modal; it resolves to eligible sections through the Stage 5.5 query (using `week_number` / `session_date`).
- The recap QuizDefinition is keyed by `(module, canonical sorted in-scope section ids)` (post-eligibility-filter); identical selections by different students map to ONE shared QuizDefinition and share section pools.

**Exam-prep (lecturer-driven):**
- New `AssessmentScope` entity: a lecturer defines a named scope by **covered weeks** (e.g. "Midterm — weeks 1–6"). One QuizDefinition per AssessmentScope, shared across that module's students.
- Covered weeks resolve to eligible sections via the Stage 5.5 query (e.g. `coveredWeeks=[1..6]`).
- Creation is gated to the lecturer role on that module, consistent with existing authorization (see Authorization & visibility). Students consume; they do not create exam-prep scopes.
- EDIT semantics: editing an AssessmentScope re-resolves its sections; if pre-warm is on (Decision #1), an edit pre-warms only newly-added eligible sections (idempotent skip for existing pools). If attempts already exist against the scope, prefer locking the scope (or recording the change) rather than silently altering what past attempts were drawn from — flag if the design system has no affordance for this.

**Generation (reuse the existing AI stack):**
- Reuse the Stage 5 generation path and the **reasoning model route** (the route the capacity math calls "Nvidia"). No new model wiring.
- Structured output via **function/tool calling** with schema enforcement (as Stage 5), validated by the OutputValidator before the pool is stored.
- One AI call per section pool; logged in AIRequestLog with full provenance + the section reference (rule 6, rule 11).

**Mistakes accrual (all modes):**
- A wrong answer in ANY mode (post-class, recap, exam-prep) creates/updates a `MistakeRecord` for that student via the ON-CONFLICT upsert on its stable key (Data model), storing `source_question_snapshot` (verbatim) and `source_quiz_definition_id` (the QuizDefinition attempted). Snapshots mean a mistake survives even if the section pool later changes.

**Retake reinforcement (v2 carried) — precise mechanics:**
- A retake's question list is assembled as: **[the student's prefixed mistake questions for this QuizDefinition, from their snapshots]** first, then **[a fresh sample from the in-scope section pools, excluding the prefix questions already placed in this attempt and applying normal recency bias]**.
- `show_in_retake_prefix` is per MistakeRecord and tied to `source_quiz_definition_id`, so a mistake only prefixes retakes of the quiz it came from.
- A correct answer to a prefixed question increments `retake_correct_count`; the increment is ATOMIC and IDEMPOTENT — performed as a guarded UPDATE keyed to the specific StudentAnswer that scored it, so a double-submit cannot double-count. At **2** (cumulative across retakes), `show_in_retake_prefix` flips to `false` and the question leaves the prefix. The flip is idempotent.
- The mistake **stays in the MistakeRecord** and keeps appearing in the mistakes-bank. Leaving the prefix ≠ leaving the bank.
- MVP behavior to state explicitly (avoids ambiguity): a wrong answer does NOT reset the count; once a question has left the prefix it does NOT auto-return if missed again later (it remains in the bank). Stricter variants (consecutive-correct requirement; re-add on re-miss) are noted as Product decision #2 — default is the simple form above.

**Mistakes-bank (v2 carried; grouping unit = the module):**
- A dedicated mode assembling a quiz from the student's accumulated mistakes, **scoped to one module (`CourseModule`) and grouped by module** (the student picks which module's mistakes to practise). The grouping unit is `MistakeRecord.moduleId` — the existing course/module data model. Do NOT invent a new "course" aggregate above the module; "course" in student-facing copy maps to `CourseModule`.
- Built from stored `MistakeRecord.source_question_snapshot` — **no AI generation, no pool**. (No minimum-entry constraint: options are snapshotted with the question.)
- Whether correct answers HERE advance `retake_correct_count` is Product decision #2; default is **no** (the bank is pure practice; only source-quiz retakes move the prefix). The bank list uses the Stage 5 pagination envelope.

**Event spine (rule 7) — granular emission resolved:**
- Every completed attempt — any mode — emits a `completed_quiz` event in the **same DB transaction** as the score (idempotency `source_id` = the attempt).
- When the attempt scores 100%, ALSO emit a `perfect_quiz_score` event in the SAME transaction (idempotency `source_id` = the attempt). Both event types are enumerated in Slice 8/10 as stored events, and rule 7 requires gamification to be reproducible from the event log without owning the events — so Stage 6 emits the raw facts at source; Stage 10 only derives streaks/badges.
- Event metadata (minimum): `quizMode`, a scope descriptor (`moduleId`, in-scope `sectionIds` or `assessmentScopeId` / date-range as applicable), and `score`. Enough for Stage 9/10/11 to filter by mode and reconstruct without re-querying quiz internals.
- Stage 6 ONLY produces these events. It does not emit `attended_class`, `added_glossary_term`, etc. (other stages' concerns).

**Post-class retrofit (consistency, not a new feature) — see Product decision #4 for sequencing:**
- Bring Stage 5 post-class onto the same per-section pool + per-attempt-sampling model so there is **one** generation model, not two. This touches a shipped, FULLY VERIFIED surface: the migration must be backward-compatible with existing attempts/mistakes (pre-retrofit rows keep `sourcePoolQuestionId = NULL` and the Stage 5 MistakeRecord identity; both remain valid), and the existing post-class browser gate must still pass unchanged. If the retrofit changes the generating-state TIMING (first post-class attempt now triggers pool generation), the gate's observable CONTRACT must still hold — adjust gate timing if needed under rule 14, but do not silently weaken the gate. *Sub-decision:* if the retrofit proves higher-risk than expected, leave post-class as-is and flag it — but two divergent generation paths is the outcome to avoid.

**No magic numbers (roadmap discipline) — defaults pinned to Slice 3:** quiz length, pool target size, and the cross-section sampling spread are configuration, not hardcoded constants — same principle as grade boundaries in DB and estimates stored on records. Seed the configuration with the Slice 3 values: **post-class quiz length = 10; recap & exam-prep = 5 questions per in-scope eligible section** (so a 6-section recap = 30); **pool target ≈ 2–3× the per-section count; cross-section spread ≈ even.** Stored as a module-level override of a global default.

---

## Authorization & visibility (do not skip — this is security-sensitive)

```
- A student can only access quizzes for modules they are ASSIGNED to (active
  membership, per rule 4 / GET /me). Unassigned access returns 404, not 403 —
  matching the Stage 4.7 pattern (do not reveal existence).
- Scope resolution for STUDENTS filters to PUBLISHED, assigned, quiz-eligible
  sections only. A student can never receive questions sampled from an
  unpublished (or ineligible) section, even if a pool exists from lecturer use.
  (Reuses the Stage 3 / 4.7 visibility rules — and the restored content-
  visibility E2E spec must be green, rule 14.)
- The mistakes-bank returns ONLY the requesting student's own mistakes. Never
  another student's, never cross-module unless the student picked that module.
- AssessmentScope create/edit is lecturer-on-that-module only; a student calling
  it gets 403 (session kept), per rule 5.
- 401 vs 403 handled per rule 5 throughout (401 → clear+redirect; 403 → keep
  session, render unauthorized).
```

---

## Thin UI scope

Built on the 4.9 system; composed from existing components.

- **Quiz mode selector** — 2×2 card grid (post-class / recap / exam-prep / mistakes-bank), each with available / unavailable states.
- **Scope selector modal** — recap (pick weeks / date range), exam-prep (pick a lecturer-defined `AssessmentScope`).
- **"Generating your quiz" waiting state** — shown only when a needed section pool is still generating; a real progress state (4.5d backoff polling), no infinite spinner. Reused-pool quizzes go straight in. Includes the FAILURE state + retry affordance from the failure contract.
- **Retake mistake-prefix banner** — tells the student their missed questions come first.
- **Lecturer `AssessmentScope` creation form** — name + covered weeks; paginated list of existing scopes.
- **Mistakes-bank entry** — pick a module; empty state when there are no mistakes in that module.

---

## UI proof obligation

A student retakes a quiz, sees missed questions first, answers one correctly twice across retakes, watches it drop from the prefix — **while still finding it in the mistakes-bank quiz**. And a second student opening the same recap/exam-prep span gets a ready quiz with **no new generation** — the reuse is observable, not just claimed.

---

## Browser gate

```
RETAKE REINFORCEMENT + BANK:
Original quiz with mistakes → retake starts with the mistake-review prefix
→ 2 correct retake answers → mistake leaves the prefix → mistake REMAINS in the
  mistakes-bank quiz (scoped to that module)

EXAM-PREP + SCOPE CORRECTNESS:
Lecturer defines covered weeks (AssessmentScope) → exam-prep quiz's sampled
  questions come ONLY from in-scope eligible sections (a question from an
  out-of-scope week never appears) → student completes it → completed_quiz event
  (and perfect_quiz_score if 100%) inserted in the same transaction as the score

POOL REUSE (the capacity decision, proven in-browser):
First student opens a recap/exam-prep span with an ungenerated section → sees
  the generating state → completes the quiz
→ Second student opens a span covering that same section → ready immediately,
  NO new generation AIRequestLog row for that section (asserted against the log;
  holds in CI too, since the deterministic adapter still writes the log)
→ A retake samples a fresh combination from the existing pool with NO new
  generation call

AUTHORIZATION:
Unassigned student → 404 on the quiz; student cannot sample an unpublished or
  ineligible section's questions; student B cannot see student A's mistakes.
```

**Assertion notes (keep the gate flake-free):**
- The DETERMINISTIC anchors are: (a) "no new generation AIRequestLog row at SECTION granularity" for reuse/retake, and (b) the mistake-review prefix = the EXACT missed snapshots (deterministic by construction).
- The "fresh combination" claim is inherently non-deterministic. Make the sampler SEEDABLE in test mode (deterministic seed → reproducible sample, and a different attempt seed → an observably different combination where the pool is large enough). This also makes sampling bugs reproducible. Do NOT assert "fresh" via a brittle "all questions differ" check against a small pool.

Testing standard (rule 9): real browser, real backend, real DB; separate browser contexts for the two students and for lecturer vs student; forced states use deterministic E2E-only fault/seed injection (impossible outside test), never random failure or manual DB edits.

---

## Sub-sessions (spec written before implementation; each gated before the next)

```
6a  Per-section pool foundation + capacity ADR.
    Durable PoolQuestion store + QuizQuestion.sourcePoolQuestionId; section pool
    keyed by (section, model, promptVersion); one-call generation from the
    detailed summary; per-attempt SAMPLING + recency bias + cross-section spread
    + snapshot-at-assembly; one-active generation lock + idempotency; the
    pool-generation FAILURE contract; stale-pool invalidation; the MistakeRecord
    upsert identity.
    HARD GATE: prove (1) pool reuse + the one-active lock (no double generation,
    incl. simultaneous first-requests), (2) sampling correctness — recency bias,
    cross-section spread, and exhaustion-recycle with NO generation call, and
    (3) the MistakeRecord upsert identity (re-missing a re-sampled question
    updates one record). All before any mode UI is built.
    (Post-class retrofit is sequenced per Product decision #4 — default: NOT here.)

6b  Recap + exam-prep modes + authorization.
    AssessmentScope entity + lecturer creation (+ optional pre-warm per decision
    #1); recap scope dedup + resolution via the 5.5 query; section-eligibility
    filtering; student-side published/assigned filtering and 404 rules;
    availability rules (decision #3).

6c  Retake reinforcement + mistakes-bank.
    Retake assembly (prefix snapshots + fresh sample); retake_correct_count
    (atomic, idempotent) + prefix flip at 2; mistakes-bank assembly per module
    from snapshots; pagination; completed_quiz (+ perfect_quiz_score) events for
    all modes.

6d  UI + gates (+ post-class retrofit if Decision #4 = "last").
    Mode selector, scope selector modal, generating/failure waiting state,
    retake-prefix banner, lecturer AssessmentScope form, mistakes-bank entry; the
    browser gate above; the real-provider smoke (rule 11, model-ID assertion,
    targeting the quiz-pool generation path on the reasoning route); full active
    E2E suite (rule 14). If the retrofit lands here, the existing post-class
    browser gate re-runs and must stay green.
```

---

## Done means

```
Three new modes work end-to-end through the per-section pooled model.
Reuse proven: a second student / a retake gets a ready quiz with NO new
  generation call (asserted against AIRequestLog, at section granularity).
One-active lock proven: simultaneous first-requests for a section generate once.
Sampling proven: recency bias + cross-section spread + exhaustion-recycle (no gen).
Snapshot-at-assembly proven: pool invalidation does not mutate a started attempt.
Pool-generation failure proven: waiters see a failure state + retry re-enqueues
  once under the lock; a multi-section quiz names a terminally-failed section.
Stale-pool invalidation proven on a transcript replacement (only that section).
Scope correctness proven: exam-prep/recap never sample out-of-scope OR ineligible
  sections.
Authorization proven: 404 for unassigned; no unpublished/ineligible-section
  questions; bank is own-student-only.
Retake reinforcement: prefix flips at 2 correct (atomic/idempotent); mistake
  stays in the bank.
Mistakes-bank assembled per module from snapshots, no generation.
completed_quiz (+ perfect_quiz_score on 100%) inserted in the same transaction as
  the score, all modes.
Post-class retrofit done (or explicitly deferred with a finding per decision #4);
  the post-class gate still passes.
Capacity ADR recorded. Deterministic adapter at the provider boundary in CI;
  real-provider smoke recorded. Full active E2E suite green (rule 14).
Knowledge files + this roadmap's status table updated in the same commit.
```

---

## Exclusions

Formal grading; lecturer question bank; proctoring; adaptive engine; generation from raw transcript; pool top-up / regeneration on exhaustion (post-MVP trigger); shared (cross-student) **mistakes** — the *pool* is shared, the *mistakes bank* is per-student; a denormalized exposure table (derive at MVP scale; denormalize is a post-MVP trigger).

---

## Product decisions for the owner (flagged, with recommended defaults)

```
#1  Exam-prep pre-warm. RECOMMENDED: when a lecturer creates an AssessmentScope,
    generate that scope's section pools immediately so NO student waits on a
    known exam. Cost is bounded (one pool per eligible section, once; pre-warm
    skips sections that already have a fresh pool) and runs at background
    priority. Alternative: stay lazy and let the first student per section wait.
    (Recap stays lazy either way — student spans are unpredictable.)

#2  Does practising in the mistakes-bank count toward clearing a mistake from a
    quiz's "missed-first" prefix? DEFAULT: no — only retaking the SOURCE quiz
    moves the prefix; the bank is pure practice. Simpler and matches the gate.
    Alternative: correct answers anywhere advance the count. Also under this
    decision: consecutive vs cumulative "2 correct", and whether a re-missed
    question returns to the prefix (default: cumulative, no return).

#3  When part of a requested span isn't ready (a lecture's summary is still
    processing). DEFAULT: the quiz is unavailable until ALL in-scope eligible
    sections are ready, with a clear note of what's still processing
    (predictable, no surprise partial coverage). Alternative: offer the quiz over
    the ready sections only, flagging the gap. NOTE: this is about eligible-but-
    not-ready summaries only — structurally ineligible sections (assignment/
    supplementary) are excluded silently and never block.

#4  Post-class retrofit sequencing. The retrofit moves a SHIPPED, FULLY VERIFIED
    surface (Stage 5 post-class) onto the pool model — the only Stage 6 change
    that can break something already green. RECOMMENDED: sequence it LAST (in 6d,
    after the new modes have proven the pool/lock/sampling design on surfaces with
    no shipped contract), with a clean revert path, rather than bundling it into
    the 6a foundation. The existing post-class gate re-runs and must pass
    unchanged. Alternative: retrofit in 6a (more risk up front; foundation and a
    shipped-surface change land together). Either way, the fallback stands: if the
    retrofit proves higher-risk than expected, leave post-class as-is and flag it
    (two generation paths is the outcome to avoid, but a broken shipped gate is
    worse).
```

---

## Recommended gstack skills for this stage

One genuinely tricky piece of architecture (per-section pool + concurrency lock + sampling + the failure contract) and several UI surfaces, so the review skills earn their keep:

```
Before building (6a especially):
  /autoplan   — runs CEO → design → eng review in one pass; good for locking the
                pool/lock/sampling design, the failure contract, and the capacity
                ADR before code.
                (Or /plan-eng-review for the architecture + /plan-design-review
                 for the §2.4 surfaces individually.)

During each sub-session:
  /review     — catch the race conditions and edge cases that pass CI but bite
                in production. The one-active lock, the upsert counters, and the
                stale-pool path are exactly where production bugs hide.

At the gates (6d especially):
  /qa         — drive the browser gate for real: two student contexts, the reuse
                assertion (section-granular AIRequestLog), the retake flow, the
                failure-and-retry path, the authorization 404s. /qa auto-generates
                a regression test per bug found.
  /cso        — light security pass on the new authorization surface (assigned/
                published/eligible filtering, own-mistakes-only, the 404 rules)
                before close, even though the heavy audit is Stage 12.

Optional:
  /investigate — if a flow misbehaves (e.g. a mistake won't leave the prefix, or
                 a pool double-generates), root-cause it before patching; no fixes
                 without investigation.
```