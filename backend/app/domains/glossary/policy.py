"""Glossary access gates (Stage 7a) — personal scoping.

The glossary is personal per student. ``require_student`` (403) fires before any lookup; every resource
lookup is owner-scoped, and a miss (another student's row, or a non-existent one) is a 404 — never a 403,
so one student can neither read nor probe another's glossary.
"""

from __future__ import annotations

from fastapi import HTTPException, status

GLOSSARY_FORBIDDEN = "GLOSSARY_FORBIDDEN"
ENTRY_NOT_FOUND = "GLOSSARY_ENTRY_NOT_FOUND"
FOLDER_NOT_FOUND = "GLOSSARY_FOLDER_NOT_FOUND"
SESSION_NOT_FOUND = "GLOSSARY_PRACTICE_SESSION_NOT_FOUND"
SUBJECT_NOT_FOUND = "GLOSSARY_SUBJECT_NOT_FOUND"
SECTION_NOT_FOUND = "GLOSSARY_SECTION_NOT_FOUND"

FOLDER_NAME_EXISTS = "GLOSSARY_FOLDER_NAME_EXISTS"
FOLDER_SYSTEM_IMMUTABLE = "GLOSSARY_FOLDER_SYSTEM_IMMUTABLE"
ENTRY_TYPE_IMMUTABLE = "GLOSSARY_ENTRY_TYPE_IMMUTABLE"


def require_student(role: str) -> None:
    if role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=GLOSSARY_FORBIDDEN)


def not_found(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)


def conflict(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code})


def validation_error(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code})
