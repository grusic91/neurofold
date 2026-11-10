"""Zero-queue blocking execution; cancellation never releases running capacity."""

import asyncio
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Lock


class AdmissionLimit(RuntimeError):
    pass


class OperationTimeout(RuntimeError):
    pass


class BlockingExecutor:
    def __init__(self, workers: int, seconds: float) -> None:
        self.pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="neurofold"
        )
        self.slots = BoundedSemaphore(workers)
        self.seconds = seconds
        self.lock = Lock()
        self.closed = False

    async def run[T](self, operation: Callable[[], T]) -> T:
        with self.lock:
            if self.closed or not self.slots.acquire(blocking=False):
                raise AdmissionLimit
            try:
                future = self.pool.submit(operation)
            except BaseException:
                self.slots.release()
                raise
        # Release only from the actual concurrent future, not the awaiting task.
        future.add_done_callback(self._finished)
        wrapped = asyncio.wrap_future(future)
        # Observe late exceptions even when no HTTP awaiter remains. Capacity is
        # still released exclusively by the concurrent future callback above.
        wrapped.add_done_callback(
            lambda done: done.exception() if not done.cancelled() else None
        )
        done, _ = await asyncio.wait({wrapped}, timeout=self.seconds)
        if not done:
            raise OperationTimeout
        return wrapped.result()

    def _finished[T](self, future: Future[T]) -> None:
        self.slots.release()

    async def close(self) -> None:
        with self.lock:
            self.closed = True
        await asyncio.to_thread(self.pool.shutdown, wait=True, cancel_futures=False)
