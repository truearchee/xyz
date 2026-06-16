# Stage 5 — Shared Quiz Engine + Event Spine

**Status:** FULLY VERIFIED on branch `spec-5` (not yet merged). See [[steps/stage-05/5a-quiz-foundation]],
[[steps/stage-05/5b-quiz-generation-recovery]], [[steps/stage-05/5c-answer-feedback-scoring-retake]],
[[steps/stage-05/5d-student-ui-browser-gate]], and [[steps/stage-05/5e-review-finding-fixes]].
**Spec version:** v1.3 (two external review passes triaged; see Revision log)
**Roadmap ref:** Stage 5 (v3).
**Path:** `knowledge/specs/stage-05/5-shared-quiz-engine-event-spine.md`
**Source slices:** Slice 3 (Quiz System) is authoritative for the quiz domain; Slice 8 (Gamification) is authoritative for `StudentActivityEvent` shape only — Stage 5 builds the spine, not the consumer.

---

## Prerequisites (do not mark this stage startable until the linked step reports confirm these)

```
Stage 4.5  FULLY VERIFIED      (AI infra, gateway, limiter, AIRequestLog, deterministic adapter)
Stage 4.6  FULLY VERIFIED      (ActiveTranscriptSummaryResolver, supersession, retry/recovery, reaper)
Stage 4.7  FULLY VERIFIED      (StudentSummaryAccessPolicy: published-section + assigned-module, 404)
Stage 4.9  FULLY VERIFIED      (Tailwind + shared components, Vitest, OpenAPI client hygiene)
Stage 4.8  NON-BLOCKING for local Stage 5. Stage 5 is built and gated locally (real backend, DB,
           browser). 4.8 stays BACKEND VERIFIED with carried debt (hosted Fly.io deploy deferred);
           that debt blocks Stage 8.3 and ANY demo / real-user exposure — NOT local Stage 5 work.
           "BACKEND VERIFIED" is not DONE and is not invoked here as if it were.

CI-GATE CAVEAT: the Done criteria assume the full active E2E suite gates merge in CI. Confirm
  4.9's F-4.9-5 (branch-protection required-checks) is CLOSED. If it is still open, "CI-green
  gates merge" is ADVISORY and the human enforces the suite at merge until F-4.9-5 lands.
```

---

## Goal

Ship the **shared MCQ quiz engine** and the **platform activity event spine**, proven end-to-end through **post-class quizzes only**. A student opens a published lecture/lab with a completed detailed summary, takes an AI-generated 10-question quiz, gets immediate per-answer feedback, sees a wrong answer become a recorded mistake, completes the attempt, sees a score — and a `completed_quiz` event lands in the same transaction as that score.

This is a **foundation stage disguised as a feature**. The engine tables, the event spine, the pagination envelope, the structured-output contract, and the shared MCQ frontend components are reused by Stages 6, 7, 8, 10, 11. Getting the boundaries right here is the point; post-class is the thin vertical proof.

---

## Scope decisions (LOCKED — confirmed with product)

```
post_class quiz mode ONLY. recap_period / exam_prep / mistakes_bank MODES → Stage 6.
MistakeRecord table is CREATED and POPULATED here. Nothing READS it for practice here (Stage 6).
AssessmentScope → EXCLUDED (needs week metadata from Stage 5.5).
Retake = plain "Start Over": new attempt, 10 newly generated questions, NO mistake-review prefix.
Generation is LAZY and PER-ATTEMPT; a brief "generating" state is acceptable (confirmed).
One AI call per attempt → all 10 questions (rule 15).
Wrong-answer behaviour: immediate red/green + text label, "Saved to your mistakes", mistakes
  count on results. No mistakes-bank practice UI (Stage 6).
Quiz panel lives on the SAME lecture/lab page as the summaries (exact placement TBD; put it there).
completed_quiz emitted in the SAME transaction as the score write.
perfect_quiz_score emitted (same transaction) when ALL answers correct. NO student-visible
  celebration until Stage 10.
Practice-only: NO grade, progress, or official-record writes anywhere.
```

