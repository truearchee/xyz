---
title: Stage 7 — Interactive Glossary & Practice (stage spec)
status: approved
updated: 2026-06-17
---

# Stage 7 — Interactive Glossary & Practice (Implementation Spec)

> Filed verbatim from the tech lead's v1.1 LOCKED spec (this session). Implementation tracked in
> [[steps/stage-07/7a-glossary-foundation]] + [[steps/findings-stage-07]]; decisions
> [[decisions/adr-047-glossary-subject-folder-separation]],
> [[decisions/adr-048-glossary-definition-cache-collapse]]. Confirmed decisions: D1 migrations 0030–0031;
> D2 minimal additive shared-infra + mitigations; D3 reuse BriefSummary for definitions.

**Status (implementation):** 7a BACKEND VERIFIED; thin UI built + type-checked; live browser gate pending. 7b/7c/7d not started.
**Status (original spec header):** NOT STARTED
**Spec version:** **v1.1 (LOCKED)** — supersedes v1.0. Changes from v1.0 are summarized at the end (“What changed in v1.1”).
**Roadmap source:** Roadmap v3.1, Stage 7 (this spec is the per-stage expansion of that entry).
**Design input:** Design Plan **§2.5** — glossary layout (folder sidebar, table/card toggle), entry detail sheet **with tabs**, save-to-glossary popover, duplicate warning, flashcard session with flip + rating row, Learn/Test reusing §2.4 quiz components, the translation action/display, and the manual-entry modal. Per the two-input rule, each 7.x sub-spec is written from this roadmap entry + §2.5 together, locked before implementation.

> **⚠️ READ THIS FIRST — PARALLEL WORK WITH STAGE 6**
> Stage 6 (Complete Quiz Modes) is being built **at the same time as this stage, by a different agent.** Both stages touch two shared areas: the **Stage 5 quiz components** and the **shared AI pipeline (`platform/llm`)**. The single biggest risk in this stage is the two agents silently overwriting each other's work, or colliding on Alembic migration numbers. The **Parallel-work coordination** section below is mandatory. If anything in it is unclear, or you find yourself needing to change a shared file, **stop and escalate (rule 10)** before touching it.
>
> **Stage 7 depends only on Stage 5 (done), not on Stage 6.** That is *why* parallel work is safe — provided the file-collision and migration-block discipline below holds. The roadmap sequences 7 after 6; running them together is a deliberate choice whose only real cost is coordination on shared files.

---

## One framing that drives the whole stage

**AI is called once per term — when it is saved — to write its definition. AI is NOT called during practice.**

Flashcards and Multiple-Choice run entirely on terms the student has already saved. Multiple-Choice builds its wrong-answer options by **sampling the student's other saved terms**, not by generating new questions. This keeps the stage cheap (rule 15), fast, and simple, and it means the only real AI path to harden here is *definition generation at save time*.

---

## Scope decision — phased, build the foundation first

This stage is deliberately **phased**. The roadmap's original Stage 7 line said "flashcards + Learn/Test MCQ." The product owner has since described a richer Quizlet-style practice experience (written/typing tests, true/false, matching, a customizable test-setup modal). That is good direction but materially larger, so it is split so a verifiable thing ships sooner.

**Stage 7 (this spec) delivers:**
1. The glossary **foundation** — saving terms (highlight-to-save from summaries, plus manual add), the personal word list, AI definitions filling in asynchronously, five-language support, duplicate detection, source references, entry management (archive, surfaced to the student as “delete”).
2. **Flashcards** practice mode.
3. **Multiple-Choice** practice mode.
4. **Highlight-to-save from quizzes** — built **last** and **coordinated with the Stage 6 agent** (see 7d and the coordination section), because it mounts a component onto quiz screens that Stage 6 is actively rebuilding.

