from __future__ import annotations

import os
from uuid import UUID

from redis import Redis
from rq import Queue


INGESTION_QUEUE_NAME = "ingestion"


def get_redis_connection() -> Redis:
    return Redis.from_url(os.environ["REDIS_URL"])


def get_ingestion_queue() -> Queue:
    return Queue(INGESTION_QUEUE_NAME, connection=get_redis_connection())


def enqueue_parse_transcript(transcript_id: UUID) -> None:
    from app.domains.transcripts.jobs import parse_transcript

    get_ingestion_queue().enqueue(parse_transcript, str(transcript_id))


def enqueue_chunk_transcript(ingestion_job_id: UUID) -> None:
    from app.domains.transcripts.jobs import chunk_transcript

    get_ingestion_queue().enqueue(chunk_transcript, str(ingestion_job_id))
