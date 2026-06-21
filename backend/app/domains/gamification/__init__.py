"""Gamification domain (Stage 10) — the unified Learning streak + badges.

Consumes the platform event spine read-only (rule 7: gamification never writes ``StudentActivityEvent``)
and the Stage 5.5 schedule + Stage 9 snapshots via ``platform/query`` (rule 8: no cross-domain imports).
Streaks and badges are derived/evaluated ON READ, idempotent and sticky, and never awarded by the
frontend. Zero AI calls.
"""
