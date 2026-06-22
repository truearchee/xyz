---
type: stage-spec
stage: 11
session: "11"
slug: proactive-ai-agent-analytics
status: approved
created: 2026-06-20
updated: 2026-06-20
owner: developer
plan: knowledge/plans/stage-11/11.1-roster-risk-scheduler.md
report: knowledge/steps/stage-11/11.1-roster-risk-scheduler.md
---

# Stage 11 — Proactive AI Agent & Analytics — SPEC (rev. 2)

## Linked documents
- Spec: [[specs/stage-11/11-proactive-ai-agent-analytics]]
- Session 11.1 spec: [[specs/stage-11/11.1-roster-risk-scheduler]]
- Session 11.1 plan: [[plans/stage-11/11.1-roster-risk-scheduler]]
- Session 11.1 report: [[steps/stage-11/11.1-roster-risk-scheduler]]
- Session 11.2 spec: [[specs/stage-11/11.2-student-detail-recommendations]]
- Session 11.2 plan: [[plans/stage-11/11.2-student-detail-recommendations]]
- Session 11.2 report: [[steps/stage-11/11.2-student-detail-recommendations]]
- Session 11.3 spec: [[specs/stage-11/11.3-assessment-analysis-question-insights]]
- Session 11.3 plan: [[plans/stage-11/11.3-assessment-analysis-question-insights]]
- Session 11.3 report: [[steps/stage-11/11.3-assessment-analysis-question-insights]]
- Session 11.4 spec: [[specs/stage-11/11.4-workload-planner]]
- Session 11.4 plan: [[plans/stage-11/11.4-workload-planner]]
- Session 11.4 report: [[steps/stage-11/11.4-workload-planner]]
- Roadmap: [[roadmap]]
- Design system: [[design-system]]
- Design plan: [[design-plan]]

> **What changed in rev. 2** (after the design review): canonical `riskTier` enum + label maps; a structured `RiskReason` contract; reproducibility fields (`algorithmVersion` / `inputHash` / `sourceCutoffAt`) on snapshots, recommendations, and plans; a concrete `AgentRun` idempotency key + scope/count fields; **separate lecturer/student recommendation states** (no state bleed); a backend AI **numeric-consistency validator** and a **student-copy safety guard**; explicit `.ics`, topic-mapping, small-cohort, and manual-trigger-hardening rules; **live-on-read** risk display (the scheduled run drives the proactive layer + history); **Stage 10 input isolation**; scheduler hosting + retention; and a design-plan reconciliation note. Structure (11.1–11.6) is unchanged.

**Status:** IN PROGRESS. Sessions 11.1, 11.2, 11.3, and 11.4 are FULLY VERIFIED; remaining student-planning
sub-sessions continue to be developed **in parallel with Stage 10 (Gamification)** — see Parallel Development.

**Builds on (all FULLY VERIFIED — confirm, do not rebuild):** Stage 5 (event spine), Stage 5.5 (schedule / `due_at` / `week_number` / `session_date`), Stage 6 (quiz + `StudentAnswer` data), Stage 9 (deterministic grade-forecast engine + ADR-052 single-tenant).

**Two audiences in one stage:** lecturer analytics (11.1–11.3) and student planning (11.4–11.6). The agent writes a per-sub-session spec before implementing each sub-session.

---

## Product decisions

**Locked by the founder (earlier round):**

1. **Risk visibility — lecturer full, student gentle.** The lecturer sees the full picture (tier + reasons + numbers). The student sees a gentle, supportive version of the **same deterministic data** — no alarming tier label, no peer comparison, just the actionable subset.
2. **Recommendations surface to BOTH.** The lecturer gets a reviewable **draft** (acts **manually** through their own channel — nothing auto-sends). The student gets an **in-app suggestion** (a gentle nudge shown passively — never pushed/emailed).
3. **Workload plan is READ-ONLY + `.ics` export.** No in-app editing, no "mark done." Student availability is the only student input.

**Defaults chosen in this revision — sensible, easy to change; the founder can veto any:**

