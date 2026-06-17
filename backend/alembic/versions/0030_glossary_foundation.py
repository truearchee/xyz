"""Stage 7a glossary foundation: folders, entries, source references, definition cache.

Revision ID: 0030
Revises: 0022
Create Date: 2026-06-17

Stage 7 owns the reserved block 0030-0039 (0029 is left to Stage 6). This migration is additive:
- New per-student tables: glossary_folders, glossary_entries, glossary_source_references; the
  shared-across-students glossary_definition_cache (UNIQUE(cache_key, prompt_version) = the
  one-active-keyed-on-cache-key concurrency guard).
- app_users gains preferred_language (default 'en'), mirroring the existing timezone column.
- TWO shared CHECK constraints are widened (drop + recreate with the FULL string):
    ck_ai_request_logs_feature           +'glossary_definition'
    ck_student_activity_events_event_type +'glossary_term_saved','glossary_practice_completed'

  ⚠ PARALLEL-STAGE HAZARD (Stage 6): a CHECK is rewritten wholesale, so whichever of Stage 6 / Stage 7
  merges SECOND must recreate these two CHECKs with the UNION of BOTH stages' values, or the earlier
  stage's additions are silently dropped. The model source-of-truth tuples
  (AI_REQUEST_LOG_FEATURES, STUDENT_ACTIVITY_EVENT_TYPES) plus the CI union test
  (tests/test_shared_check_union.py) are the guard. See knowledge/steps/findings-stage-07.md.

Guards are existence-checked so a partially-applied run is re-runnable (matches 0008-0019).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030"
# Rebased onto Stage 6 (head 0025) at integration: was 0022 (the pre-Stage-6 head this branch forked
# from). Re-pointed to 0025 to keep a single linear chain 0025 → 0030 → 0031.
down_revision = "0025"
branch_labels = None
depends_on = None


AI_FEATURE_CONSTRAINT = "ck_ai_request_logs_feature"
EVENT_TYPE_CONSTRAINT = "ck_student_activity_events_event_type"

# Head-at-this-revision values. Rebased onto Stage 6 (head 0025), so the PRIOR state already includes
# Stage 6a's 'quiz_pool'; Stage 7 adds 'glossary_definition' on top. The NEW constraint is the UNION of
# both stages' values — a CHECK is rewritten wholesale, so dropping quiz_pool here would silently remove
# it from the live DB (the test_shared_check_union CI test guards exactly this).
_AI_FEATURE_PRIOR = (
    "feature IN ('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool')"
)
_AI_FEATURE_NEW = (
    "feature IN ('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', "
    "'glossary_definition')"
)
_EVENT_TYPE_PRIOR = "event_type IN ('completed_quiz', 'perfect_quiz_score')"
_EVENT_TYPE_NEW = (
    "event_type IN ('completed_quiz', 'perfect_quiz_score', "
    "'glossary_term_saved', 'glossary_practice_completed')"
)


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :name
                """
            ),
            {"name": name},
        ).scalar()
    )


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"
            ),
            {"name": name},
        ).scalar()
    )


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()
    )


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def upgrade() -> None:
    # --- app_users.preferred_language (mirrors timezone) ---
    if not _column_exists("app_users", "preferred_language"):
        op.add_column(
            "app_users",
            sa.Column(
                "preferred_language",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'en'"),
            ),
        )
    if not _constraint_exists("ck_app_users_preferred_language"):
        op.create_check_constraint(
            "ck_app_users_preferred_language",
            "app_users",
            "preferred_language IN ('en', 'ar', 'zh', 'es', 'fr')",
        )

    # --- glossary_folders ---
    if not _table_exists("glossary_folders"):
        op.create_table(
            "glossary_folders",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column(
                "is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_glossary_folders"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_glossary_folders_student_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'archived')", name="ck_glossary_folders_status"
            ),
        )
    if not _index_exists("uq_glossary_folders_student_name_active"):
        op.create_index(
            "uq_glossary_folders_student_name_active",
            "glossary_folders",
            ["student_id", "name"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        )
    if not _index_exists("uq_glossary_folders_one_system"):
        op.create_index(
            "uq_glossary_folders_one_system",
            "glossary_folders",
            ["student_id"],
            unique=True,
            postgresql_where=sa.text("is_system AND status = 'active'"),
        )

    # --- glossary_entries ---
    if not _table_exists("glossary_entries"):
        op.create_table(
            "glossary_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("term", sa.Text(), nullable=False),
            sa.Column("normalized_term", sa.Text(), nullable=False),
            sa.Column("normalize_version", sa.Text(), nullable=False),
            sa.Column(
                "entry_type", sa.Text(), nullable=False, server_default=sa.text("'term'")
            ),
            sa.Column("language", sa.Text(), nullable=False),
            sa.Column("cache_key", sa.Text(), nullable=False),
            sa.Column("short_definition", sa.Text(), nullable=True),
            sa.Column("detailed_explanation", sa.Text(), nullable=True),
            sa.Column("example", sa.Text(), nullable=True),
            sa.Column("formula_latex", sa.Text(), nullable=True),
            sa.Column(
                "definition_status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column(
                "status", sa.Text(), nullable=False, server_default=sa.text("'active'")
            ),
            sa.Column("model_id", sa.Text(), nullable=True),
            sa.Column("prompt_version", sa.Text(), nullable=True),
            sa.Column("prompt_content_hash", sa.Text(), nullable=True),
            sa.Column("backend_used", sa.Text(), nullable=True),
            sa.Column("source_content_hash", sa.Text(), nullable=True),
            sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "definition_generated_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_glossary_entries"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_glossary_entries_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["subject_id"],
                ["course_modules.id"],
                name="fk_glossary_entries_subject_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["folder_id"],
                ["glossary_folders.id"],
                name="fk_glossary_entries_folder_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["module_section_id"],
                ["module_sections.id"],
                name="fk_glossary_entries_module_section_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["ai_request_log_id"],
                ["ai_request_logs.id"],
                name="fk_glossary_entries_ai_request_log_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "entry_type IN ('term', 'concept', 'formula')",
                name="ck_glossary_entries_entry_type",
            ),
            sa.CheckConstraint(
                "language IN ('en', 'ar', 'zh', 'es', 'fr')",
                name="ck_glossary_entries_language",
            ),
            sa.CheckConstraint(
                "definition_status IN ('pending', 'generated', 'failed', 'manual')",
                name="ck_glossary_entries_definition_status",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'archived')", name="ck_glossary_entries_status"
            ),
        )
    if not _index_exists("uq_glossary_entries_dedup_active"):
        op.create_index(
            "uq_glossary_entries_dedup_active",
            "glossary_entries",
            ["student_id", "subject_id", "normalized_term"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        )
    if not _index_exists("ix_glossary_entries_student_subject_status"):
        op.create_index(
            "ix_glossary_entries_student_subject_status",
            "glossary_entries",
            ["student_id", "subject_id", "status"],
        )
    if not _index_exists("ix_glossary_entries_student_folder"):
        op.create_index(
            "ix_glossary_entries_student_folder",
            "glossary_entries",
            ["student_id", "folder_id"],
        )
    if not _index_exists("ix_glossary_entries_cache_key"):
        op.create_index(
            "ix_glossary_entries_cache_key", "glossary_entries", ["cache_key"]
        )

    # --- glossary_source_references ---
    if not _table_exists("glossary_source_references"):
        op.create_table(
            "glossary_source_references",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("glossary_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_type", sa.Text(), nullable=False),
            sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_summary_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "source_quiz_attempt_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
            sa.Column("selected_text", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_glossary_source_references"),
            sa.ForeignKeyConstraint(
                ["glossary_entry_id"],
                ["glossary_entries.id"],
                name="fk_glossary_source_references_entry_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["module_section_id"],
                ["module_sections.id"],
                name="fk_glossary_source_references_module_section_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["source_summary_id"],
                ["generated_lecture_summaries.id"],
                name="fk_glossary_source_references_summary_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["source_quiz_attempt_id"],
                ["quiz_attempts.id"],
                name="fk_glossary_source_references_quiz_attempt_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "source_type IN ('summary', 'manual', 'quiz')",
                name="ck_glossary_source_references_source_type",
            ),
        )
    if not _index_exists("ix_glossary_source_references_entry"):
        op.create_index(
            "ix_glossary_source_references_entry",
            "glossary_source_references",
            ["glossary_entry_id"],
        )

    # --- glossary_definition_cache ---
    if not _table_exists("glossary_definition_cache"):
        op.create_table(
            "glossary_definition_cache",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("cache_key", sa.Text(), nullable=False),
            sa.Column("prompt_version", sa.Text(), nullable=False),
            sa.Column("normalized_term", sa.Text(), nullable=False),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("entry_type", sa.Text(), nullable=False),
            sa.Column("language", sa.Text(), nullable=False),
            sa.Column("term", sa.Text(), nullable=False),
            sa.Column("context_text", sa.Text(), nullable=True),
            sa.Column(
                "status", sa.Text(), nullable=False, server_default=sa.text("'pending'")
            ),
            sa.Column("short_definition", sa.Text(), nullable=True),
            sa.Column("model_id", sa.Text(), nullable=True),
            sa.Column("prompt_content_hash", sa.Text(), nullable=True),
            sa.Column("backend_used", sa.Text(), nullable=True),
            sa.Column("source_content_hash", sa.Text(), nullable=True),
            sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_glossary_definition_cache"),
            sa.ForeignKeyConstraint(
                ["ai_request_log_id"],
                ["ai_request_logs.id"],
                name="fk_glossary_definition_cache_ai_request_log_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'generated', 'failed')",
                name="ck_glossary_definition_cache_status",
            ),
            sa.CheckConstraint(
                "entry_type IN ('term', 'concept', 'formula')",
                name="ck_glossary_definition_cache_entry_type",
            ),
            sa.CheckConstraint(
                "language IN ('en', 'ar', 'zh', 'es', 'fr')",
                name="ck_glossary_definition_cache_language",
            ),
        )
    if not _index_exists("uq_glossary_definition_cache_key"):
        op.create_index(
            "uq_glossary_definition_cache_key",
            "glossary_definition_cache",
            ["cache_key", "prompt_version"],
            unique=True,
        )

    # --- shared CHECK widenings (union-aware; see docstring hazard note) ---
    if _constraint_exists(AI_FEATURE_CONSTRAINT):
        op.drop_constraint(AI_FEATURE_CONSTRAINT, "ai_request_logs", type_="check")
    op.create_check_constraint(AI_FEATURE_CONSTRAINT, "ai_request_logs", _AI_FEATURE_NEW)

    if _constraint_exists(EVENT_TYPE_CONSTRAINT):
        op.drop_constraint(EVENT_TYPE_CONSTRAINT, "student_activity_events", type_="check")
    op.create_check_constraint(
        EVENT_TYPE_CONSTRAINT, "student_activity_events", _EVENT_TYPE_NEW
    )


def downgrade() -> None:
    # Restore the shared CHECKs to their pre-0030 values.
    if _constraint_exists(EVENT_TYPE_CONSTRAINT):
        op.drop_constraint(EVENT_TYPE_CONSTRAINT, "student_activity_events", type_="check")
    op.create_check_constraint(
        EVENT_TYPE_CONSTRAINT, "student_activity_events", _EVENT_TYPE_PRIOR
    )
    if _constraint_exists(AI_FEATURE_CONSTRAINT):
        op.drop_constraint(AI_FEATURE_CONSTRAINT, "ai_request_logs", type_="check")
    op.create_check_constraint(AI_FEATURE_CONSTRAINT, "ai_request_logs", _AI_FEATURE_PRIOR)

    if _table_exists("glossary_definition_cache"):
        op.drop_table("glossary_definition_cache")
    if _table_exists("glossary_source_references"):
        op.drop_table("glossary_source_references")
    if _table_exists("glossary_entries"):
        op.drop_table("glossary_entries")
    if _table_exists("glossary_folders"):
        op.drop_table("glossary_folders")

    if _constraint_exists("ck_app_users_preferred_language"):
        op.drop_constraint("ck_app_users_preferred_language", "app_users", type_="check")
    if _column_exists("app_users", "preferred_language"):
        op.drop_column("app_users", "preferred_language")
