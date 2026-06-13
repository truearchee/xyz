from __future__ import annotations

import os
from uuid import UUID

from redis import Redis
from rq import Queue, Retry

from app.platform.config import settings


INGESTION_QUEUE_NAME = "ingestion"
EMBEDDING_QUEUE_NAME = "embedding"
AI_QUEUE_NAME = "ai"
EMBEDDING_RQ_RETRY_MAX = 3
EMBEDDING_RQ_RETRY_INTERVALS = [30, 120, 300]
# RQ retries are reserved for provider_transient + bounded invalid_output (rule 15).
AI_RQ_RETRY_MAX = 3
AI_RQ_RETRY_INTERVALS = [30, 120, 300]
# The RQ work-horse `job_timeout` MUST exceed the HTTP request timeout, else RQ SIGKILLs a legitimate long
# call (the detailed/reasoning K2-Think-v2 call on a real-sized transcript) mid-flight — before it can return
# OR fail cleanly — then retries into the same wall ("Work-horse terminated unexpectedly"). RQ's default
# (180s) is SHORTER than the 240s detailed HTTP timeout, so it was killing real detailed calls. Track the HTTP
# timeout (env; defaults mirror config.py LLM_*_TIMEOUT_SECONDS) + a buffer for limiter/backoff + persistence.
_AI_JOB_TIMEOUT_BUFFER_SECONDS = 120


def _summary_job_timeout(http_timeout_env: str, default_seconds: int) -> int:
    return int(os.environ.get(http_timeout_env, str(default_seconds))) + _AI_JOB_TIMEOUT_BUFFER_SECONDS


def _detailed_summary_job_timeout() -> int:
    """Detailed = map-reduce (4.5.1a): up to MAX_MAP_UNITS sequential map calls + a bounded tiered reduce
    (≤ MAP_UNITS reduce calls across tiers), each capped at the detailed HTTP timeout. Budget the RQ
    work-horse timeout as (map units + an equal reduce allowance) × the detailed timeout + buffer — a
    CEILING, not the expected run (a real ~60-min lecture is ~9 units, ~20 min). A sequential N-call job
    keeping the single-call timeout is the same SIGKILL we already hit once.

    MAX_MAP_UNITS is read from the SAME ``settings`` the partition cost-guard reads — raising it raises
    this ceiling in lock-step, so the cap and the timeout can never drift into two copies (decision 3)."""
    return (
        2 * settings.LLM_SUMMARY_MAX_MAP_UNITS * settings.LLM_DETAILED_TIMEOUT_SECONDS
        + _AI_JOB_TIMEOUT_BUFFER_SECONDS
    )


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
        job_timeout=_summary_job_timeout("LLM_PROVIDER_TIMEOUT_SECONDS", 60),
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )


def enqueue_generate_detailed_summary(ingestion_job_id: UUID) -> None:
    from app.domains.transcripts.jobs import generate_detailed_summary

    get_ai_queue().enqueue(
        generate_detailed_summary,
        str(ingestion_job_id),
        job_id=f"summary-detailed-{ingestion_job_id}",
        job_timeout=_detailed_summary_job_timeout(),
        retry=Retry(max=AI_RQ_RETRY_MAX, interval=AI_RQ_RETRY_INTERVALS),
    )


def enqueue_summary_job(job_type: str, ingestion_job_id: UUID) -> None:
    if job_type == "generate_brief_summary":
        enqueue_generate_brief_summary(ingestion_job_id)
    elif job_type == "generate_detailed_summary":
        enqueue_generate_detailed_summary(ingestion_job_id)
    else:
        raise ValueError(f"unknown summary job type: {job_type}")