### Defaulted product decisions (no preference given — defaults taken; flipping each is a one-line change)
```
D-MATH    Math/formulas in quiz text render as ESCAPED PLAIN TEXT in Stage 5 (students may see raw
          `$\lim_{x\to0}$`). KaTeX rendering is DEFERRED to Stage 7, where it integrates into the
          SHARED MCQ component — post-class quizzes inherit it for free, no rework. (Flip = pull
          KaTeX into 5d.) Rationale: lower scope; matches roadmap's "KaTeX integrated early" living
          in Stage 7; the reusable-component design makes the later upgrade automatic.
D-ABANDON No abandon-from-in-progress. "Start Over" is terminal-only; a mid-quiz student resumes or
          finishes. Answers are final once submitted (stated in the UI section). (Flip = add an
          `abandoned` attempt status + an abandon endpoint.)
```

---

## Hard prerequisites internal to the stage (block 5b/5d)

```
1. 4.5 LLMGateway structured-output path confirmed against the codebase in 5b (tool/function-calling
   per the IFM reference, OR the existing structured-JSON path). Code wins over docs.
2. The 4.5 deterministic test adapter is extended with: (a) a valid 10-question quiz fixture
   (schema-valid, known correct options) so the full path runs in CI and the E2E can deterministically
   reach 100% and specific wrong answers; (b) a forced-invalid fixture for the validator/retry test.
   Lands in 5b.
```

---

## Backend scope

`platform/events`: `StudentActivityEvent` + `EventRecorder` (same-transaction emit, idempotency). `platform/query`: pagination envelope + **read-only** post-class availability model. Quiz domain: `QuizDefinition`, `QuizAttempt`, `QuizQuestion`, `AnswerOption`, `StudentAnswer`, `MistakeRecord`; generation job on the existing `ai` RQ queue (4.5a) through the gateway; `OutputValidator` for quiz schema (structure **and** size); answer / completion endpoints; plain retake; stale-generating recovery. New prompt in the flat-file PromptRegistry. Alembic migration per sub-session, fresh-DB round-trip verified.

**No new IngestionJob types.** Quiz generation is a quiz-domain job; the **`QuizAttempt` row is its own status tracker** (`generating → in_progress | failed`) and the recovery target. No separate job table.

---

## Key design locks (each becomes or references an ADR)

### 1. Lazy per-attempt generation
Questions are generated at Start, never ahead of time. UX: a brief "generating" poll before Q1 (reuse the 4.5d backoff-polling pattern; no 60s hard timeout).

### 2. Availability is computed, read-only; writes only on Start
**Reads never create domain rows.** Availability is a pure read; the `QuizDefinition` row is materialized only on `POST start` (get-or-create).
```
QuizDefinition (post_class, moduleSectionId): thin anchor row.
  - get-or-create on POST start ONLY. Partial-unique (moduleSectionId, quizMode) WHERE quizMode='post_class'.
  - lecture / lab sections ONLY (mirrors the Slice 2 transcript-section restriction).
  - moduleId derived from the section's courseModuleId at creation (needed for event emit).
  - questionPolicy = { count: 10, optionsPerQuestion: 4 }.
  - NO persisted readiness `status` (deviation from Slice 3 — a stored-but-untrusted status is a
    drift magnet). Readiness is computed every time.
  - sourceScope = { sectionType, moduleSectionId }; sourceSummaryIds = []  ← NO summary pointer
    (resolved live at Start, snapshotted on the attempt — supersession-safe).
```

### 3. Attempt state model + the one-active invariant
```
States: generating | in_progress | completed | failed        (no `abandoned` — D-ABANDON)
INVARIANT 1: at most ONE attempt in {generating, in_progress} per (student, quizDefinition),
             partial-unique index.
INVARIANT 2: UNIQUE (studentId, quizDefinitionId, attemptNumber)  ← history integrity.
Resume vs restart:
  Page load → non-terminal attempt resumes (generating→poll; in_progress→next unanswered;
              in_progress all-answered→"See results", idempotent complete).
  Start button → resumes a non-terminal attempt; never creates a 2nd.
  "Start Over" → terminal state only (completed|failed) → new generating attempt, attemptNumber+1.
  Concurrent Start race → on partial-unique IntegrityError: rollback, re-read non-terminal
              attempt, return it as resume. DB rejection NEVER surfaced as a user error.
```

