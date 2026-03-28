"""Tests for nexus/tasks — async task queue, retry, scheduling."""

import asyncio
import pytest
from nexus.tasks.queue import Task, TaskQueue, TaskStatus, task


class TestTaskQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_execute(self):
        queue = TaskQueue(workers=1)
        await queue.start()

        results = []

        async def my_task(x):
            results.append(x)

        task_id = await queue.enqueue(my_task, 42)
        await asyncio.sleep(0.2)

        t = queue.get_task(task_id)
        assert t is not None
        assert t.status == TaskStatus.SUCCESS
        assert results == [42]

        await queue.stop()

    @pytest.mark.asyncio
    async def test_failed_task_retries(self):
        queue = TaskQueue(workers=1)
        await queue.start()

        attempt_count = 0

        async def flaky():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Not yet")

        task_id = await queue.enqueue(flaky, max_retries=3, retry_delay=0.01)
        await asyncio.sleep(0.5)

        t = queue.get_task(task_id)
        assert t.status == TaskStatus.SUCCESS
        assert attempt_count == 3

        await queue.stop()

    @pytest.mark.asyncio
    async def test_permanent_failure(self):
        queue = TaskQueue(workers=1)
        await queue.start()

        async def always_fail():
            raise RuntimeError("always")

        task_id = await queue.enqueue(always_fail, max_retries=2, retry_delay=0.01)
        await asyncio.sleep(0.5)

        t = queue.get_task(task_id)
        assert t.status == TaskStatus.FAILED
        assert t.attempts == 2
        assert "always" in t.error

        await queue.stop()

    @pytest.mark.asyncio
    async def test_stats(self):
        queue = TaskQueue(workers=2)
        await queue.start()

        async def noop(): pass

        await queue.enqueue(noop)
        await asyncio.sleep(0.2)

        s = queue.stats()
        assert s["workers"] == 2
        assert "by_status" in s

        await queue.stop()

    @pytest.mark.asyncio
    async def test_task_decorator(self):
        queue = TaskQueue(workers=1)
        await queue.start()

        results = []

        @task(queue, max_retries=1)
        async def process(value):
            results.append(value)

        task_id = await process("hello")
        await asyncio.sleep(0.2)

        t = queue.get_task(task_id)
        assert t.status == TaskStatus.SUCCESS
        assert "hello" in results

        await queue.stop()

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        queue = TaskQueue(workers=1)
        await queue.start()

        async def noop(): pass

        await queue.enqueue(noop)
        await asyncio.sleep(0.2)

        tasks = queue.list_tasks()
        assert len(tasks) >= 1

        success_tasks = queue.list_tasks(status=TaskStatus.SUCCESS)
        assert all(t.status == TaskStatus.SUCCESS for t in success_tasks)

        await queue.stop()
