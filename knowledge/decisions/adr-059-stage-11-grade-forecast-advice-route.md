# ADR-059 — Stage 11 Grade-Forecast Advice Model Route

Date: 2026-06-21

## Status
Accepted

## Context
Stage 11.6 adds a student-facing AI note that EXPLAINS the Stage 9 deterministic grade forecast
(target grade, current standing, required remaining average, forecast status incl. the "impossible"
case). The AI must phrase only — it never calculates the forecast, the target, the required average, or
the state. The copy is short, supportive, and wellbeing-sensitive (the impossible case especially), and
it must be reproducible, cached, and resilient when the provider is unavailable.

## Decision
- Use prompt `grade_forecast_advice/v1`.
- Route through the existing `platform/llm` gateway with **BACKGROUND** priority.
- Use the V2/Cerebras route declared in the prompt — `model: MBZUAI-IFM/K2-Think-v2`,
  `backend: cerebras` — the same short-supportive-phrasing route as Stage 11.2 (ADR-057).
- The prompt is **anchored on rewriting the deterministic `templateAdvice`** baseline (not on
  open-ended construction from rules). K2-Think reasons inline in `content` with no request-level
  reasoning control (provider note F-4.5-04: `reasoning_level` is never faked), so anchoring on a
  rewrite keeps the reasoning trace short and the JSON within `max_tokens=4000` and the route timeout.
- The advice is generated **lazily on read** (one cached call per `(student, module)` advice row), not
  by a scheduled `AgentRun`. It regenerates only when the forecast `inputHash` or the prompt version
  changes; a terminal failure for the current forecast is not re-attempted until the forecast changes.
- Cache AI text with `aiProvenance { modelId, promptVersion, inputHash, generatedAt }` plus the
  reproducibility fields `algorithmVersion` / `inputHash` / `sourceCutoffAt` on the advice row.
- Reject the whole AI result when **any** validator fails — numeric/fact consistency, the state-aware
  contradiction guard, or the (reused) student-copy safety guard — then retry once, then fall back to
  the deterministic template.

## Consequences
- The deterministic/template advice is the user-visible fallback and never waits for AI; the page
  renders it immediately and the AI rephrase swaps in when ready (async poll).
- The model route is auditable by the rule-11 model-ID echo smoke (`gate11_advice_smoke.py`) before the
  session can be marked FULLY VERIFIED.
- Provider output is never trusted directly: `GradeForecastAdvice` schema validation plus the
  numeric-consistency + contradiction + student-copy-safety validators gate persistence. The impossible
  case is held to honest-but-constructive framing (must name the best reachable grade + an unreachable
  phrase; never a "still reachable" claim about the target; never shaming/defeatist language).
- E2E runs the deterministic provider (hermetic) which echoes the deterministic template through the
  full gateway path; the real K2-Think-v2 route + echo is proven separately by the rule-11 smoke.

## Linked documents
- Spec: [[specs/stage-11/11.6-grade-forecast-advice]]
- Plan: [[plans/stage-11/11.6-grade-forecast-advice]]
- Report: [[steps/stage-11/11.6-grade-forecast-advice]]
- Real-provider smoke: [[steps/stage-11/11.6-real-provider-smoke]]
- Recommendation-copy route (sibling): [[decisions/adr-057-stage-11-recommendation-copy-route]]
- Master spec: [[specs/stage-11/11-proactive-ai-agent-analytics]]