4. **Risk is per-course**, not one per-student score (a student can be fine in one course and behind in another).
5. **Risk on screen is always current** (computed on read); the scheduled run drives the proactive layer (history + 48h pre-deadline recommendations). So a student who improves during the day is **not** stuck showing "behind" until tomorrow.
6. **Student nudge tone:** specific + gentle + actionable — name the topic and a next step, no alarming labels. e.g. *"Topic 3 could use a little extra time before Friday — a good next step is the recap quiz."* Not vague ("this week needs attention"), not blunt ("you're behind").
7. **Impossible grade target:** honest, paired with a constructive path — e.g. *"Reaching [target] isn't possible from your current scores. Here's what's still achievable and where to focus."* No false hope, no sugarcoating.
8. **Availability input** (one-time settings): study days (Mon–Sun), preferred window (morning / afternoon / evening / no preference), max study minutes per day. Lightweight; the plan itself stays read-only.
9. **Lecturer discoverability:** an in-app **"Needs support: N"** indicator on the roster (in-app only — no external notifications). The student side stays passive (card / banner, no alerts).
10. **Student nudge is dismissible** ("Not now") but has **no "mark done."** The lecturer can preview the student-facing nudge text (so they don't contradict it).
11. **AI phrasing ships as the last layer** of 11.2/11.6 on top of the mandatory template path — so it can be descoped to an immediate fast-follow under time pressure without restructuring.

---

## Governing constraints (apply to every sub-session)

- **Governing principle:** thin vertical slice + a browser-verifiable gate. No backend-only "done."
- **Rule 6 — AI is infrastructure:** all AI goes through `LLMGateway → PromptRegistry → ContextBuilder → RateLimiter → AIRequestLog → OutputValidator`. **Plus: a backend OutputValidator enforces numeric consistency + student-copy safety — see Canonical contracts.**
- **THE STAGE 11 HARD LINE — AI EXPLAINS, NEVER CALCULATES.** Risk tiers, grades/forecast, and the workload plan are **deterministic** and are the source of truth. Every tier traces to enumerated `riskReasons` + the `supportingMetrics` behind them. AI may only phrase/explain. If AI is unavailable, the deterministic output still renders (template fallback). **No black-box scores anywhere.**
- **Rule 7 — events:** Stage 11 **consumes** `StudentActivityEvent` only; it owns none and **introduces no new event types**.
- **Rule 8 — `platform/query`:** the agent domain reads its cross-domain inputs through `platform/query` read models — it never imports another domain. It owns its own writes.
- **Stage 10 input isolation:** risk / recommendations / plan read ONLY from **already-shipped** stages (quiz + `StudentAnswer`, `StudentActivityEvent`, schedule/deadlines, grade forecast). They must **NOT** read Stage 10 gamification data (streaks/badges) — Stage 10 ships in parallel and may be absent when Stage 11 computes; depending on it would couple the two and break independent delivery.
- **Rule 9 — testing:** real browser, real backend, real DB on the critical path. Scheduled runs are fired **deterministically in E2E** via the manual trigger + seeded temporal data — never by waiting wall-clock or mutating the clock in a shippable build.
- **Rule 11 — AI smoke:** the two AI sub-sessions (11.2, 11.6) each record a real-provider smoke with the **model-ID-echo assertion** before FULLY VERIFIED.
- **Rule 12 — knowledge:** every stage-closing commit updates the per-stage knowledge trio **and this roadmap's status table**.
- **Rule 14 — full suite:** the entire active Playwright suite re-runs at every sub-session close. Archived = deleted.
- **Rule 15 — AI capacity, request count is sacred:** the scheduled run computes deterministic snapshots for **all** students with **zero AI calls**. AI phrasing is **lazy + cached** — one call per recommendation/advice, regenerated only on `inputHash`/`promptVersion` change. **Never one AI call per student per run.** BACKGROUND priority; reserve INTERACTIVE headroom for the Stage 8 assistant.
- **Single-tenant (ADR-052):** inherited. One institution timezone is a single-tenant config value.
- **Reproducibility:** every deterministic output carries `algorithmVersion` + `inputHash` + `sourceCutoffAt` — see Canonical contracts.

---

## Canonical enums & contracts — lock BEFORE 11.1

### `riskTier`
```
internal:         on_track | watch | needs_support
lecturer labels:  "On track" | "Watch" | "Needs support"
student:          no tier label shown (gentle view shows reasons + next steps only)
```
Avoids "critical"/"failing" (wellbeing) and avoids colliding with the Stage 9 forecast status. Labels are a display map — trivial to change.

### `RiskReason`
```
RiskReason {
  code             // stable enum, e.g. "missed_recent_quizzes"
  severity         // watch | needs_support  (this reason's contribution to the tier)
  metricKeys[]     // the metrics this reason cites
  lecturerText     // deterministic, precise:  "Missed 2 of the last 3 quizzes"
  studentText      // deterministic, gentle:   "Recent quiz practice could use a little time"
  supportingMetrics  // { <metricKey>: number, ... } — must contain exactly metricKeys
}
```
`studentText` is deterministic template text → **the student gentle view needs no AI** (frugal + safe). AI is reserved for the richer 11.2 recommendation / 11.6 advice.

### `Recommendation` — separate audience state, no bleed
```
Recommendation {
  reasonCode, target, deterministicPayload,
  audience: lecturer | student | both,
  lecturerState: open | acted | dismissed,
  studentState:  visible | hidden | dismissed,
  studentShownAt, studentDismissedAt,
  lecturerAiText?, studentAiText?,            // lazy, cached
  aiProvenance { modelId, promptVersion, inputHash, generatedAt }
}
```
The lecturer dismissing their draft does **not** hide the student nudge (different surfaces, different purposes). **One active recommendation per `(student, reasonCode, target)`** — it auto-closes when the underlying problem clears, and a dismissed one is **not re-shown**. (This stops the same nudge reappearing daily and the lecturer's "acted" status silently resetting.)

### Reproducibility fields
```
StudentRiskSnapshot: agentRunId, algorithmVersion, inputHash, sourceCutoffAt, computedAt
Recommendation:      algorithmVersion, inputHash, sourceCutoffAt
WorkloadPlan:        algorithmVersion, inputHash, availabilityVersion, sourceCutoffAt, supersededAt, isActive
```
`sourceCutoffAt` pins exactly what data a computation saw → "why did this student move watch → needs_support?" is debuggable and tests don't drift after rule changes. **Retention:** keep the latest snapshot per student + a bounded history window for trends — never unbounded growth.

### Risk definitions are configurable, not magic numbers
Thresholds (what counts as "activity", the inactivity window, the missed-quiz count, etc.) live in config — like Stage 9's grade boundaries — not hardcoded. Each threshold change is an `algorithmVersion` bump. Computations bind to `sourceCutoffAt` so numbers are reproducible and the gates don't flake on timing.

### AI consistency + copy safety (backend `OutputValidator` — not just a browser check)
- **Numeric consistency (11.6):** the AI advice must not contradict, and where relevant must include, the deterministic `targetGrade`, `requiredRemainingAverage`, `forecastStatus`, `remainingWeight`, `currentWeightedScore`. **(11.2):** the AI text invents no peer comparisons, no diagnoses, no new risk reasons, and no numbers absent from `deterministicPayload`. On failure → regenerate, then template fallback.
- **Student-copy safety guard (student-facing text ONLY):** block/regenerate on banned ideas — "at risk", "critical", "failing", "behind the class", "other students", "mental health", "diagnosis", "you're not trying", and similar. Allowed shape: *"You may want to spend a little extra time on [topic]. A good next step is [action]."* **Lecturer copy is exempt** (precise language is appropriate there). This stops lecturer-risk language leaking into the gentle student view. Treat the list as a starting set the prompt + validator enforce, not a one-shot hard fail — flag and regenerate.

---

## Hard prerequisites (MET — confirm, don't reimplement)

1. Stage 5.5 schedule fields populated (`due_at`, `week_number`, `session_date`).
2. Stage 9 deterministic forecast engine (`requiredRemainingAverage = (target − current) / remainingWeight`) — **reused, not reimplemented**.
3. Stage 5 event spine + Stage 6 quiz/answer data.
4. ADR-052 single-tenant.

**New check for 11.3 (topic mapping):** each `QuizQuestion` must expose ≥1 of `topicId | sourceSectionId | sourceSummaryId | sourceWeekNumber`. If topic metadata is missing, 11.3 shows question-level analytics and marks per-topic mastery **unavailable** — it never guesses. If none exist anywhere, that's a **stop-and-escalate** (rule 10) before building per-topic mastery. If a read model is missing for any input, add it in `platform/query` — don't import the owning domain.

---

## Shared infrastructure — `platform/scheduler` (lands in 11.1)

Shared, consumed by domains (Stage 10 may use it too). Record as an ADR.

- Lives in `platform/scheduler`, mirroring the `platform/*` infra pattern.
- It only **enqueues** onto the existing RQ queues; heavy work runs in workers. Scheduled trigger → enqueue an `AgentRun` job → worker computes.
- **Idempotent**, **single-instance** (advisory lock / flock — mirrors the 4.6c reaper singleton), **failure-safe** (a missed/failed run is recorded on `AgentRun` and recoverable; never crashes the app), **timezone-aware** (against the single-tenant institution timezone).

**`AgentRun` shape + idempotency:**
```
AgentRun {
  triggerType:  scheduled_daily | pre_deadline | manual_admin
  scopeType:    all | module | student | deadline
  scopeId?:     UUID
  scheduledFor: timestamp
  triggeredByUserId?: UUID
  algorithmVersion, status, startedAt, completedAt
  snapshotCount, recommendationCount, planCount
  idempotencyKey = triggerType + scopeType + scopeId + scheduledFor + algorithmVersion
}
```
Same key → no duplicate work or rows. The "second run is idempotent" gate proves it with these counts.

**Manual trigger hardening (it's powerful — treat it as such):** admin-only (explicit **403** tests for lecturer/student roles); audited via `triggeredByUserId`; rate-limited; scope-limited where possible; and it **computes deterministic snapshots only — it never triggers AI phrasing** (keeps rule-15's "zero AI in runs"; AI stays lazy/on-view). This is also the deterministic E2E fire (don't wait for 6 AM).

**Hosting note (new process):** the scheduler is a long-running process that did not exist at Stage 4.8. Deploying Stage 11 requires running the scheduler in the hosted env, guaranteeing a **single scheduler instance** (one-per-replica → double fires), and confirming scheduled jobs only enqueue onto the already-deployed workers. Carry this into the staging / Stage 12 deploy checklist.

**Test rule:** time-dependent behavior (daily, 48h pre-deadline) is proven by **seeding data at the right temporal offsets + a manual trigger** — not by clock mutation. Any clock/test hook is test-only and absent from hosted builds (Stage 4.8 hygiene rule).

---

## Sub-sessions

### 11.1 — Roster + Deterministic Risk + Scheduler  (NO AI)

**Backend:** `platform/scheduler` + `AgentRun` (above); deterministic **per-course** risk classification → `riskTier` + `RiskReason[]` (contracts above), thresholds from config; risk computed **on read** for display (cheap aggregation at MVP scale — always current) **and** persisted as `StudentRiskSnapshot` per scheduled `AgentRun` (history + reproducibility); `platform/query` read models — full (lecturer) + gentle (student). Inputs: quiz/answers, events, schedule, forecast — **not Stage 10**.

**Thin UI:** lecturer per-course roster (tier + reasons + metrics; sort/filter by tier; the **"Needs support: N"** in-app indicator); student gentle "Where you stand" (the reasons' `studentText` + next steps; no tier; no peer data).

**UI proof obligation:** the lecturer sees a real per-course tier **with** reasons + numbers for a seeded student; the student sees the gentle version of that same data; the displayed tier reflects current data (improve the data → the display updates without waiting for the next scheduled run).

**Browser gate:**
```
Manual-admin trigger fires an AgentRun → per-student per-course snapshots computed from real data (counts on AgentRun)
→ lecturer roster shows the correct tier + reasons + metrics for the seeded student, per course
→ EVERY on-screen tier traces to ≥1 RiskReason AND each reason's supportingMetrics contains exactly its metricKeys
→ student gentle view shows studentText + next steps only (no tier, no peer data)
→ change the student's underlying data + reload → the display reflects it immediately (live-on-read)
→ a second identical trigger is idempotent (snapshotCount unchanged; no duplicate rows)
```
**Authz:** lecturer → own students/courses only; student → self only; admin → all (single-tenant ops). 403 tests for cross-access.

---

### 11.2 — Student detail + Recommendations  (lecturer draft + student suggestion)  [AI phrasing enters]

Deterministic recommendation engine first → `Recommendation` (contract above: separate lecturer/student state; one-active-per-problem; `deterministicPayload` renders via template with **no AI**). Then the lazy AI phrasing layer (gateway, cached with provenance, **one call per recommendation**, regenerated on `inputHash`/`promptVersion` change, template fallback). **AI text passes the numeric-consistency validator and — for `studentAiText` — the copy-safety guard.**

Two surfaces, one `Recommendation`:
- **Lecturer draft** — on the student-detail page: reasons + AI draft + **Copy draft / Mark acted / Dismiss** (**no Send button, ever**). The lecturer reaches out through their own channel. Can preview the student-facing nudge text.
- **Student nudge** — gentle, passive: **primary** = the My-Progress "Where you stand" card; **secondary** = a dashboard banner (≤1 active); **dismissible** ("Not now"); **never** modal / push / email / toast.

**UI proof obligation:** the lecturer opens a seeded at-risk student → an AI draft grounded in **visible** reasons (AIRequestLog + provenance) → marks it acted (`lecturerState` persists; **`studentState` unchanged**; nothing sent) → the student sees the gentle nudge → dismisses it ("Not now" → `studentState=dismissed`; not re-shown) → forced AI-down path renders the template fallback.

**Browser gate:**
```
Seeded at-risk student → deterministic Recommendation → AI phrasing via the gateway (AIRequestLog + provenance;
  numeric + copy validators pass) → lecturer sees draft + reasons; Copy / Mark-acted / Dismiss present, NO Send
→ lecturer marks acted → lecturerState=acted, studentState unchanged, NOTHING sent
→ student sees the gentle nudge in the pinned surface → "Not now" → hidden, not re-shown next run
→ forced AI-unavailable → template fallback renders
```
**Real-provider smoke** (rule 11, model-ID echo). Routing per PromptRegistry (short supportive phrasing → V2 / Cerebras — ADR the choice).

---

### 11.3 — Assessment analysis + question insights  (lecturer; DETERMINISTIC, aggregate-only)

**Backend:** deterministic item analytics over `StudentAnswer` — per-question correct rate, most-missed questions, distractor breakdown, and **per-topic class mastery via the question topic metadata** (prerequisite above; "unavailable" if missing — never guessed). Compute-on-read in `platform/query`. **Small-cohort rule:** if a cohort's answer count < 3, show *"Not enough submissions for an aggregate insight"* instead of misleading percentages. Aggregate-only; no per-student exposure beyond entitlement.

**UI proof obligation:** for a quiz with a seeded, known answer distribution, the lecturer sees statistics that match the seed exactly.

**Browser gate:**
```
Seeded quiz with a known answer distribution → analysis matches the seed exactly
  (per-question rates, most-missed, distractor breakdown)
→ per-topic mastery present when metadata exists / marked "unavailable" when it doesn't
→ a <3-submission cohort shows the small-cohort message, not percentages
→ aggregate-only (no student identity beyond entitlement)
```
**No AI in 11.3.** (An AI narrative is out of scope for now — the stats stand alone; if added later it needs its own rule-11 smoke.)

---

### 11.4 — Workload planner  (student; DETERMINISTIC 6-phase; READ-ONLY)

**Backend:** `StudentAvailability` (days / preferred window / max-minutes-per-day — contract above, one-time); the deterministic **6-phase planning algorithm** → `WorkloadPlan` + `WorkloadPlanItem` (topic/section, date/window, **stored** effort estimate, the **reason** it exists — a deadline / a detected gap; versioned + reproducible). Inputs = deadlines (5.5) + gaps (11.1 snapshot) + forecast (9) + availability. **No AI in the planning math.**

> Confirm the exact 6 phases against **Slice 5** (you have it) before coding. If Slice 5 doesn't pin them, **STOP and escalate** (rule 10). Lock the contract regardless: deterministic, reproducible, every item traceable, estimates stored.

**Thin UI:** the read-only plan, **list-first** (calendar optional/secondary) — items with date, topic, stored estimate, and reason; plus the availability settings. **No mark-done, no in-app editing.**

**UI proof obligation:** the student sets availability, the agent generates a plan, and the student sees real items tied to real deadlines + their own gaps — read-only.

**Browser gate:**
```
Set availability → plan generated (deterministic) → items tied to real schedule deadlines + the student's real gaps,
  each with a stored estimate + a reason → plan is READ-ONLY (no edit/done controls present)
→ change availability + regenerate → the plan changes accordingly (availability-driven, not hardcoded;
  the old plan is superseded, the new one isActive)
```
**No AI in 11.4.**

---

### 11.5 — Calendar (.ics) export  (student)

**Backend:** generate a valid `.ics` (iCalendar) from the student's plan items + deadlines:
```
UID: stable per WorkloadPlanItem        DTSTAMP: export generation time
DTSTART/DTEND: plan-item window         SUMMARY: "Study: [topic]"
DESCRIPTION: reason + estimate          PRODID: "XYZ LMS"
TIMEZONE: institution tz (or UTC-normalized with explicit handling)
Deadlines: consistently all-day or timed
```
File download only — **no Google/external OAuth or two-way sync**. The export is a **snapshot**; it does not auto-update.

**UI proof obligation:** the student clicks export and gets a valid `.ics` containing their plan items/deadlines that imports cleanly into a calendar app.

**Browser gate:**
```
Open plan → export → .ics downloads → valid iCalendar; contains the expected study items + deadlines
  with correct dates/times → a timezone edge case (the institution tz) lands on the right local time
  (assert no off-by-one-hour shift)
```
**No AI.**

---

### 11.6 — Grade-forecast advice  (student; AI EXPLAINS Stage 9's deterministic forecast)

**Backend:** **reuse Stage 9's forecast engine** (no new grade math). A lazy/cached AI advice layer through the gateway; **passes the numeric-consistency + copy-safety validators**. When the deterministic math says the target is unreachable, the advice is **honest + constructive** (decision #7) — never sugarcoated, no diagnosis, no shaming. Template fallback if AI is down.

**Thin UI:** on the Stage 9 My-Progress / forecast surface, the student sees AI advice alongside the deterministic forecast. (Coordinate this surface with Stage 10 — see Parallel Development.)

**UI proof obligation:** a student with a known deterministic forecast (including an "impossible" case) sees AI advice that references those exact numbers correctly and handles the impossible case honestly + kindly.

**Browser gate:**
```
Seeded student with a known forecast (incl. an impossible-target case) → AI advice via the gateway
  (AIRequestLog + provenance; numeric + copy validators pass) → advice references the deterministic numbers
  correctly and invents none → impossible case stated honestly + constructively
→ forced AI-unavailable → template fallback renders
```
**Real-provider smoke** (rule 11, model-ID echo).

---

## Parallel development with Stage 10 (Gamification) — coordination

1. **Database migration numbers.** Stage 9 ends at `0039`; both stages start at `0040+` and **will** collide. Agree non-overlapping ranges up front (suggested: Stage 10 → `0040–0049`, Stage 11 → `0050+`). Whoever merges **second** rebases the chain, re-runs the Alembic round-trip (upgrade → base → upgrade), and confirms a single head — as at Stage 5.5g.
2. **The scheduler is shared.** Stage 11 builds `platform/scheduler` in 11.1. If Stage 10's streaks need scheduled jobs, Stage 10 consumes the **same** component — it does not build a second one. Land it early; if Stage 10 computes streaks on-read, there's no dependency. Decide at the start.
3. **`platform/query`.** Both add read models — keep additions additive (new functions/files); expect and resolve merge conflicts; don't refactor shared files mid-flight.
4. **Events.** Both only READ `StudentActivityEvent`. Neither adds new event types. No write conflict.
5. **My Progress page (Stage 9).** Stage 10 fills the "placeholder gamification section"; Stage 11.6 adds grade advice to the forecast area. Same page, different sections — coordinate the layout so the last merge doesn't clobber the other's section.
6. **Full E2E suite (rule 14).** On separate branches that's each branch's suite; at merge the **combined** suite must be green. The second stage to merge owns getting it green after rebase.
7. **Risk inputs isolated from gamification** (governing constraint) — Stage 11 doesn't block on Stage 10 and vice-versa.

---

## Design-plan reconciliation (do this BEFORE coding the UIs)

The older design plan / Slice 5 — which the agent has and I have **not** seen, so **verify** — reportedly still describes interactions that these locked decisions **override**. Reconcile explicitly so engineers don't build the old model:

- **Recommendation modal:** Copy draft / Mark acted / Dismiss only — **remove any "Send message" button.**
- **Workload plan:** read-only — **remove draggable study blocks, accept/reject actions, and "export only after acceptance"** (export is always available).

If anything in the design plan conflicts with this spec, **this spec wins**; record the conflict in a findings note (rule 10).

---

## Recommended gstack skills (where they pay off most)

- Before coding 11.1: **`/plan-eng-review`** on the scheduler + deterministic-risk design — timezone, idempotency, single-instance locking, and the reproducibility/`sourceCutoffAt` contract are classic bug sources; lock the data flow + failure paths + test matrix first.
- Before coding the student/lecturer UIs (11.1, 11.2, 11.4): **`/plan-design-review`** — real end-user surfaces; the student gentle view especially needs careful, non-alarming design.
- On the risk-classification and 6-phase planning logic: **`/codex`** in adversarial mode — correctness-critical; the deterministic output must never be overridden by AI.
- After each sub-session, before `/ship`: **`/review`** then **`/qa`** on the live surface.
- Once per stage (after 11.2 and again before stage close): **`/cso`** focused on the authorization boundary (lecturer → own students only; student → self only), the `manual_admin` trigger endpoint, and `.ics` generation.
- At stage close: **`/document-release`**.

---

## Done means (stage)

- Canonical enums/contracts locked; `platform/scheduler` runs deterministically (idempotent, single-instance, recoverable, every run recorded on `AgentRun`); the scheduler is single-instance in the hosted env.
- Risk, grades/forecast, and the plan are fully deterministic and reproducible; every output carries `algorithmVersion` + `inputHash` + `sourceCutoffAt` with bounded retention; **every risk label traces to reasons + metrics whose keys it cites**; no AI calculates any of them; no black-box score anywhere.
- Lecturer per-course roster (full + "Needs support" indicator) and student gentle view both correct from the same data; risk display is live-on-read; authz enforced (own-students / self / admin-all) with 403 tests.
- Recommendations: deterministic trigger + lazy/cached AI phrasing (gateway + provenance), passing the numeric + copy validators; separate lecturer/student states; lecturer draft (manual, nothing auto-sent, no Send button) + student passive nudge (pinned surface, dismissible).
- Assessment analysis deterministic + aggregate-only, exact against seeds, with topic-mastery fallback and the small-cohort rule.
- Workload plan deterministic, read-only, list-first, availability-driven, versioned, with stored estimates + reasons; `.ics` export valid with correct timezones.
- Grade advice: AI explains Stage 9's forecast, honest + kind on impossible targets, wellbeing-safe.
- The manual trigger is hardened + AI-free; the design plan is reconciled.
- Every sub-session browser gate green; the full active Playwright suite green at each close (rule 14); real-provider smokes recorded for 11.2 and 11.6 (rule 11); knowledge trio + this roadmap's status table updated in the closing commit (rule 12).

---

## Exclusions

- No live LMS integration / no live LMS metrics.
- No Google OAuth or external-calendar two-way sync (only `.ics` file export).
- No autonomous or auto-sent messages (email / SMS / push). Recommendations are in-app / drafts only — **no Send button.**
- No black-box scoring — risk is deterministic + explainable.
- No auto-rescheduling — the plan is read-only; the agent never moves things on its own. **No draggable blocks, no accept/reject.**
- No interactive plan — no mark-done, no in-app editing (availability is the only student input).
- No peer rankings or named comparisons shown to students (carry from Stage 9) — the gentle view shows no peer data.
- No mental-health diagnosis.
- No new `StudentActivityEvent` types.
- No dependency on Stage 10 gamification data in risk/recommendation/plan inputs.
- AI never calculates risk or grades — explanation/phrasing only.
