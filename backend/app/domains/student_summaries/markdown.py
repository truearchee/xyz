"""Server-side summary → markdown shaping (Stage 4.7 §3.3 / §8.3).

The student endpoint serves summary ``content`` as a single markdown STRING. The detailed summary is
stored structured (overview / key concepts / definitions / …) but §3.3 excludes structured client
rendering — so we flatten it to markdown here, server-side, and the client only sanitize-renders it
(react-markdown, raw HTML disabled — S1). Centralizing the shape keeps the frontend dumb and keeps the
one place generated text becomes markup behind a single hardened path.

Only ever consumes the summary ``content_json`` (the AI artifact). It never touches transcript text,
provenance, or job internals — those are not in scope and must never reach a student (§8.3).
"""

from __future__ import annotations


def _clean(value: object) -> str:
    return str(value or "").strip()


def _bullets(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [f"- {_clean(item)}" for item in items if _clean(item)]


def brief_to_markdown(content_json: dict | None) -> str:
    """Brief summary is ``{"text": "..."}`` — the text already reads as prose/markdown."""
    return _clean((content_json or {}).get("text"))


def detailed_to_markdown(content_json: dict | None) -> str:
    """Flatten the structured detailed summary (camelCase ``content_json``) into markdown headings."""
    cj = content_json or {}
    blocks: list[str] = []

    overview = _clean(cj.get("overview"))
    if overview:
        blocks.append(f"## Overview\n\n{overview}")

    key_concepts = _bullets(cj.get("keyConcepts"))
    if key_concepts:
        blocks.append("## Key concepts\n\n" + "\n".join(key_concepts))

    definitions = cj.get("importantDefinitions")
    if isinstance(definitions, list):
        def_lines = [
            f"- **{_clean(d.get('term'))}** — {_clean(d.get('definition'))}"
            for d in definitions
            if isinstance(d, dict) and (_clean(d.get("term")) or _clean(d.get("definition")))
        ]
        if def_lines:
            blocks.append("## Important definitions\n\n" + "\n".join(def_lines))

    main_explanations = _bullets(cj.get("mainExplanations"))
    if main_explanations:
        blocks.append("## Main explanations\n\n" + "\n".join(main_explanations))

    examples = _bullets(cj.get("examples"))
    if examples:
        blocks.append("## Examples\n\n" + "\n".join(examples))

    exam_points = _bullets(cj.get("examRelevantPoints"))
    if exam_points:
        blocks.append("## Exam-relevant points\n\n" + "\n".join(exam_points))

    lab_notes = _bullets(cj.get("labNotes"))
    if lab_notes:
        blocks.append("## Lab notes\n\n" + "\n".join(lab_notes))

    return "\n\n".join(blocks)


def summary_to_markdown(summary_type: str, content_json: dict | None) -> str:
    if summary_type == "brief":
        return brief_to_markdown(content_json)
    return detailed_to_markdown(content_json)
