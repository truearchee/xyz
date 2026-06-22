# ADR-057 — Stage 11 Recommendation Copy Model Route

Date: 2026-06-20

## Status
Accepted

## Context
Stage 11.2 adds AI phrasing for deterministic recommendations. The model is allowed to phrase only the
deterministic payload; it may not calculate risk, grades, eligibility, peer comparisons, diagnoses, or new facts.

Recommendation copy is short supportive text for two audiences:
- a lecturer draft that the lecturer manually copies into their own channel;
- a gentle in-app student nudge.

## Decision
- Use prompt `recommendation_copy/v1`.
- Route through the existing `platform/llm` gateway with BACKGROUND priority.
- Use the V2/Cerebras route declared in the prompt: `model: MBZUAI-IFM/K2-Think-v2`, `backend: cerebras`.
- Generate both lecturer and student copy in one call per recommendation.
- Cache AI text with `aiProvenance { modelId, promptVersion, inputHash, generatedAt }`.
- Regenerate only when `inputHash` or prompt version changes.
- Reject the whole AI result when either audience fails validation, then fall back to deterministic templates.

## Consequences
- The deterministic/template path remains the user-visible fallback and never waits for AI.
- The model route is auditable by rule-11 model-ID echo smoke before the session can be marked FULLY VERIFIED.
- Provider output is never trusted directly: `RecommendationCopy` schema validation plus numeric consistency and
  student-copy safety validators gate persistence.

## Linked documents
- Spec: [[specs/stage-11/11.2-student-detail-recommendations]]
- Plan: [[plans/stage-11/11.2-student-detail-recommendations]]
- Report: [[steps/stage-11/11.2-student-detail-recommendations]]
- Master spec: [[specs/stage-11/11-proactive-ai-agent-analytics]]
