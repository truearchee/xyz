# Stage 5d — Findings

Findings raised during Stage 5d (student quiz UI + browser gate + real-provider smoke). Resolution
vocabulary: each finding is RESOLVED (with the fix) or DEFERRED (with written rationale + owner) before
Stage 5 is stamped FULLY VERIFIED.

---

## F-5d-1 — Quiz generation truncates structured output under a dense summary (`finish_reason='length'`)

**Status: RESOLVED + RE-CONFIRMED.** Fix landed (max_tokens 8000→16000), drift-clean, and the
real-provider smoke re-run at 16000 returned **`finish_reason='stop'`** (completion=11350 < 16000, a
parseable 10-question quiz, rule-11 echo OK) — the truncation is empirically gone, not just logically
addressed.

**Trigger.** The 5d real-provider smoke (`gate3_quiz_smoke.py`, reasoning route) returned
`finish_reason='length'` with `completion=8000` (the full `max_tokens` budget) on a SHORT, lightweight
synthetic summary. It still produced a valid 10-question quiz, but only because the JSON happened to
complete within budget.

**Risk (user-visible, happy-path — not an edge case).** A reasoning model thinks inline in `content`
before emitting the JSON. On a denser detailed summary (longer lecture, more concepts), the inline
reasoning consumes more of the budget and the structured output gets truncated mid-JSON →
`OutputValidator` raises `invalid_output` → RQ retries the bounded set → exhaustion → the student lands
on a `failed` attempt. That is a visible failure on the generation path, not a corner case.

**Options considered.**
1. Increase `max_tokens` in the PromptRegistry for `post_class_quiz_generation` so the budget covers the
   reasoning AND the full 10-question answer. (Chosen.)
2. Reduce the summary payload sent to the prompt (cap the rendered summary text at N tokens before the
   call). (Viable; deferred — keeps the full summary as context for question quality. Revisit if (1)
   proves insufficient under load.)

**Resolution.** `backend/prompts/post_class_quiz_generation/v1.yaml` `max_tokens: 8000 → 16000`
(2× headroom; same flat-file knob as the summary prompts). `prompts/CHECKSUMS.json` updated to the new
content hash; the prompt-drift guard passes (`test_llm_unit.py -k drift` → 4 passed). The change is
**monotonic** — raising the token budget can only reduce truncation; it cannot make a call that already
passed green (the prior smoke at 8000 produced a valid 10-Q quiz with the rule-11 echo OK) regress.

**Re-confirm — DONE.** Re-ran `python scripts/gate3_quiz_smoke.py` at 16000 with the valid key (recovered
from the operator-supplied `/Desktop/LMS/test2/.env`): **`finish_reason='stop'`**, completion=11350,
model echo `MBZUAI-IFM/K2-Think-v2` (rule 11), parseable 10-question quiz, one-correct-per-q. Recorded in
[[steps/stage-05/5d-real-provider-smoke]]. The earlier 8000 truncation no longer reproduces.

**Owner.** Resolved this session (config fix). The real-provider re-confirm passed with the
operator-supplied valid key. Stage 5 was stamped FULLY VERIFIED only after the live browser gate (Gate 1)
also ran green.

**Raised / resolved:** 2026-06-16 (#5d).