### 4. Generation recovery — no stuck `generating` (mechanically precise)
```
Job identity:  RQ job_id = "quiz-generate:{attemptId}". Store generationJobId on QuizAttempt at enqueue.
Enqueue-after-commit failure (commit ok, enqueue throws): mark attempt failed in a COMPENSATING
               transaction; failureCategory="enqueue_failed"; return failed state to the frontend.
Primary failure path: the worker failure callback / domain failure handler writes the failed state
               (RQ timeout, provider 5xx exhausted, invalid output exhausted).
               failureCategory ∈ { generation_timeout | provider_error | invalid_output | enqueue_failed | crashed }.
Reaper (SAFETY NET, liveness not age): extend the 4.6c singleton-locked reaper to QuizAttempt rows
               in `generating`. Liveness judged by RQ registries + job_id — NOT age alone. A job
               still queued/running behind a backed-up AI queue (the cohort-burst case Stage 5
               deliberately absorbs) must NOT be reaped. Only LOST jobs (absent from registries) →
               failed (failureCategory="crashed").
               ON `crashed`: the reaper ALSO finalizes the linked AIRequestLog (via the attempt's
               aiRequestLogId) to a terminal status with reason="abandoned_crashed". AIRequestLog is
               written before the call (rule 6); on a lost job the worker handler never runs, so
               without this the cost dashboard (rule 6 → Stage 12 cost review) leaks dangling rows.
```
No in-place generation retry of a failed attempt (attempts are cheap; the student uses Start Over).

### 5. One call per attempt; structured output + OutputValidator both
Job `generate_post_class_quiz` (background priority; AIRequestLog idempotency key `quiz:{attemptId}`):
```
1. AIRequestLog row written BEFORE the call (rule 6, hard). generationStartedAt set.
2. Through LLMGateway: render post_class_quiz_generation prompt with the detailed-summary TEXT,
   pass the limiter (rule 15), single call → 10 questions, structured output.
   Routing intent = reasoning route (K2-Think / Nvidia per Slice 3); model resolved from config —
   carries the current K2-Think-v2 named deviation forward. NOT hardcoded here.
3. OutputValidator is the AUTHORITY regardless of mechanism.
   STRUCTURE: per question — non-empty questionText; exactly optionsPerQuestion options; exactly one
     isCorrect; no empty or duplicate option text; explanation present.
     Overall — exactly 10 valid questions; no duplicate questionText within the attempt.
   SIZE: total payload ≤ 64 KB (configurable); questionText ≤ 1,000 chars; option text ≤ 500;
     explanation ≤ 2,000.
   TEXT SAFETY: "no HTML" means ESCAPE-ON-DISPLAY, not reject-on-angle-bracket. Store raw text
     faithfully (legitimate math/code contains `<` and `>`); the validator must NOT reject content
     for containing `<`/`>`. Escaping happens at render (UI). (See D-MATH for the math path.)
4. SINGLE TRANSACTION (atomic): persist all QuizQuestion + AnswerOption rows (displayOrder shuffled)
   AND stamp attempt-level + question-level provenance AND flip attempt → in_progress
   (totalQuestions=10, newQuestionCount=10, mistakeReviewQuestionCount=0, generationCompletedAt).
   Because this is atomic, `status=generating` PROVABLY implies "no questions persisted" — the reaper
   never strands a generating-with-questions row, and re-runs are unambiguous.
5. Invalid output or provider 5xx → RQ retry → exhausted → attempt `failed` (sanitized message).
6. FENCING: generate only if attempt.status=generating AND no questions exist. With step 4 atomic,
   `status != generating` alone is authoritative; the no-questions clause is belt-and-suspenders.
```
**Capacity (rule 15) — explicit:** quiz generation runs on the **reasoning route (K2-Think / Nvidia, 10 RPM)** — the platform's *tightest* request budget — and post-class is the *burstiest* trigger (a whole cohort hitting one lecture's quiz at once). One call per attempt, summary-sized prompt, background priority; the "generating" state + limiter queue absorb the burst, and the reaper does not kill queued jobs. This is acceptable for MVP. The route is a **config knob** (the gateway abstracts it); if cohort-burst latency proves painful, re-routing brief-vs-reasoning is an **ADR**, not a code change. The heavier recap/exam-prep burst math is **Stage 6's capacity ADR**.

### 6. Enqueue-after-commit (project invariant)
Start creates `QuizAttempt(generating)`, **commits**, then enqueues by `job_id` **after commit**. Never enqueue inside the creating transaction (rollback → phantom job). Lock 4 covers the inverse edge.

### 6a. Provenance on the attempt (the generated-artifact boundary)
```
QuizAttempt provenance: sourceSummaryId, sourceSummaryContentHash, sourceTranscriptChecksum,
  modelName, promptVersion, backendUsed, aiRequestLogId, generationJobId,
  generationStartedAt, generationCompletedAt, failureCategory, failureMessageSanitized
```
The row you query to answer "why did this quiz look wrong?". Questions keep nullable `modelName`/`promptVersion`/`sourceSummaryId` for Stage 6 mistake-review compatibility; the attempt is authoritative.

