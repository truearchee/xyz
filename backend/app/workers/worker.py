import logging
import os

from redis import Redis
from rq import Queue, Worker

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    redis_url = os.environ["REDIS_URL"]
    connection = Redis.from_url(redis_url)
    worker = Worker([Queue("default", connection=connection)], connection=connection)
    logger.info("Worker ready. Listening on default queue.")
    worker.work()


if __name__ == "__main__":
    main()
