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


def enqueue_summary_job(job_type: str, ingestion_job_id: UUID) -> None:
    if job_type == "generate_brief_summary":
        enqueue_generate_brief_summary(ingestion_job_id)
    elif job_type == "generate_detailed_summary":
        enqueue_generate_detailed_summary(ingestion_job_id)
    else:
        raise ValueError(f"unknown summary job type: {job_type}")