### 7. Correctness on option identity, never letter; never leaked early
`AnswerOption.isCorrect` is the truth; `StudentAnswer.isCorrect` is computed server-side from the submitted option's identity. **Never serialize `AnswerOption.isCorrect` in a student DTO.** It surfaces only inside the answer-feedback object after answering, or the completed result view.

### 8. Event spine
```
StudentActivityEvent: id, studentId, moduleId, eventType, sourceId, occurredAt, metadata
  occurredAt = tz-aware UTC (timestamptz). Stage 10 streaks are tz-aware/scheduled-day-based —
    the event needs an unambiguous UTC instant recorded now.
  eventType enum = full Slice 8 set. Stage 5 EMITS only completed_quiz, perfect_quiz_score.
  UNIQUE (eventType, sourceId) ← idempotency. sourceId = action instance = attemptId.
EventRecorder.record(session, student_id, module_id, event_type, source_id, metadata):
  inserts WITHIN the caller's transaction. It does NOT commit. The domain owns the commit.
Metadata contract (Slice 8: "badges reproducible from events"):
  completed_quiz     = { quizMode, quizDefinitionId, moduleSectionId, attemptNumber,
                         correctCount, totalQuestions, scorePercentage }
  perfect_quiz_score = { quizMode, quizDefinitionId, moduleSectionId, attemptNumber }
NO consumer is built in Stage 5 (rule 7: gamification consumes events, never owns them).
```

### 9. Pagination envelope, defined once
```
PaginatedResponse[T] = { items: T[], pagination: { limit, offset, total } }   (offset-based)
```
Reused verbatim by glossary, conversations, events. Stage 5 originally named a paginated attempts list as
the first real consumer, but 5c deliberately shipped the student panel as an aggregate (best score ·
attempt count), not pagination theatre. Per ADR-041's amendment, the first genuine list consumer is
deferred to Stage 6 mistakes-bank or Stage 7 glossary lists.

### 10. QuizQuestion is an attempt-snapshot table
```
quizAttemptId NOT NULL. questionType pinned to multiple_choice. QuizQuestion is an ATTEMPT SNAPSHOT
  table, never a pool — Stage 6 question pools get a SEPARATE table; never overload one table across
  two lifecycles.
Stage-6-ready nullable columns added NOW (avoids a hot-table migration; matches Slice 3):
  sourceType (new_generated | mistake_review) — Stage 5 always new_generated
  sourceMistakeRecordId (nullable)            — Stage 5 always null
  sourceModuleId, sourceSectionId, sourceSummaryId (nullable), modelName (nullable), promptVersion (nullable)
```

---

## Data model — fields that must match Slice 3 / roadmap minimum (set in 5a)

```
StudentAnswer: id, quizAttemptId, quizQuestionId, selectedAnswerOptionId, isCorrect, answeredAt
  UNIQUE (quizAttemptId, quizQuestionId)  ← DB-enforced answer idempotency (the missing guard).
  On IntegrityError (double-tap / two-tab) → return the ORIGINAL AnswerFeedback. Same pattern as
  the Start race. Without this, a double-submit inserts two rows and inflates correctCount,
  silently corrupting scorePercentage AND the correctCount==totalQuestions perfect-score test.

MistakeRecord (full Slice 3 minimum — denormalized for Stage 6 scoped queries):
  id, studentId, moduleId, moduleSectionId, sourceQuizDefinitionId, sourceQuizAttemptId,
  sourceQuestionId, questionSnapshot, answerOptionsSnapshot, selectedWrongAnswer, correctAnswer,
  explanation, retakeCorrectCount (0), showInRetakePrefix (true), createdAt, updatedAt
  UNIQUE (sourceQuizAttemptId, sourceQuestionId).
  sourceQuizDefinitionId + moduleId are denormalized (not join-only) so Stage 6's "my mistakes in
  this module/quiz" does not join through a snapshot table.

QuizAttempt score fields: scorePercentage DECIMAL(5,2), correctCount, incorrectCount, totalQuestions.
  Perfect-score from counts (correctCount == totalQuestions), never float equality.
```

---

## HTTP contract (explicit — improvisation is where weird bugs breed)

