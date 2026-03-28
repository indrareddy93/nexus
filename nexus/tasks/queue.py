"""Async background task queue — workers, retry with exponential backoff, scheduling."""

from __future__ import annotations

import asyncio
import functools
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("nexus.tasks")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """
    A single unit of background work.

    Attributes
    ----------
    fn:          The async callable to execute.
    args:        Positional arguments.
    kwargs:      Keyword arguments.
    max_retries: Maximum retry attempts on failure.
    retry_delay: Initial delay (seconds) before first retry; doubles each attempt.
    task_id:     Auto-generated UUID for tracking.
    status:      Current lifecycle status.
    result:      Return value after success.
    error:       Exception message on failure.
    """

    fn: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    max_retries: int = 3
    retry_delay: float = 1.0
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    attempts: int = 0
    created_at: float = field(default_factory=time.monotonic)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def elapsed(self) -> float | None:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "fn": getattr(self.fn, "__name__", str(self.fn)),
            "status": self.status.value,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "elapsed_s": round(self.elapsed, 4) if self.elapsed else None,
        }


class TaskQueue:
    """
    Async background task queue with configurable workers.

    Features:
    - Multiple concurrent workers
    - Automatic retry with exponential backoff
    - Periodic scheduled tasks (cron-style)
    - Task status tracking

    Usage::

        queue = TaskQueue(workers=4)
        await queue.start()

        # Enqueue a task
        task_id = await queue.enqueue(send_email, to="user@example.com", subject="Hi")

        # Check status
        status = queue.get_task(task_id)

        # Schedule recurring task (every 60 seconds)
        queue.schedule(sync_data, interval=60)

        await queue.stop()
    """

    def __init__(self, workers: int = 2, max_queue_size: int = 1000) -> None:
        self.workers = workers
        self._queue: asyncio.Queue[Task] = asyncio.Queue(maxsize=max_queue_size)
        self._tasks: dict[str, Task] = {}
        self._worker_tasks: list[asyncio.Task] = []
        self._scheduler_tasks: list[asyncio.Task] = []
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start worker coroutines."""
        if self._running:
            return
        self._running = True
        for i in range(self.workers):
            worker = asyncio.create_task(self._worker(i), name=f"nexus-worker-{i}")
            self._worker_tasks.append(worker)
        logger.info("TaskQueue started with %d workers", self.workers)

    async def stop(self, timeout: float = 10.0) -> None:
        """Gracefully drain the queue and stop workers."""
        self._running = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Queue did not drain within %ss — cancelling workers", timeout)
        for w in self._worker_tasks:
            w.cancel()
        for s in self._scheduler_tasks:
            s.cancel()
        self._worker_tasks.clear()
        self._scheduler_tasks.clear()
        logger.info("TaskQueue stopped")

    # ------------------------------------------------------------------
    # Enqueueing
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        fn: Callable,
        *args: Any,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs: Any,
    ) -> str:
        """
        Add a task to the queue. Returns the task ID.

        Usage::

            task_id = await queue.enqueue(
                send_email,
                to="user@example.com",
                subject="Welcome",
                max_retries=5,
            )
        """
        t = Task(
            fn=fn,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        self._tasks[t.task_id] = t
        await self._queue.put(t)
        logger.debug("Enqueued task %s → %s", t.task_id, fn.__name__)
        return t.task_id

    def enqueue_nowait(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        """Non-blocking enqueue (raises QueueFull if the queue is at capacity)."""
        t = Task(fn=fn, args=args, kwargs=kwargs)
        self._tasks[t.task_id] = t
        self._queue.put_nowait(t)
        return t.task_id

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule(
        self,
        fn: Callable,
        *,
        interval: float,
        args: tuple = (),
        kwargs: dict | None = None,
        run_immediately: bool = False,
    ) -> None:
        """
        Schedule *fn* to run every *interval* seconds.

        Usage::

            queue.schedule(cleanup_expired_tokens, interval=3600)
        """
        async def _loop() -> None:
            if not run_immediately:
                await asyncio.sleep(interval)
            while self._running:
                await self.enqueue(fn, *args, **(kwargs or {}))
                await asyncio.sleep(interval)

        task_obj = asyncio.create_task(_loop(), name=f"nexus-schedule-{fn.__name__}")
        self._scheduler_tasks.append(task_obj)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[Task]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks[-limit:]

    def stats(self) -> dict[str, Any]:
        total = len(self._tasks)
        by_status: dict[str, int] = {}
        for t in self._tasks.values():
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        return {
            "total": total,
            "queue_size": self._queue.qsize(),
            "workers": self.workers,
            "by_status": by_status,
        }

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _worker(self, worker_id: int) -> None:
        while self._running:
            try:
                t: Task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            await self._execute(t, worker_id)
            self._queue.task_done()

    async def _execute(self, t: Task, worker_id: int) -> None:
        t.status = TaskStatus.RUNNING
        t.started_at = time.monotonic()
        t.attempts += 1
        logger.debug("Worker-%d executing task %s (attempt %d)", worker_id, t.task_id, t.attempts)

        try:
            if asyncio.iscoroutinefunction(t.fn):
                result = await t.fn(*t.args, **t.kwargs)
            else:
                result = t.fn(*t.args, **t.kwargs)
            t.result = result
            t.status = TaskStatus.SUCCESS
            t.finished_at = time.monotonic()
            logger.debug("Task %s succeeded in %.3fs", t.task_id, t.elapsed or 0)

        except Exception as exc:
            t.error = f"{type(exc).__name__}: {exc}"
            if t.attempts < t.max_retries:
                delay = t.retry_delay * (2 ** (t.attempts - 1))  # exponential backoff
                t.status = TaskStatus.RETRYING
                logger.warning(
                    "Task %s failed (attempt %d/%d), retrying in %.1fs: %s",
                    t.task_id, t.attempts, t.max_retries, delay, exc,
                )
                await asyncio.sleep(delay)
                await self._queue.put(t)
            else:
                t.status = TaskStatus.FAILED
                t.finished_at = time.monotonic()
                logger.error("Task %s failed permanently after %d attempts: %s", t.task_id, t.attempts, exc)


def task(
    queue: TaskQueue,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Callable:
    """
    Decorator that turns a function into a background task.

    Usage::

        @task(queue, max_retries=5)
        async def send_email(to: str, subject: str):
            ...

        # Call normally — automatically enqueued
        task_id = await send_email("user@example.com", "Hello")
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            return await queue.enqueue(
                fn, *args, max_retries=max_retries, retry_delay=retry_delay, **kwargs
            )
        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapper
    return decorator
