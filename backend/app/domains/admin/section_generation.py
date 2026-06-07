from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import CourseModule, ModuleSection


MVP_DEFAULT_POLICY = "mvp_default"


@dataclass(frozen=True)
class SectionDefinition:
    title: str
    type: str
    order_index: int


DEFAULT_MODULE_SECTIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(title="Lecture 1", type="lecture", order_index=1),
    SectionDefinition(title="Lecture 2", type="lecture", order_index=2),
    SectionDefinition(title="Lab 1", type="lab", order_index=3),
    SectionDefinition(title="Assignment 1", type="assignment", order_index=4),
)


def generate_initial_sections(
    db: AsyncSession,
    *,
    module: CourseModule,
    policy: str = MVP_DEFAULT_POLICY,
) -> list[ModuleSection]:
    if policy != MVP_DEFAULT_POLICY:
        raise ValueError(f"Unsupported section generation policy: {policy}")

    sections = [
        ModuleSection(
            course_module_id=module.id,
            title=definition.title,
            type=definition.type,
            order_index=definition.order_index,
            publish_status="draft",
            lecturer_notes=None,
            status="active",
        )
        for definition in DEFAULT_MODULE_SECTIONS
    ]
    db.add_all(sections)
    return sections