**Deferred to Stage 7.x (separate spec, after 7 is FULLY VERIFIED):**
- Written / typing tests
- True/False mode
- Matching mode
- The full customizable "Set up your test" modal (question count, answer-direction, per-type toggles)
- **On-demand re-translation of an existing entry into a different language** (the design plan's "translation action/display" maps here).
- **Folder-scoped practice** (Stage 7 practice is course-or-all only — see Decisions).
- Other MCQ directions (term→definition, formula→explanation). **Stage 7 ships definition→term only.**
- **Text-to-speech / audio buttons — explicitly OUT of Stage 7 and 7.x.** Product decision: not implementing audio. Do **not** build audio buttons or wire up TTS anywhere, even though the Quizlet reference shows them.

The Stage 5 schema and pagination envelope are reused as-is; nothing in the deferred list requires reopening Stage 5 work.

---

## Data model — `subject` vs `folder` (READ BEFORE WRITING ANY MIGRATION)

This is the foundational decision the whole stage keys off. Slice 6 treated “subject” and “folder” as the same thing; this spec separates them, because Stage 7 introduces an **Unsorted inbox**, **movable folders**, and **course-scoped practice** — none of which are coherent if folder == subject == dedup-key.

**Two independent axes:**

- **`subjectId` — the course/module a term belongs to.** This is the **dedup, cache, and practice-scope dimension.**
  - On **highlight-save from a summary**, `subjectId` is **derived from the module of the source summary/section** — the student is not asked.
  - On **manual add**, the student **chooses the course** (from the modules they are enrolled in). This is a required field on the manual-entry modal.
  - `subjectId` is effectively immutable after creation (it is part of the dedup key). Moving a term *between subjects* is not a Stage 7 feature.

- **`folderId` — a free-form organizational bucket, per student.** Pure display/organization.
  - **Default destination is the student’s “Unsorted” inbox folder** (nullable `folderId` resolves to Unsorted, or Unsorted is a real row created lazily — implementer’s choice, but a highlight-save must never block on a folder prompt).
  - The student can **move an entry into another folder later.**
  - `folderId` does **NOT** participate in dedup, cache, or practice scope in Stage 7. A folder may contain terms from multiple subjects; that is fine.

**Two distinct keys — do not conflate them:**

| Purpose | Key | Scope | Notes |
|---|---|---|---|
| **Duplicate detection** | `studentId + normalizedTerm + subjectId` | per-student | **Language-independent.** First save wins the entry; the entry keeps the language it was generated in. Changing language preference does **not** create a second entry for the same term+subject. |
| **Definition cache** | `normalizedTerm + subjectId + entryType + language` | **shared across all students** | One cached definition **per language**. Invalidated only on the definition prompt’s `promptVersion`. A cache hit = **no model call**. |

**`GlossaryFolder`** (per student)
```
- id
- studentId            (FK)
- subjectId            (nullable; folders are cross-subject by default. If you choose to
                        scope folders to a subject, do it consistently — but Stage 7 does
                        not require subject-scoped folders.)
- name
- isSystem             (true for the auto-created "Unsorted" inbox; not user-deletable)
- status: active | archived
- createdAt / updatedAt
```

**`GlossaryEntry`** (per student)
```
- id
- studentId            (FK)
- subjectId            (FK module/course) — REQUIRED. Dedup + cache + practice-scope key.
                        Derived from source on highlight-save; chosen on manual-add.
- folderId             (FK GlossaryFolder, nullable → resolves to the student's "Unsorted")
- term                 (the display term, AS ENTERED; expected English). NO separate
                        AI-generated "canonical English" form — see normalization note below.
- normalizedTerm       (lowercase, trimmed, internal-whitespace-collapsed — server-side only;
                        the dedup-key component)
- entryType: term | formula | vocabulary | concept
- language             (the language the stored definition was generated in — one of the five;
                        pairs with the cache key; needed for correct display incl. Arabic RTL)
- shortDefinition
- detailedExplanation
- example
- formulaLatex
- definitionStatus: pending | generated | failed | manual
- status: active | archived          ← "delete" archives; the row is preserved (Slice 6 rule)
- createdAt / updatedAt
```
*(Definition field shape follows Slice 6. Stage 5/5.5 are done; Slice 6 is the data-model authority for the glossary domain.)*

**`GlossarySourceReference`**, **`GlossaryDefinitionCache`** (with the `language` dimension added to its key), **`GlossaryReviewState`**, and the practice tables (`GlossaryPracticeAttempt` / `…Question` / `…AnswerOption` / `…Answer`) follow Slice 6 as-is, with the cache-key change noted above. Correctness on a practice answer option is stored **on the option (identity), never on display position.**

**Normalization note (closes the “canonical English” ambiguity):** the **term is stored exactly as the student highlighted or typed it** (we expect English input — highlights come from English summaries; manual-add expects an English term). `normalizedTerm` is purely the lowercase/trim/collapse transform of that text, computed server-side, used for dedup and the cache key. **There is no AI normalization or translation step at save time** — that would be a second model call and violate the one-call-per-save rule. Handling non-English *input* terms is a 7.x concern.

---

## How saving a term should work (user experience)

Three entry points, one result (a saved glossary entry):

1. **Highlight-to-save from a summary.** A student reading a brief or detailed summary selects some text. A small "Save to glossary" popover appears. They confirm; the term is saved. `subjectId` is derived from the summary’s module; the entry lands in **Unsorted**. *(7a — safe, Stage 6 does not touch summaries.)*
2. **Manual add.** The student opens their glossary and types a term in via the manual-entry modal. The modal **requires a course selection** (the `subjectId`) and entry type; folder defaults to Unsorted. *(7a)*
3. **Highlight-to-save from a quiz.** Same gesture, available on quiz question/answer text. This is **read-only** highlighting — it never changes the quiz. *(7d — coordinated with Stage 6; see below.)*

**The definition appears asynchronously.** When a term is saved, the entry appears in the list **immediately** with a "generating…" state, and the student keeps reading or browsing. The AI definition fills in a moment later — the same pattern already used for lecture summaries. The student never waits on a blocking spinner.

**Duplicate handling.** If the student tries to save a term they already have (same `normalizedTerm`, same `subjectId`), they see a duplicate warning instead of a second copy being created. Detection is **server-side** — the client must not be the only thing preventing duplicates. On a confirmed duplicate, attach a **new source reference** to the existing entry rather than creating a second entry (Slice 6 behavior).

**Source reference.** Each saved entry remembers where it came from (which summary/section, or "manual," or which quiz), so the student can trace a term back to its lecture.

**Managing entries.** The student can **“delete”** an entry — which **archives** it (status → archived; hidden from all glossary and practice views; row and its events preserved). (Editing the term text and re-generating is optional; if not built here, defer to 7.x — but archive-style delete is required in Stage 7.)

---

## Definitions in the student's language

Supported languages: **English, Arabic, Chinese, Spanish, French.** The **term** is always stored canonically in **English** (it is the dedup key, and we expect English input). What gets localized is the **definition**.

**CONFIRMED MODEL (product owner):** the student sets a **language preference** (in their settings; default English). When a term is saved, its definition is **generated directly in that language** — there is no separate "translate" step in the default flow. A Chinese-preference student saves "mitochondria" (the English term) and gets a Chinese definition.

- This is **one AI call per saved term** (rule 15) — the localized definition is produced in a single generation.
- **The roadmap-required `TranslationService` abstraction is this language-aware generation path:** given a term + context + target language, it returns a localized definition. It stays an abstraction so the provider/model can be swapped later (e.g. DeepL, per the post-MVP watchlist) without touching callers.
- Changing the preference applies to **new** saves; existing definitions keep the language they were generated in (no silent mass-regeneration, no surprise cost). Re-generating an existing term into a different language **on demand** is deferred to **7.x** — this is what the design plan's "translation action/display" maps to.

**Cache design:**
- **Definition cache** — keyed `normalizedTerm + subjectId + entryType + language`, invalidated on the definition prompt's `promptVersion`. The `language` dimension is **required** because the same term has a distinct definition per language. The cache is shared across students, so the *second* Chinese-preference student to save "mitochondria" in the same subject gets a **cache hit** — no model call.
- **A cache hit means no model call** — the primary cost control.
- **Concurrent-miss protection:** the one-active / idempotency guard for in-flight definition jobs is keyed on the **cache key** (`normalizedTerm + subjectId + entryType + language`), and the job **re-checks the cache at start**. This collapses two students saving the same term/subject/language *before the first generation completes* into a single model call (otherwise the “second student gets a cache hit” guarantee only holds after the first fill).

**Arabic is right-to-left.** The definition display must render RTL text correctly, including the common mixed case of an English term shown above an Arabic definition. The display container sets `dir="rtl"` (or equivalent CSS logical-property direction) for RTL-language definitions. A layout that breaks on mixed LTR/RTL content is a **finding (rule 10)**, not something to work around.

**Provider + priority.** Definition generation uses **K2-V2-Instruct via Cerebras** (per the slice), through the **existing shared Redis limiter and the existing `ai` RQ queue** — **no new AI infrastructure is built in this stage.** It uses **background priority** in the limiter; the interactive-priority headroom stays reserved for the Stage 8 assistant (rule 15). A 500-character context cap is enforced server-side.

---

## Backend scope

Carried from Roadmap v3.1 Stage 7 / Slice 6, with the platform rules made explicit:

- **Folders** — students organize entries into folders; an **"Unsorted" inbox** is the default destination for highlight-saved terms. See the data-model section for the `subject` vs `folder` split.
- **Entries** — saved term, normalized term (dedup key), entry type, source reference, review state, `subjectId`, `folderId`, `language`, `status`. See data model.
- **Source references** — link back to the originating summary/section, a quiz, or "manual."
- **Definition cache** (keyed including `language`) as specified above.
- **Review state** — per entry, to drive flashcard/practice progress.
- **Flashcards** with hardcoded review intervals (no adaptive SRS this stage).
- **Multiple-Choice** reusing Stage 5 **answer/correctness/shuffle mechanics** — correctness keyed on option **identity**, never display position. **Direction is definition→term only in Stage 7.** **Wrong-answer options are sampled from the student's other in-scope terms; no AI call per question.** Requires **≥4 in-scope terms**; below that, Multiple-Choice is unavailable and the student is offered Flashcards.
- **Server-side duplicate detection** on `studentId + normalizedTerm + subjectId`.
- **`TranslationService` abstraction + K2Think adapter** — the language-aware definition-generation path (see above); built so a different provider (e.g. DeepL) can be swapped later without touching callers.
- **`<SaveToGlossary>` shared component** — one reusable component, used by the summary surface (7a) and the quiz surface (7d).
- **KaTeX integrated in 7a (early, not bolted on later)** — terms/definitions from technical lectures contain formulas and must render from the start.
- **Entry archive (“delete”)** (and optional edit).

**AI artifact rules (rule 6 — mandatory):**
- Every generated definition is an AI-generated artifact and **carries the full provenance set**: `modelId`, `promptVersion`, `backendUsed`, source/input hash, `generatedAt` — enforced by DB constraints where practical.
- Each generation job carries an **idempotency key** and a **one-active partial-unique index** for in-flight jobs of that type (extend the migration-0007 pattern used by summaries). Per the concurrent-miss note above, **the one-active index is keyed on the cache key**, so a double-click *and* two students racing the same term cannot both produce a generation.
- Every definition generation writes an **`AIRequestLog`** row with a clear `feature` label (`glossary_definition`) so "tokens by feature by day" stays one query.
- A light **OutputValidator** check: the definition is **non-empty** and **is not an echo of the prompt** (these are hard rejections → retry). A **language check is a logged soft signal, not a hard reject** — short bilingual technical definitions (e.g. a Chinese definition full of Latin-script terms and formulae) trip naive language detectors and would cause spurious retries (rule-15 waste) and stuck “generating” states. Log a mismatch warning; do not reject on it. (No rich section structure is required, unlike the detailed-summary validator.)

**Authorization (personal scoping):** the glossary is **personal per student**. Every glossary endpoint is scoped to the authenticated student; a request for another student's entry returns **404, not 403** (matching the roadmap's student-resource pattern). One student must never be able to read or practise another's glossary. This must be covered by a test (see the security note under Suggested skills).