```
GET availability (section)
  200 { availability: "available" | "unavailable",
        reasonCode?: "summary_processing" | "summary_unavailable" }    ← visible-but-not-ready
  404                                                                   ← unpublished OR unassigned
  403                                                                   ← non-student
  READ-ONLY. Creates no rows.
POST start
  200/201 created or resumed
  409 { code: "quiz_unavailable" }   ← visible but no active GENERATED detailed summary
  404 ← unpublished OR unassigned        403 ← non-student
GET attempt detail / status
  200 attempt DTO (no isCorrect leaked pre-answer)
  404 ← not owner OR section no longer visible    403 ← non-student
POST answer / POST complete
  200 feedback / result     409 ← business state    404 ← not owner OR not visible    403 ← non-student
```
**Non-student → 403 uniformly on every quiz endpoint.** **Visibility re-checked on EVERY student endpoint** (availability, start, detail, answer, complete):
```
caller owns the attempt AND caller still assigned AND section still published AND section ∈ {lecture,lab}
  → else 404.
```
Two distinct seams:
```
SUPERSESSION (replace transcript): must NOT break an in-flight attempt — questions snapshotted, it
  stays answerable/scorable; a NEW attempt uses the new summary.
UNPUBLISH (hide section): must HIDE the in-flight attempt — all endpoints 404 while hidden; the row
  persists; on re-publish the student resumes; no event fires while hidden (complete 404s).
```

---

## DTO contract (so correctness cannot leak via a careless `response_model`)

```ts
type QuizOptionForStudent = { id: string; text: string; displayOrder: number };  // NO isCorrect
type QuizQuestionForStudent = {
  id: string; questionText: string; displayOrder: number; options: QuizOptionForStudent[];
  answer?: { selectedAnswerOptionId: string; isCorrect: boolean; correctAnswerOptionId: string; explanation: string };
};
type AnswerFeedback = {
  questionId: string;
  selectedAnswerOptionId: string;   // the ORIGINAL selected option (idempotent re-answer)
  isCorrect: boolean; correctAnswerOptionId: string; explanation: string;
  alreadyAnswered: boolean; mistakeSaved: boolean;
};
```
`AnswerOption.isCorrect` is never serialized in a student DTO. If a duplicate request sends a *different* option than the original, the server returns the ORIGINAL result with `alreadyAnswered=true`.

---

## Endpoint behaviour (the vertical path)

```
POST start: visibility + student; resolve active detailed summary (none → 409 quiz_unavailable);
  get-or-create QuizDefinition (derive moduleId); non-terminal exists → resume; else create
  generating attempt (attemptNumber=prior max+1), COMMIT, enqueue after commit (compensate on failure).

POST answer { attemptId, questionId, selectedAnswerOptionId }   ← one at a time
  visibility; attempt.status==in_progress (else 409)
  INTEGRITY: attempt.studentId==caller (cross-student→404); question.quizAttemptId==attemptId (404);
             selectedAnswerOption.quizQuestionId==questionId (422)
  insert StudentAnswer; on UNIQUE(quizAttemptId,questionId) IntegrityError → return ORIGINAL feedback
  isCorrect from OPTION IDENTITY; if incorrect → create MistakeRecord (idempotent snapshot)
  return AnswerFeedback. Does NOT score or emit events.

POST complete { attemptId }   ← the atomic unit
  visibility; all questions answered (always reachable — no skip)
  SELECT attempt FOR UPDATE (serialize); if completed → return cached
  ONE TRANSACTION: counts; scorePercentage=round(correct/total*100,2); status=completed + counts +
    completedAt; EventRecorder(completed_quiz); if correctCount==totalQuestions →
    EventRecorder(perfect_quiz_score); commit (event UNIQUE is the backstop).
```
Mistakes accumulate **per failed-question instance** (no concept dedup in Stage 5 — Stage 6 territory).

---

## Thin UI scope (on the 4.9 Tailwind system)

Reusable, **API-agnostic** MCQ components (Stage 7 glossary Learn/Test reuses them — accessibility and, later, KaTeX fixed once):
```
MultipleChoiceQuestionCard, AnswerOptionButton, AnswerFeedbackPanel, QuizResultSummary
  — must NOT import post-class-specific API code.
```
Post-class quiz panel below the summaries. States: unavailable (passive), available (Start), generating (poll), in-progress (resumes on reload), per-answer feedback (red/green **plus** text label, correct answer shown, explanation, "Saved to your mistakes" on wrong), all-answered (See results), results (score, correct/incorrect, mistakes count, Start Over), failed (sanitized + Start Over), history line (best score · attempt count).
```
Math text (D-MATH): rendered as ESCAPED PLAIN TEXT in Stage 5 (raw `$...$` may show). KaTeX arrives
  via the shared component in Stage 7.
Answers are FINAL once submitted (D-ABANDON): no change-answer; immediate-feedback model makes this
  explicit, not just implied.
```

