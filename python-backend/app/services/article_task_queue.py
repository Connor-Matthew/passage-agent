"""Redis-backed article task queue with bounded backlog and worker concurrency."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

from redis.asyncio import Redis

from app.config import settings
from app.exceptions import BusinessException, ErrorCode
from app.services.article_async_service import article_async_service
from app.utils import session as session_utils

logger = logging.getLogger(__name__)


class ArticleTaskQueueManager:
    """Bounded article task queue.

    The queue accepts up to ``article_task_queue_max_size`` pending jobs and
    starts ``article_task_worker_concurrency`` worker loops in the API process.
    This keeps article generation from creating unbounded background tasks.
    """

    _ENQUEUE_SCRIPT = """
    local length = redis.call('LLEN', KEYS[1])
    if tonumber(length) >= tonumber(ARGV[2]) then
        return 0
    end
    redis.call('RPUSH', KEYS[1], ARGV[1])
    return 1
    """

    def __init__(self):
        self.queue_key = settings.article_task_queue_key
        self.max_size = max(1, settings.article_task_queue_max_size)
        self.worker_concurrency = max(1, settings.article_task_worker_concurrency)
        self._workers: list[asyncio.Task] = []
        self._active_task_ids: Set[str] = set()

    async def start(self):
        """Start queue consumers if they are not already running."""
        if self._workers:
            return

        self._get_client()
        for worker_index in range(self.worker_concurrency):
            self._workers.append(
                asyncio.create_task(
                    self._worker_loop(worker_index + 1),
                    name=f"article-task-worker-{worker_index + 1}",
                )
            )
        logger.info(
            "Article task queue started, key=%s, maxSize=%s, workerConcurrency=%s",
            self.queue_key,
            self.max_size,
            self.worker_concurrency,
        )

    async def stop(self):
        """Stop queue consumers gracefully during application shutdown."""
        if not self._workers:
            return

        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._active_task_ids.clear()
        logger.info("Article task queue stopped")

    async def enqueue_phase1(
        self,
        task_id: str,
        topic: str,
        style: Optional[str],
        enable_web_search: bool,
    ):
        """Queue phase 1 title generation."""
        await self._enqueue({
            "phase": "phase1",
            "taskId": task_id,
            "topic": topic,
            "style": style,
            "enableWebSearch": enable_web_search,
        })

    async def enqueue_phase2(self, task_id: str):
        """Queue phase 2 outline generation."""
        await self._enqueue({"phase": "phase2", "taskId": task_id})

    async def enqueue_phase3(self, task_id: str):
        """Queue phase 3 content and image generation."""
        await self._enqueue({"phase": "phase3", "taskId": task_id})

    async def ensure_has_capacity(self):
        """Fail fast when the backlog is already full."""
        stats = await self.get_stats()
        if stats["pending"] >= self.max_size:
            raise BusinessException(
                ErrorCode.OPERATION_ERROR,
                f"任务队列已满（最多排队 {self.max_size} 个），请稍后再试",
            )

    async def get_stats(self) -> Dict[str, Any]:
        """Return queue depth and worker state for diagnostics."""
        client = self._get_client()
        pending = await client.llen(self.queue_key)
        return {
            "queueKey": self.queue_key,
            "pending": pending,
            "maxSize": self.max_size,
            "workerConcurrency": self.worker_concurrency,
            "workersRunning": len(self._workers),
            "active": len(self._active_task_ids),
            "activeTaskIds": sorted(self._active_task_ids),
        }

    async def _enqueue(self, payload: Dict[str, Any]):
        client = self._get_client()
        payload_json = json.dumps(payload, ensure_ascii=False)
        queued = await client.eval(
            self._ENQUEUE_SCRIPT,
            1,
            self.queue_key,
            payload_json,
            self.max_size,
        )
        if int(queued) != 1:
            raise BusinessException(
                ErrorCode.OPERATION_ERROR,
                f"任务队列已满（最多排队 {self.max_size} 个），请稍后再试",
            )
        logger.info(
            "Article task queued, taskId=%s, phase=%s",
            payload.get("taskId"),
            payload.get("phase"),
        )

    async def _worker_loop(self, worker_id: int):
        client = self._get_client()
        logger.info("Article task worker started, workerId=%s", worker_id)
        while True:
            try:
                result = await client.blpop(self.queue_key, timeout=5)
                if result is None:
                    continue

                _, payload_json = result
                if isinstance(payload_json, bytes):
                    payload_json = payload_json.decode("utf-8")
                payload = json.loads(payload_json)
                await self._execute(payload, worker_id)
            except asyncio.CancelledError:
                logger.info("Article task worker cancelled, workerId=%s", worker_id)
                raise
            except Exception:
                logger.exception("Article task worker error, workerId=%s", worker_id)

    async def _execute(self, payload: Dict[str, Any], worker_id: int):
        phase = payload.get("phase")
        task_id = payload.get("taskId")
        if not task_id:
            logger.error("Article task payload missing taskId, payload=%s", payload)
            return

        self._active_task_ids.add(task_id)
        logger.info(
            "Article task started, workerId=%s, taskId=%s, phase=%s",
            worker_id,
            task_id,
            phase,
        )
        try:
            if phase == "phase1":
                await article_async_service.execute_phase1(
                    task_id=task_id,
                    topic=payload.get("topic") or "",
                    style=payload.get("style"),
                    enable_web_search=bool(payload.get("enableWebSearch")),
                )
            elif phase == "phase2":
                await article_async_service.execute_phase2(task_id)
            elif phase == "phase3":
                await article_async_service.execute_phase3(task_id)
            else:
                logger.error("Unknown article task phase, taskId=%s, phase=%s", task_id, phase)
        finally:
            self._active_task_ids.discard(task_id)
            logger.info(
                "Article task finished, workerId=%s, taskId=%s, phase=%s",
                worker_id,
                task_id,
                phase,
            )

    def _get_client(self) -> Redis:
        client = session_utils.redis_client
        if client is None:
            raise RuntimeError("Redis 未初始化，无法使用文章任务队列")
        return client


article_task_queue_manager = ArticleTaskQueueManager()
