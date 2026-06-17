"""Stage 6 quiz configuration — named defaults, not magic numbers (roadmap discipline).

Quiz length, pool sizing, and the cross-section sampling spread are CONFIGURATION (same principle as grade
boundaries in DB and estimates stored on records), seeded with the Slice 3 values. Global defaults live
here; a module-level override seam is a post-MVP trigger, not Stage 6. The validator's acceptable pool
COUNT band (min/max) is the validation authority and lives in ``platform/llm/validation.py`` — these are
the GENERATION / SAMPLING targets the quiz domain drives.
"""

from __future__ import annotations

# ── Per-attempt question counts (Slice 3) ────────────────────────────────────────────────────────
POST_CLASS_QUIZ_LENGTH = 10          # post_class: per section (a post_class quiz is one section)
RECAP_EXAM_QUESTIONS_PER_SECTION = 5  # recap & exam_prep: per in-scope eligible section (6 sections → 30)

# ── Pool sizing ──────────────────────────────────────────────────────────────────────────────────
# The pool is generated ONCE per section and shared across every mode, so it is sized against the LARGEST
# per-section draw (post_class = 10) with headroom for fresh retake combinations (~2.4×). Mirrors the
# count requested by prompts/quiz_pool_generation/v1.yaml and the deterministic provider fixture size; the
# validator accepts a band around it so a reasoning model over/undershooting the target still succeeds.
POOL_TARGET_SIZE = 24

# ── Cross-section sampling spread (multi-section recap / exam_prep) ───────────────────────────────
# Roughly even coverage per in-scope section — never all from one lecture. The only supported value at MVP.
CROSS_SECTION_SPREAD = "even"