---

## UI proof obligation

A student answers a question and sees correct/incorrect feedback **immediately** in a real browser against the real backend — and a wrong answer **visibly becomes a recorded mistake**. Start Over yields a new attempt.

---

## Browser gate

```
Student opens published lecture/lab with completed detailed summary → quiz available
→ Start → "generating" → 10 generated questions appear
→ answers each → immediate red/green + text feedback + explanation
→ a wrong answer creates a MistakeRecord; results show the mistakes count
→ completes → sees score
→ completed_quiz event row exists, inserted in the SAME transaction as the score
→ Start Over → new attempt → 10 newly generated question rows from a new AI request
   (textual novelty is NOT guaranteed in Stage 5 — see Generation note)
NEGATIVE (two-surface): unpublished/unassigned → no quiz in UI AND availability/start/detail/answer/
  complete return 404. Non-student → 403. Lecturer cannot start an attempt.
UNPUBLISH-MID-ATTEMPT: start while published → unpublish → all endpoints 404; re-publish → resume.
DETERMINISTIC-ONLY (adapter, not real provider): answer all correctly → score=100 →
  perfect_quiz_score event exists. (Cannot be asserted against the real provider.)
```
**Generation note (anti-repeat deferred):** the prompt instructs varied phrasing; Stage 5 does NOT enforce textual non-repetition (Stage 6 pooling does). The gate promises new question *rows from a new request*, not guaranteed-different *text*.

---

## Cross-stage seams (explicit tests)

```
S1  4.6 supersession × quiz: start → replace transcript → in-flight attempt stays answerable/scores
    (snapshotted) → a NEW attempt uses the NEW summary.
S2  4.7 visibility × quiz: availability+start resolve through StudentSummaryAccessPolicy;
    unpublished/unassigned → 404 on UI-absence AND direct API call (two surfaces).
S3  4.5 infra: AIRequestLog before the call; limiter on the path; deterministic adapter in CI;
    real-provider smoke (rule 11) with model-ID echo asserted against the CONFIGURED identifier.
S4  Atomicity: forced failure after the score write but before commit rolls back BOTH score and
    completed_quiz event.
S5  Idempotency: re-generation no-ops; re-completing emits no duplicate event; re-answering returns
    the ORIGINAL feedback and creates no second StudentAnswer (UNIQUE) and no second mistake;
    Start race → resume.
S6  Lockout/recovery: a generating attempt is recovered to `failed` via (a) enqueue-failure
    compensating path, (b) worker failure handler, (c) reaper for a LOST job — and NOT reaped while
    legitimately queued behind a backed-up AI queue. The reaper ALSO finalizes the linked
    AIRequestLog. After failure, Start Over works.
S7  Unpublish-mid-attempt: in-flight attempt becomes 404 on all endpoints while hidden; no event
    fires while hidden; re-publish → resume. (Distinct from S1.)
```

---

## Sub-sessions (spec each before implementation)

