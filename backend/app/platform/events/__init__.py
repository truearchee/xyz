from app.platform.events.recorder import (
    COMPLETED_QUIZ,
    GLOSSARY_PRACTICE_COMPLETED,
    GLOSSARY_TERM_SAVED,
    PERFECT_QUIZ_SCORE,
    QUIZ_EVENT_TYPES,
    STUDIED_SECTION,
    EventRecorder,
)
from app.platform.events.studied_section import (
    STUDIED_SECTION_NAMESPACE,
    record_studied_section,
)

__all__ = [
    "COMPLETED_QUIZ",
    "GLOSSARY_PRACTICE_COMPLETED",
    "GLOSSARY_TERM_SAVED",
    "PERFECT_QUIZ_SCORE",
    "QUIZ_EVENT_TYPES",
    "STUDIED_SECTION",
    "STUDIED_SECTION_NAMESPACE",
    "EventRecorder",
    "record_studied_section",
]