**Events (rule 7):** glossary actions emit `StudentActivityEvent`s through `platform/events`; the glossary **emits, never owns** them. Name at least:
- `glossary_term_saved` — on a successful save
- `glossary_practice_completed` — on finishing a practice session

The event insert commits **in the same DB transaction** as the source action; the idempotency `source_id` points to the action instance (the entry id / the practice-session id). Stage 10 gamification will later consume these, so they must be reproducible from events. **This is also why “delete” archives rather than hard-deletes** — the events and the rows they reference must remain.

**Reads (rule 8):** the glossary never imports the quiz domain (or vice versa). Any cross-domain read goes through `platform/query` (read models only). Entry lists use the **Stage 5 pagination envelope** — do not invent a new one.

---

## Thin UI scope (Stage 7)

Built on the Stage 4.9 styling system and Stage 5 quiz components — no new component-library work beyond what §2.5 specifies.

- Glossary view: folder sidebar, term list (table/card toggle per §2.5), empty state per §2.5.
- Entry detail sheet **with tabs** (per §2.5), showing term, definition (in the student's set language), and source reference. *(An on-demand re-translate-to-another-language action is 7.x, not Stage 7.)*
- Save-to-glossary popover (the `<SaveToGlossary>` component).
- Manual-entry modal — **includes a required course (`subjectId`) selector** and entry-type selector; folder defaults to Unsorted.
- Duplicate warning.
- "Generating…" state on a freshly saved entry while its definition is produced.
- “Delete” control (archives).
- **Flashcards session:** card showing the term; flip to reveal definition; **both** keyboard shortcuts (Left = "study again", Right = "I know this") **and** an on-screen **rating row** with the same two actions (mobile/touch users can't press arrow keys — the rating row is required, not optional); a progress tracker (e.g. "1 / 143"). **No audio button.**
- **Multiple-Choice practice (definition→term):** the definition is shown; the student picks the correct **English term** from **4 options** (1 correct + 3 deck-sampled distractors); a **"Don't know?"** control that **reveals the correct answer and records the item as not-known** (so it stays in review). **No audio button.**
- **Practice scope selector:** before a session, the student chooses **a specific course** or **all their saved terms** (confirmed model). The ≥4-term minimum for Multiple-Choice applies *within the chosen scope* (a course with fewer than 4 saved terms offers Flashcards only). Note: under the “all terms” scope, distractors may be sampled cross-subject — acceptable for MVP.

---

## UI proof obligation

A student (whose preferred language is, say, Arabic) highlights text in a **real** summary, saves it, and watches the **Arabic** definition fill in **asynchronously** (no blocking wait) and render **right-to-left** (`dir="rtl"`). They then choose a practice scope (a course, or all their terms) and practise in **both** Flashcards and Multiple-Choice — all in a real browser, against the real backend, through the logged AI infrastructure. A duplicate save is visibly rejected. A **second student cannot see the first student's entries**. A component rendering against a mock does not satisfy this (rules 2, 9).

---

## Browser gate

```
Student opens a published summary → highlights text → Save to glossary
→ entry appears immediately in "generating…" state (subject derived from the summary's module,
   landing in Unsorted)
→ AI definition fills in asynchronously, generated in the student's set language
   (cache miss = one model call, logged in AIRequestLog, full provenance stored)
→ an Arabic-preference student's definition container asserts dir="rtl" (+ manual QA confirms
   the mixed English-term / Arabic-definition layout reads correctly)
→ saving the SAME term again (same normalizedTerm + subjectId) → duplicate warning, no second
   entry (a new source reference may attach to the existing entry)
→ manual add (course + type chosen) → entry created
→ student "deletes" an entry → it disappears from all views (row archived, not destroyed)
→ student chooses a practice scope (a specific course, or all saved terms)
→ open Flashcards → term shown → flip reveals definition
   → Right (or on-screen "know") advances; Left (or on-screen "study again") re-queues
   → progress tracker updates (n / total)
→ open Multiple-Choice (scope has ≥4 terms) → definition shown → 4 options (deck-sampled)
   → correct pick accepted, wrong pick rejected → "Don't know?" reveals answer, records not-known
   → (scope with <4 terms: Multiple-Choice unavailable, Flashcards offered)
→ glossary_term_saved and glossary_practice_completed events inserted via the
   StudentActivityEvent spine, in the same transaction as their action
→ SECOND student / browser context cannot read the first student's entry (404)
→ real-provider smoke recorded (rule 11): one definition generated against the REAL K2Think
   provider, model-ID echo asserted to match the configured identifier
→ FULL active E2E suite re-runs green (rule 14)

[7d, coordinated with Stage 6:]
→ student highlights text in a quiz (when reviewing answers after an attempt) → Save to glossary
   → entry created with a quiz source reference
```

---

## Parallel-work coordination (Stage 6 is live at the same time) — MANDATORY

Stage 6 and Stage 7 both reuse **Stage 5 quiz components** and the **shared AI pipeline**. To avoid the two agents overwriting each other:

1. **Consume the shared AI pipeline; never modify it.** Both stages call through the existing `platform/llm` gateway, the shared Redis limiter, and the `ai` RQ queue. **Neither stage changes those files.** If you believe a change to shared AI infrastructure is required, **stop and escalate (rule 10)** — do not edit it unilaterally. Glossary prompts are **NEW flat files** under `/prompts` (e.g. `prompts/glossary_definition/...`); never edit summary or quiz prompts.

2. **Reuse Stage 5 quiz mechanics; do not fork or rewrite them.** Stage 6 is actively extending quiz modes. If Stage 7's Multiple-Choice needs behavior the Stage 5 components don't expose, **do not copy-paste a private variant** and **do not edit the shared quiz component to suit the glossary.** Write a findings note (`knowledge/steps/findings-stage-07.md`) describing exactly what you need, and escalate so it can be coordinated.

3. **The quiz-highlight feature (7d) is the sharpest collision point — do it last and coordinate.** Mounting `<SaveToGlossary>` onto quiz screens means editing the quiz question/answer surface, which Stage 6 is actively rebuilding (mode selector, recap, exam-prep, retake banners). **Before building 7d, confirm with the Stage 6 agent that the quiz question-card structure has settled, and agree on where the highlight affordance attaches.** Everything else in Stage 7 (7a–7c) lives in the glossary domain and does not touch Stage 6's files — build that first.

4. **Do not touch Stage 6's files.** Stage 6 owns the quiz-mode selector, recap/exam-prep scope, mistakes-bank, retake reinforcement, and `AssessmentScope`. Glossary work stays in the glossary domain.

5. **Migrations — reserved block (this replaces v1.0's "grab the next free number"):**
   ```
   Stage 7 owns the reserved Alembic migration-number block 0030–0039.
   Number EVERY Stage 7 migration within 0030–0039, in order.

   Context (do not re-derive): Window 1 consumed through 0020
     — Stage 5: 0013–0017, Stage 5.5: 0018–0019, 4.9: 0020.
     Stage 6 (the other live Window-2 stage) owns the block BELOW 0030.

   At branch creation: confirm 0030 is free against BOTH main HEAD and the live
     Stage 6 branch. If 0030 (or anything in 0030–0039) is already taken — i.e. the
     blocks have drifted — STOP and escalate (rule 10). Never renumber opportunistically
     or grab "the next free number"; that is the collision the reserved blocks exist to
     prevent. At merge, fix only your first migration's down_revision to the current head.
   ```

6. **The full E2E suite is the shared safety net (rule 14).** When you close a sub-session, the **entire** active Playwright suite re-runs — including Stage 6's specs once they've merged. Green inherited from your own branch is not green. If a Stage 6 spec fails after your change, that is a real signal — escalate, don't silence it.

7. **`platform/query` stays read-only; domains never import each other (rule 8).**

8. **OpenAPI client is regenerated on main only**, after each merge — never merge a regenerated client from this branch.

If plan and reality disagree at any point, **stop and write a findings note** rather than forcing a test to pass (rule 10).

---

## Sub-sessions (specs written before implementation)

Each gets its own spec and browser gate before the next begins. The foundation must land before practice modes; the quiz-highlight integration comes last.

```
7a  Glossary foundation: folders (+ "Unsorted" inbox), entries with subjectId/folderId/language,
    server-side normalized-term dedup (studentId + normalizedTerm + subjectId), source references,
    archive-style delete, TranslationService + K2Think adapter, definition cache (keyed incl.
    language) with concurrent-miss protection, <SaveToGlossary> (wired into SUMMARIES only),
    async "generating…" state, manual-entry modal (course + type), KaTeX, glossary_term_saved
    event, personal-scoping authz (404 cross-student), language preference setting, definitions
    generated in the student's set language (any of the five) incl. Arabic RTL (dir="rtl").
    HARD GATES:
      - definition generation goes through the EXISTING ai queue + limiter at
        BACKGROUND priority; no new AI infrastructure introduced.
      - every generated artifact carries the full provenance set + idempotency key
        + one-active index keyed on the cache key (rule 6); AIRequestLog written.

7b  Flashcards: card UI, flip, keyboard shortcuts AND on-screen rating row,
    progress tracker, practice-scope selector (a course, or all terms),
    review-state persistence, glossary_practice_completed event.

7c  Multiple-Choice (definition→term): definition → 4 options (correct + 3 deck-sampled
    distractors) → correctness on option identity → "Don't know?" reveals + records not-known;
    ≥4-term minimum handled. Browser gate + real-provider smoke (rule 11) +
    full active E2E suite green (rule 14) → Stage 7 (core) FULLY VERIFIED.

7d  Quiz-highlight integration (COORDINATED WITH STAGE 6 — see coordination point 3): mount
    <SaveToGlossary> on the settled quiz surface (in answer-review, not mid-attempt); entry
    created with a quiz source reference. Build only after confirming the Stage 6 quiz
    question-card structure is stable.
```

---

## Done means

- Terms save from summaries (highlight, subject derived) and manual add (course chosen); from quizzes (highlight) once 7d is coordinated and built.
- Definitions generate **asynchronously** through the **existing** AI infrastructure at **background priority**, are **logged** (AIRequestLog), and carry the **full provenance set + idempotency** (rule 6); concurrent misses collapse to one call.
- Definitions generated in the student's chosen language (any of the five) via the `TranslationService`; **Arabic renders right-to-left** (`dir="rtl"`) correctly.
- Cache hit = no model call; duplicate detection works server-side on `normalizedTerm + subjectId`.
- Flashcards (keyboard **and** on-screen rating) and Multiple-Choice (definition→term, deck-sampled, ≥4-term minimum handled), scoped to a course or all terms, both work in a real browser, with **no AI calls during practice.**
- A student can **“delete” (archive)** an entry; one student **cannot access** another's glossary (404), covered by a test.
- `glossary_term_saved` and `glossary_practice_completed` flow through the existing event spine, in the same transaction as their action.
- **Real-provider smoke recorded (rule 11)** with the model-ID echo assertion.
- Full active E2E suite green (rule 14), type-check green, OpenAPI client fresh.
- UI matches the §2.5 design input (light check, per the acceptance rule).
- Migrations confined to the **0030–0039** block; no Stage 6 files modified; no shared AI/quiz infrastructure forked.
- Knowledge files updated in the same commit, including the roadmap status table.

---

## Exclusions

As Roadmap v3.1 Stage 7, plus the decisions above:
- No shared/class glossary (personal per student only).
- No transcript sources (glossary draws from summaries, not raw transcripts).
- No OCR.
- No advanced/adaptive SRS (hardcoded intervals only).
- No AI auto-saving terms (the student always chooses what to save).
- **No AI calls during practice** — distractors are sampled from saved terms.
- **No second AI call at save** — no AI term normalization / "canonical English" generation; `normalizedTerm` is a deterministic string transform.
- **A wrong answer in glossary Multiple-Choice does NOT feed the Stage 5/6 quiz mistakes-bank.** Glossary review state is separate from course-quiz mistakes; do not wire them together.
- **No hard delete** — "delete" archives; rows and events are preserved (Slice 6 rule; required by Stage 10 event reproducibility).
- **No text-to-speech / audio buttons** (deferred indefinitely; do not build).
- **No written/typing test, True/False, Matching, the full test-setup modal, on-demand re-translation, folder-scoped practice, or MCQ directions other than definition→term** (all deferred to Stage 7.x).
- No changes to Stage 5 or Stage 6 quiz infrastructure.

---

## Decisions — confirmed and remaining defaults

1. **Definition language — CONFIRMED.** The student sets a **language preference** (default English) and definitions are **generated directly in that language** at save time. No separate translate step in Stage 7; on-demand re-translation to another language is deferred to 7.x.
2. **Practice scope — CONFIRMED.** A practice session covers **either a specific course or all the student's saved terms** — the student chooses. (Practising a single folder is a 7.x addition.)
3. **`subject` vs `folder` — DECIDED (tech lead).** `subjectId` (= course/module) is the dedup/cache/practice key; `folderId` is a separate free-form organizational layer with an **"Unsorted" inbox** default, movable later and ignored by dedup/cache/practice in Stage 7. (Supersedes Slice 6's collapsed subject==folder model, which is incompatible with this spec's Unsorted inbox + course-scoped practice.)
4. **Default destination for highlight-saved terms — CONFIRMED:** the **"Unsorted" inbox** folder, movable later.
5. **Quiz-highlight timing — default in place (changeable):** allow it **when reviewing answers after an attempt**, not mid-attempt (avoids distraction/peeking). Affects 7d.
6. **Delete semantics — DECIDED (tech lead):** "delete" is a **soft archive** (status → archived; hidden everywhere; row + events preserved). UI may still say "delete."
7. **OutputValidator language check — DECIDED (tech lead):** **logged soft signal, not a hard reject.** Hard rejections are limited to empty output and prompt-echo.

---

## Suggested gstack skills for this stage

Optional helpers for the coding agent, matched to where this stage is risky:

- **`/plan-eng-review`** before 7a — this stage shares infrastructure with a parallel stage; an up-front pass that forces the shared-file boundaries (and the 0030–0039 migration block) into the open is worth it here specifically.
- **`/review`** after each sub-session — catches the "quietly forked a shared component" class of bug this parallel setup makes likely.
- **`/qa` for the browser gate, run LOCALLY against the dev stack.** The proof obligation is heavily interactive (highlight, async fill-in, keyboard + touch, RTL), exactly what a real-browser QA pass is good at. *(Note: hosted staging from Stage 4.8 is not provisioned — there is no staging URL to QA against; run the gate against the local stack.)*
- **`/cso`** is **not** a full requirement here, but this stage introduces new **per-student private data**, so the personal-scoping rule (one student can't read another's glossary → 404) **must** be covered by a test; a light security check on those endpoints is reasonable.

---

## What changed in v1.1 (from v1.0)

1. **Added the `subject` vs `folder` data model** (the foundational gap in v1.0): `subjectId` (dedup/cache/practice key, derived on highlight-save, chosen on manual-add) and `folderId` (free-form, Unsorted default). Explicit `GlossaryFolder` / `GlossaryEntry` field lists. Two distinct keys spelled out: dedup (`studentId + normalizedTerm + subjectId`, language-independent) vs cache (`+ entryType + language`, shared).
2. **Manual-entry modal now requires a course (`subjectId`) selector** (consequence of #1).
3. **Migration coordination (point 5) replaced** "number against latest committed migration / rebase if taken" with the **reserved block 0030–0039** + branch-time verify-or-escalate guard.
4. **"Delete" defined as soft archive** (status → archived; rows + events preserved) — was ambiguous in v1.0; reconciled with Slice 6 and Stage 10 event reproducibility.
5. **OutputValidator language check demoted** from a hard reject to a logged soft signal (avoids spurious retries on bilingual technical text).
6. **Concurrent cache-miss protection added:** one-active index keyed on the cache key + cache re-check at job start.
7. **RTL made concrete:** assert `dir="rtl"` on the definition container + a manual-QA note (Playwright cannot eyeball "renders correctly").
8. **MCQ scoped to definition→term only** for Stage 7 (other directions → 7.x).
9. **"Canonical English" clarified:** term is stored as entered; `normalizedTerm` is a deterministic transform; no second AI call at save.
10. **`/qa` retargeted to local** (no provisioned staging URL).
```