```
5a  Foundation — NO AI.
    platform/events: StudentActivityEvent (occurredAt timestamptz) + EventRecorder (same-txn emit,
      (eventType,sourceId) unique; test proves same-transaction insert + idempotency; no consumer).
    Quiz schema: QuizDefinition (no persisted status, no summary pointer); QuizAttempt (provenance +
      score fields); QuizQuestion (attempt-snapshot + Stage-6 nullable columns); AnswerOption;
      StudentAnswer (UNIQUE(quizAttemptId,quizQuestionId)); MistakeRecord (full Slice 3 fields,
      denormalized sourceQuizDefinitionId + moduleId, UNIQUE(sourceQuizAttemptId,sourceQuestionId)).
      Indexes: partial-unique post_class definition; partial-unique one-active attempt;
      UNIQUE(studentId,quizDefinitionId,attemptNumber); all integrity FKs.
    platform/query: PaginatedResponse envelope; READ-ONLY availability model (no row creation).
    DTO + HTTP-status contracts drafted (student-safe shapes; no isCorrect leak; 403/404 split).
    HARD GATE: schema + event spine land before any generation code exists.

5b  Generation pipeline + recovery.
    post_class_quiz_generation prompt (flat file, versioned, max_tokens, optionsPerQuestion);
    generate_post_class_quiz job (job_id "quiz-generate:{attemptId}", RQ timeout, stored generationJobId);
    gateway structured-output call (mechanism confirmed against codebase);
    OutputValidator (structure + size + escape-not-reject, authoritative);
    ATOMIC persist+provenance+flip (single transaction); fencing; enqueue-after-commit + compensating
    enqueue-failure; worker failure handler (primary) + 4.6c reaper extension (liveness-not-age safety
    net that also finalizes the orphaned AIRequestLog on `crashed`).
    Deterministic adapter extended with valid + forced-invalid quiz fixtures.

5c  Answer / feedback / scoring / retake.
    Visibility on ALL endpoints; answer endpoint (immediate feedback, option-identity, three-way
    integrity, DB-enforced idempotent re-answer); MistakeRecord on incorrect (idempotent snapshot);
    complete (FOR UPDATE, all-answered-gated, atomic score + events); Start Over; attempts list.

5d  Student UI + gates.
    Reusable MCQ components (API-agnostic; math = escaped plain text; answers final); quiz panel
    states; generating poll; resume; accessible feedback; results + mistakes count + Start Over;
    failed; history line. Browser gate + full active Playwright suite (rule 14, --workers=1) +
    real-provider smoke in knowledge/steps/stage-05/5d-real-provider-smoke.md (rule 11, model-ID echo).
```

---

## Done means

```
Event spine in platform/events; completed_quiz + perfect_quiz_score emitted in the same transaction
  as the score; occurredAt tz-aware UTC; idempotent; no consumer.
One AI call per attempt through the 4.5 gateway; AIRequestLog before the call; OutputValidator
  (structure + size + escape-not-reject) authoritative; persist+provenance+flip atomic; deterministic
  adapter (valid + invalid fixtures) in CI only.
One-active invariant enforced; stuck `generating` recoverable via three paths, not reaped while
  legitimately queued; reaper finalizes orphaned AIRequestLog; enqueue-after-commit + compensating
  failure honoured.
Reads create no rows; availability computed; get-or-create only on Start.
StudentAnswer DB-idempotent (UNIQUE); option-identity correctness; three-way integrity; never leaked early.
Visibility re-checked on every student endpoint; non-student 403; unpublish hides in-flight (404).
Attempt-level provenance recorded; MistakeRecords carry denormalized definition/module ids.
Plain retake from terminal state; resume on reload; answers final once submitted.
Pagination envelope defined; first genuine list consumer deferred per ADR-041 (Stage 6 mistakes-bank /
Stage 7 glossary lists).
Reusable, API-agnostic MCQ components shipped for Stage 7 reuse.
Backend tests pass; frontend tsc + Vitest pass; OpenAPI client regenerated + committed.
Browser gate passes; full active E2E suite green; real-provider smoke recorded.
Knowledge files updated in the same commit, incl. roadmap status table (rule 12/14).
```

---

## Exclusions

```
recap_period / exam_prep / mistakes_bank MODES (Stage 6).
AssessmentScope, coveredWeeks, week-scoped generation (needs Stage 5.5).
Mistake-review prefix, retakeCorrectCount, the 2-correct rule, concept dedup, mistakes-bank UI (Stage 6).
Question pool / per-attempt sampling, anti-repeat enforcement (Stage 6).
Any gamification consumer, streak, badge (Stage 10) — events emitted, not consumed.
KaTeX / math rendering (D-MATH defers to Stage 7's shared component).
`abandoned` status / abandon-from-in-progress (D-ABANDON).
In-place generation retry of a failed attempt (Start Over makes a new attempt instead).
True/false, short-answer, essay; lecturer-authored questions; manual editor; approval workflow.
Generation from raw transcript, PDFs, or lecturer notes — detailed summary is the sole source.
Any grade / progress / official-record write.
```

---

## ADRs to record

