import logging
import os
import sys

from redis import Redis
from rq import Queue, Worker

from app.domains.transcripts.embedding_encoder import validate_model_snapshot
from app.platform.config import settings
from app.workers.queues import EMBEDDING_QUEUE_NAME, INGESTION_QUEUE_NAME

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    queue_name = _queue_name()
    if queue_name == EMBEDDING_QUEUE_NAME:
        _validate_embedding_worker_startup()
    redis_url = os.environ["REDIS_URL"]
    connection = Redis.from_url(redis_url)
    worker = Worker([Queue(queue_name, connection=connection)], connection=connection)
    logger.info("Worker ready. Listening on %s queue.", queue_name)
    worker.work()


def _queue_name() -> str:
    if len(sys.argv) <= 1:
        return INGESTION_QUEUE_NAME
    if sys.argv[1] == "embedding":
        return EMBEDDING_QUEUE_NAME
    if sys.argv[1] == "ingestion":
        return INGESTION_QUEUE_NAME
    raise SystemExit("worker queue must be ingestion or embedding")


def _validate_embedding_worker_startup() -> None:
    _ = settings.EMBEDDING_BATCH_SIZE
    _ = settings.EMBEDDING_WORKER_CONCURRENCY
    validate_model_snapshot(
        model_path=settings.EMBEDDING_MODEL_PATH,
        expected_revision=settings.EMBEDDING_MODEL_REVISION,
    )


if __name__ == "__main__":
    main()
