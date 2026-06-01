import logging
import os

from redis import Redis
from rq import Queue, Worker

from app.workers.queues import INGESTION_QUEUE_NAME

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    redis_url = os.environ["REDIS_URL"]
    connection = Redis.from_url(redis_url)
    worker = Worker([Queue(INGESTION_QUEUE_NAME, connection=connection)], connection=connection)
    logger.info("Worker ready. Listening on %s queue.", INGESTION_QUEUE_NAME)
    worker.work()


if __name__ == "__main__":
    main()
