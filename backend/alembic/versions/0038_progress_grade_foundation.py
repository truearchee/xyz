"""Stage 9 grade foundation and target-grade goals.

Revision ID: 0038
Revises: 0033
Create Date: 2026-06-18

Stage 9 owns migration block 0038-0043 and now follows the integrated Stage 8.2
assistant head 0033.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0038"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_grade_schemes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("on_track_max", sa.Numeric(5, 2), nullable=False, server_default=sa.text("70.00")),
        sa.Column("at_risk_max", sa.Numeric(5, 2), nullable=False, server_default=sa.text("85.00")),
        sa.Column("benchmark_min_cohort", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_course_grade_schemes"),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_course_grade_schemes_module_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("module_id", name="uq_course_grade_schemes_module"),
        sa.CheckConstraint(
            "on_track_max >= 0 AND on_track_max <= 100",
            name="ck_course_grade_schemes_on_track_max",
        ),
        sa.CheckConstraint(
            "at_risk_max >= on_track_max AND at_risk_max <= 100",
            name="ck_course_grade_schemes_at_risk_max",
        ),
        sa.CheckConstraint("benchmark_min_cohort >= 2", name="ck_course_grade_schemes_benchmark_min"),
    )

    op.create_table(
        "grade_boundaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("letter_grade", sa.Text(), nullable=False),
        sa.Column("lower_bound", sa.Numeric(5, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_grade_boundaries"),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["course_grade_schemes.id"],
            name="fk_grade_boundaries_scheme_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("scheme_id", "letter_grade", name="uq_grade_boundaries_scheme_letter"),
        sa.UniqueConstraint("scheme_id", "sort_order", name="uq_grade_boundaries_scheme_order"),
        sa.CheckConstraint("lower_bound >= 0 AND lower_bound <= 100", name="ck_grade_boundaries_lower"),
    )
    op.create_index("ix_grade_boundaries_scheme_lower", "grade_boundaries", ["scheme_id", "lower_bound"])

    op.create_table(
        "grade_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("weight", sa.Numeric(8, 4), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("component_kind", sa.Text(), nullable=False, server_default=sa.text("'coursework'")),
        sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_grade_components"),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["course_grade_schemes.id"],
            name="fk_grade_components_scheme_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_section_id"],
            ["module_sections.id"],
            name="fk_grade_components_module_section_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("scheme_id", "sort_order", name="uq_grade_components_scheme_order"),
        sa.CheckConstraint("weight > 0 AND weight <= 1", name="ck_grade_components_weight"),
        sa.CheckConstraint(
            "component_kind IN ('quiz', 'assignment', 'exam', 'lab', 'coursework')",
            name="ck_grade_components_kind",
        ),
    )
    op.create_index("ix_grade_components_scheme", "grade_components", ["scheme_id"])

    op.create_table(
        "student_grade_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grade_component_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("percentage_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'seed'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_grade_records"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_grade_records_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grade_component_id"],
            ["grade_components.id"],
            name="fk_student_grade_records_grade_component_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "student_id",
            "grade_component_id",
            name="uq_student_grade_records_student_component",
        ),
        sa.CheckConstraint(
            "percentage_score >= 0 AND percentage_score <= 100",
            name="ck_student_grade_records_percentage",
        ),
        sa.CheckConstraint(
            "source IN ('seed', 'e2e', 'import')",
            name="ck_student_grade_records_source",
        ),
    )
    op.create_index(
        "ix_student_grade_records_student_component",
        "student_grade_records",
        ["student_id", "grade_component_id"],
    )

    op.create_table(
        "student_target_grade_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_letter_grade", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_target_grade_goals"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_target_grade_goals_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_student_target_grade_goals_module_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_student_target_grade_goals_status",
        ),
    )
    op.create_index(
        "uq_student_target_grade_goals_one_active",
        "student_target_grade_goals",
        ["student_id", "module_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_student_target_grade_goals_student",
        "student_target_grade_goals",
        ["student_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_target_grade_goals_student", table_name="student_target_grade_goals")
    op.drop_index("uq_student_target_grade_goals_one_active", table_name="student_target_grade_goals")
    op.drop_table("student_target_grade_goals")
    op.drop_index("ix_student_grade_records_student_component", table_name="student_grade_records")
    op.drop_table("student_grade_records")
    op.drop_index("ix_grade_components_scheme", table_name="grade_components")
    op.drop_table("grade_components")
    op.drop_index("ix_grade_boundaries_scheme_lower", table_name="grade_boundaries")
    op.drop_table("grade_boundaries")
    op.drop_table("course_grade_schemes")
