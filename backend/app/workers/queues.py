from __future__ import annotations

import os
from uuid import UUID

from redis import Redis
from rq import Queue, Retry


INGESTION_QUEUE_NAME = "ingestion"
EMBEDDING_QUEUE_NAME = "embedding"
AI_QUEUE_NAME = "ai"
EMBEDDING_RQ_RETRY_MAX = 3
EMBEDDING_RQ_RETRY_INTERVALS = [30, 120, 300]
# RQ retries are reserved for provider_transient + bounded invalid_output (rule 15).
AI_RQ_RETRY_MAX = 3
AI_RQ_RETRY_INTERVALS = [30, 120, 300]


def get_redis_connection() -> Redis:
    return Redis.from_url(os.environ["REDIS_URL"])


def get_ingestion_queue() -> Queue:
    return Queue(INGESTION_QUEUE_NAME, connection=get_redis_connection())


def get_embedding_queue() -> Queue:
    return Queue(EMBEDDING_QUEUE_NAME, connection=get_redis_connection())


def get_ai_queue() -> Queue:
    return Queue(AI_QUEUE_NAME, connection=get_redis_connection())


def quiz_generation_job_id(attempt_id: UUID) -> str:
    return f"quiz-generate-{attempt_id}"


def section_pool_job_id(pool_id: UUID) -> str:
    return f"quiz-pool-{pool_id}"


def enqueue_parse_transcript(transcript_id: UUID) -> None:
    from app.domains.transcripts.jobs import parse_transcript

    get_ingestion_queue().enqueue(parse_transcript, str(transcript_id))


def enqueue_chunk_transcript(ingestion_job_id: UUID) -> None:
    from app.domains.transcripts.jobs import chunk_transcript

    get_ingestion_queue().enqueue(chunk_transcript, str(ingestion_job_id))


def enqueue_embed_transcript(ingestion_job_id: UUID) -> None:
    from app.domains.transcripts.jobs import embed_transcript

    queue = get_embedding_queue()
    queue.enqueue(
        embed_transcript,
        str(ingestion_job_id),
        job_id=f"embed-{ingestion_job_id}",
        retry=Retry(max=EMBEDDING_RQ_RETRY_MAX, interval=EMBEDDING_RQ_RETRY_INTERVALS),
    )


def enqueue_generate_brief_summary(ingestion_job_id: UUID) -> None:
    from app.domains.transcripts.jobs import generate_brief_summary

    get_ai_queue().enqueue(
        generate_brief_summary,
        str(ingestion_job_id),
        job_id=f"summary-brief-{ingestion_job_id}",
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )


def enqueue_generate_detailed_summary(ingestion_job_id: UUID) -> None:
    from app.domains.transcripts.jobs import generate_detailed_summary

    get_ai_queue().enqueue(
        generate_detailed_summary,
        str(ingestion_job_id),
        job_id=f"summary-detailed-{ingestion_job_id}",
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )


def enqueue_generate_post_class_quiz(attempt_id: UUID) -> str:
    from app.domains.quiz.jobs import generate_post_class_quiz

    job_id = quiz_generation_job_id(attempt_id)
    get_ai_queue().enqueue(
        generate_post_class_quiz,
        str(attempt_id),
        job_id=job_id,
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )
    return job_id


def enqueue_generate_section_pool(pool_id: UUID) -> str:
    """Enqueue a section-pool generation (Stage 6a) under a stable job id (``quiz-pool-{pool_id}``) so the
    reaper can check its liveness. Bounded RQ retry for transient / invalid-output failures (rule 15)."""
    from app.domains.quiz.jobs import generate_section_pool

    job_id = section_pool_job_id(pool_id)
    get_ai_queue().enqueue(
        generate_section_pool,
        str(pool_id),
        job_id=job_id,
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )
    return job_id


def enqueue_try_assemble_attempt(attempt_id: UUID) -> str:
    """Enqueue a pooled-attempt assembly (Stage 6a) under the SAME stable id as post_class generation
    (``quiz-generate-{attempt_id}``) so the stuck-row reaper's liveness check keys on it correctly. The
    job is idempotent/fenced, so the start-enqueue + each pool-completion fan-in re-enqueue are safe."""
    from app.domains.quiz.jobs import try_assemble_attempt

    job_id = quiz_generation_job_id(attempt_id)
    get_ai_queue().enqueue(
        try_assemble_attempt,
        str(attempt_id),
        job_id=job_id,
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )
    return job_id


def enqueue_generate_glossary_definition(cache_row_id: UUID) -> str:
    from app.domains.glossary.jobs import generate_glossary_definition

    job_id = f"glossary-definition-{cache_row_id}"
    get_ai_queue().enqueue(
        generate_glossary_definition,
        str(cache_row_id),
        job_id=job_id,
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )
    return job_id


def assistant_answer_job_id(message_id: UUID) -> str:
    return f"assistant-answer-{message_id}"


def enqueue_generate_assistant_answer(message_id: UUID) -> str:
    """Enqueue a Stage 8.1 interactive assistant turn. ``at_front=True`` so a chat answer is not stuck
    behind a long-running background summary/pool job (a ~264s reasoning generation); combined with the
    limiter's reserved interactive headroom (rule 15), interactive traffic keeps priority. Bounded RQ
    retry for transient / invalid_output only (rule 15)."""
    from app.domains.assistant.jobs import generate_assistant_answer

    job_id = assistant_answer_job_id(message_id)
    get_ai_queue().enqueue(
        generate_assistant_answer,
        str(message_id),
        job_id=job_id,
        at_front=True,
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )
    return job_id


def enqueue_summary_job(job_type: str, ingestion_job_id: UUID) -> None:
    if job_type == "generate_brief_summary":
        enqueue_generate_brief_summary(ingestion_job_id)
    elif job_type == "generate_detailed_summary":
        enqueue_generate_detailed_summary(ingestion_job_id)
    else:
        raise ValueError(f"unknown summary job type: {job_type}")
