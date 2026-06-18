"""Assistant retrieval + grounding configuration (Stage 8.2, review #8).

Single place for the tunable knobs so the threshold and budgets are configurable + versioned and the
calibration note can reference exact values. ``RETRIEVAL_CONFIG_VERSION`` is stamped into the
generation-time context snapshot, so a later threshold change is auditable per answer.
"""

from __future__ import annotations

# Cosine DISTANCE (pgvector `<=>`; 0 == identical direction, 1 == orthogonal, 2 == opposite). A chunk is
# "relevant" iff its distance to the query is <= this. Start value 0.35 — calibrated against observed
# in-lecture vs off-lecture MiniLM distances in 8.2-retrieval-threshold-calibration.md. CI/E2E does not
# depend on this exact number: the deterministic encoder yields distance 0 (identical text) or ≈1
# (different text), both far from the boundary.
RELEVANCE_MAX_DISTANCE = 0.35

# Bumped whenever the retrieval recipe changes (threshold, top-k, caps, scan shape). Audit-only.
RETRIEVAL_CONFIG_VERSION = "retrieval-v1"

# How many nearest chunks the exact scan returns (ordered by distance asc). A single lecture is small;
# 6 keeps the prompt focused and bounded.
RETRIEVAL_TOP_K = 6

# Per-source and total character caps on the grounded context packed into the prompt (review #7). One
# large/oversized summary or chunk cannot blow the budget; the total cap bounds the whole combined
# summary+retrieval block. Applied BEFORE the gateway's ContextBuilder cap (which is the final safety net).
RETRIEVAL_SUMMARY_CHAR_CAP = 2500
RETRIEVAL_CHUNK_CHAR_CAP = 1500
RETRIEVAL_CONTEXT_CHAR_CAP = 6000
