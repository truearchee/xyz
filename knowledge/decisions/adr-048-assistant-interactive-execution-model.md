---
type: adr
stage: "8"
status: accepted
created: 2026-06-18
updated: 2026-06-18
related-session: knowledge/specs/stage-08/8.1-conversation-foundation.md
---

# ADR-048 — Assistant interactive turn: create-then-poll via the `ai` queue

## Linked documents
- Spec: [[specs/stage-08/8.1-conversation-foundation]]
- Plan: [[plans/stage-08/8.1-conversation-foundation]]
- Report: [[steps/stage-08/8.1-conversation-foundation]]

## Context
Stage 8.1 is the first INTERACTIVE consumer of the LLM gateway (every prior consumer — summaries, quiz,
pools — is a background RQ job). `LLMGateway.complete()` is awaitable directly in a request, but a chat
answer can take many seconds (and longer under limiter backoff), and a long-held synchronous HTTP request
is exactly the fragility Stage 8.3/4.8 exist to remove. Decision 7 also mandates the 4.5d async pattern
(passive "thinking…", no hard timeout) which is a polling pattern.

## Decision
Use **create-then-poll**, mirroring the quiz `start → enqueue-after-commit → claim → gateway → atomic
persist` pipeline:
1. `POST …/messages` saves the user message + a `pending` assistant message, COMMITS, then enqueues
   `generate_assistant_answer(messageId)` on the **`ai` queue** with `at_front=True`.
2. The worker runs `LLMGateway.complete(priority="interactive", feature="assistant")` over the bounded
   recent history, persists the answer + provenance + `ai_request_log_id`, flips status `pending →
   completed | failed`.
3. The frontend polls `GET …/messages` with the 4.5d backoff (no hard timeout) until terminal.

`priority="interactive"` consumes the reserved limiter headroom (rule 15, first time). `at_front=True`
keeps a chat turn ahead of queued background jobs.

## Consequences
- Reuses tested infrastructure; lifecycle/retry/navigate-away are well-defined (decision 11); the 8.3 SSE
  swap is a transport-only change (poll → stream).
- A single `ai_worker` can still delay a chat turn behind an in-flight long background job (`at_front`
  reorders the queue, not a running job). Mitigation: limiter interactive headroom; a dedicated
  `ai_interactive` queue/worker is a future option (open question).
- Conversation history is packed into `ContextRefs.transcript_text` because the registry only templates
  `{{transcript}}`/`{{section_type}}` — an accepted contract stretch; richer templating deferred.
