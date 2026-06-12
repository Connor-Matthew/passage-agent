"""Standalone article task worker entrypoint."""

import asyncio
import contextlib
import logging
import signal

from app.config import settings
from app.database import database
from app.services.article_task_queue import article_task_queue_manager
from app.utils.session import close_redis, init_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_worker():
    """Run article queue consumers until the process receives a stop signal."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    await database.connect()
    await init_redis()
    await article_task_queue_manager.start()
    logger.info(
        "Article worker started, maxSize=%s, workerConcurrency=%s",
        settings.article_task_queue_max_size,
        settings.article_task_worker_concurrency,
    )

    try:
        await stop_event.wait()
    finally:
        await article_task_queue_manager.stop()
        await database.disconnect()
        await close_redis()
        logger.info("Article worker stopped")


def main():
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
