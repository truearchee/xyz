"""Resolve the URL Alembic migrates over (Stage 4.8b). Importable + side-effect-free so it can be
unit-tested (``alembic/env.py`` itself runs migrations on import and cannot be imported in a test)."""

from __future__ import annotations

import os


def resolve_migration_url(ini_fallback: str | None = None) -> str:
    """Migrations run over the DIRECT/session endpoint (adr-041): DDL + advisory locks need a real
    session, never the transaction pooler. Falls back to DATABASE_URL locally (single URL), then the
    alembic.ini value."""
    return (
        os.environ.get("DIRECT_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ini_fallback
        or ""
    )