**Numbering:** the labels below (040–045) are PLACEHOLDERS for six decisions and are almost certainly already taken — 4.6–4.9, 4.5.1c (≈051–053), and Stage 12 (≈048) have issued ADRs past 039; expect the real floor **≥054**. At authoring time, grep `decisions/` for the current max, number these six sequentially from there, and update the in-spec cross-references (locks 2/3/4/5/8 reference ADR-044/045 by name).
```
(A) Lazy per-attempt quiz generation (vs pre-generated marker quizzes).
(B) Event spine: same-transaction emit; (eventType, sourceId) idempotency; sourceId = action
    instance; tz-aware occurredAt; metadata contract; domain owns the commit; no consumer.
(C) Structured quiz output mechanism (tool-calling vs JSON path); OutputValidator authority
    (structure + size + escape-not-reject) regardless of mechanism.
(D) Offset-based pagination envelope as the platform standard.
(E) QuizDefinition availability + active-summary resolution: computed availability (read-only,
    no GET-side writes), no persisted readiness status (Slice 3 deviation), no summary pointer
    (snapshot on the attempt), 404-not-403 hidden, 403 non-student.
(F) QuizAttempt lifecycle: one-active invariant, attempt-number uniqueness, resume-vs-restart,
    atomic persist+provenance+flip, three-path stuck-generating recovery (enqueue-failure / worker
    handler / liveness reaper) incl. orphaned-AIRequestLog finalization.
```

---

## Mandatory knowledge updates (rule 12)

```
knowledge/specs/stage-05/  5a–5d specs (this file is the stage spec)
knowledge/plans/stage-05/  5a–5d plans
knowledge/steps/stage-05/  5a–5d step reports + 5d-real-provider-smoke.md
knowledge/decisions/       six ADRs (numbered from the current decisions/ max — see above)
knowledge/STATUS.md        Stage 5 progression
knowledge/roadmap.md       Stage 5 status table (same commit that closes the stage)
knowledge/steps/findings-5*.md  as needed (rule 10/13)
```

---

## Revision log

**v1.1 — self-review.** Stuck-`generating` lockout (one-active invariant + recovery + resume); float-eq perfect score (→ counts); exploitable option-identity (three-way integrity); unpinned enqueue (→ enqueue-after-commit); stale summary-pointer (→ none on definition, snapshot on attempt); undefined event metadata (→ defined); gate testability (→ adapter quiz fixture, split assertions). Plus score-as-percentage, idempotent re-answer, completion row-lock, museum-endpoint tie-in, lecture/lab restriction.

**v1.2 — external review #1 triaged.** Accepted: prereq wording (4.8 NON-BLOCKING, "BACKEND VERIFIED ≠ done"); removed GET-side writes; explicit HTTP status contract; visibility on every endpoint (→ S7); mechanically precise recovery (deterministic job_id, compensating enqueue-failure, worker handler + liveness reaper); attempt-level provenance; explicit no-leak DTOs + AnswerFeedback; Start-race → resume + UNIQUE(student,definition,attemptNumber); OutputValidator size limits; reusable MCQ components. Refined: split ADR-044/045; dropped persisted QuizDefinition.status; QuizQuestion = attempt-snapshot + Stage-6 nullable columns; score DECIMAL(5,2). Held: anti-repeat for Start Over (gate language weakened instead).

**v1.3 — external review #2 triaged.**
```
ACCEPTED (must-fix 1–3 + schema items):
  1. StudentAnswer UNIQUE(quizAttemptId,quizQuestionId) + IntegrityError→original — the only
     mutating endpoint that lacked DB-enforced idempotency; double-submit corrupted correctCount.
  3. Persist+provenance+flip pinned to ONE transaction → `generating` provably means "no questions";
     reaper unambiguous; fencing no-questions clause now belt-and-suspenders.
  4b. "no HTML" = escape-on-display, not reject-on-`<` (math/code contain `<`/`>`); store raw.
  5. MistakeRecord aligned to Slice 3 minimum — denormalized sourceQuizDefinitionId + moduleId.
  6. Reaper finalizes the orphaned AIRequestLog on `crashed` (stops cost-dashboard leak).
  Smaller: occurredAt = tz-aware UTC; non-student 403 uniform on all endpoints; explicit capacity
  note (reasoning route = tightest budget × burstiest event; route is a config knob, re-route = ADR);
  F-4.9-5 CI-gate caveat in prerequisites.
NOTED (#2): ADR numbers stale — labels are placeholders; grep decisions/ for the real max (≥054).
DEFAULTED (no product preference given):
  D-MATH: raw escaped text in Stage 5; KaTeX deferred to Stage 7's shared component (flippable).
  D-ABANDON: no abandon-from-in-progress; answers final once submitted, stated in UI (flippable).
```
