from app.platform.db.models.ai_request_log import AIRequestLog
from app.platform.db.models.answer_option import AnswerOption
from app.platform.db.models.assessment_scope import AssessmentScope
from app.platform.db.models.base import Base
from app.platform.db.models.course_membership import CourseMembership
from app.platform.db.models.course_module import CourseModule
from app.platform.db.models.generated_lecture_summary import GeneratedLectureSummary
from app.platform.db.models.glossary_definition_cache import GlossaryDefinitionCache
from app.platform.db.models.glossary_entry import GlossaryEntry
from app.platform.db.models.glossary_folder import GlossaryFolder
from app.platform.db.models.glossary_practice_answer import GlossaryPracticeAnswer
from app.platform.db.models.glossary_practice_session import GlossaryPracticeSession
from app.platform.db.models.glossary_review_state import GlossaryReviewState
from app.platform.db.models.glossary_source_reference import GlossarySourceReference
from app.platform.db.models.ingestion_job import IngestionJob
from app.platform.db.models.maintenance_run import MaintenanceRun
from app.platform.db.models.mistake_record import MistakeRecord
from app.platform.db.models.module_section import ModuleSection
from app.platform.db.models.pool_question import PoolQuestion
from app.platform.db.models.quiz_attempt import QuizAttempt
from app.platform.db.models.quiz_definition import QuizDefinition
from app.platform.db.models.quiz_question import QuizQuestion
from app.platform.db.models.section_asset import SectionAsset
from app.platform.db.models.section_question_pool import SectionQuestionPool
from app.platform.db.models.student_activity_event import StudentActivityEvent
from app.platform.db.models.student_answer import StudentAnswer
from app.platform.db.models.transcript import Transcript
from app.platform.db.models.transcript_chunk import TranscriptChunk
from app.platform.db.models.transcript_segment import TranscriptSegment
from app.platform.db.models.user import AppUser

__all__ = [
    "AIRequestLog",
    "AnswerOption",
    "AppUser",
    "AssessmentScope",
    "Base",
    "CourseMembership",
    "CourseModule",
    "GeneratedLectureSummary",
    "GlossaryDefinitionCache",
    "GlossaryEntry",
    "GlossaryFolder",
    "GlossaryPracticeAnswer",
    "GlossaryPracticeSession",
    "GlossaryReviewState",
    "GlossarySourceReference",
    "IngestionJob",
    "MaintenanceRun",
    "MistakeRecord",
    "ModuleSection",
    "PoolQuestion",
    "QuizAttempt",
    "QuizDefinition",
    "QuizQuestion",
    "SectionAsset",
    "SectionQuestionPool",
    "StudentActivityEvent",
    "StudentAnswer",
    "Transcript",
    "TranscriptChunk",
    "TranscriptSegment",
]
