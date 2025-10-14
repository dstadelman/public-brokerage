"""
Worker thread pool for executing order operations.

Workers handle:
- Order placement logic
- Verification loops
- Business logic
- Queuing API requests (NOT making HTTP calls directly!)

Workers do NOT:
- Make HTTP requests directly
- Access network sockets
- Handle rate limiting
"""

import threading
import uuid
import time
import logging
from typing import Callable, Any, Optional, Dict, Union, Set

logger = logging.getLogger(__name__)


# ============================================================================
# Global Cancellation Registry (Thread-Safe)
# ============================================================================

class CancellationRegistry:
    """
    Thread-safe registry of cancelled task IDs.
    
    Workers check this registry periodically to see if their task has been cancelled.
    This is much better than per-task threading.Events:
    - Single global registry (no per-task overhead)
    - Can cancel tasks by ID
    - Thread-safe with minimal locking
    - Workers can check cancellation status anytime
    """
    
    def __init__(self):
        self._cancelled_tasks: Set[str] = set()
        self._lock = threading.Lock()
    
    def cancel(self, task_id: str) -> bool:
        """
        Mark a task as cancelled.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if task was newly cancelled, False if already cancelled
        """
        with self._lock:
            if task_id in self._cancelled_tasks:
                return False
            self._cancelled_tasks.add(task_id)
            logger.info(f"Task {task_id} marked for cancellation")
            return True
    
    def is_cancelled(self, task_id: str) -> bool:
        """
        Check if a task has been cancelled.
        
        Args:
            task_id: Task ID to check
            
        Returns:
            True if task is cancelled, False otherwise
        """
        with self._lock:
            return task_id in self._cancelled_tasks
    
    def clear(self, task_id: str) -> bool:
        """
        Remove a task from the cancelled set (cleanup after completion).
        
        Args:
            task_id: Task ID to clear
            
        Returns:
            True if task was in cancelled set, False otherwise
        """
        with self._lock:
            if task_id in self._cancelled_tasks:
                self._cancelled_tasks.discard(task_id)
                return True
            return False
    
    def reset(self):
        """Clear all cancelled tasks (for testing)."""
        with self._lock:
            self._cancelled_tasks.clear()


# Global cancellation registry
_cancellation_registry = CancellationRegistry()


def is_task_cancelled(task_id: str) -> bool:
    """
    Check if a task has been cancelled.
    
    Workers call this function periodically during long-running operations.
    
    Args:
        task_id: Task ID to check
        
    Returns:
        True if task should stop, False otherwise
    """
    return _cancellation_registry.is_cancelled(task_id)


def cancel_task(task_id: str) -> bool:
    """
    Request cancellation of a task.
    
    This doesn't forcibly stop the task - it just marks it as cancelled.
    The task must check is_task_cancelled() periodically and exit gracefully.
    
    Args:
        task_id: Task ID to cancel
        
    Returns:
        True if task was newly cancelled, False if already cancelled
    """
    return _cancellation_registry.cancel(task_id)


class WorkerThread(threading.Thread):
    """
    Worker thread that executes a task function.
    
    The task function can queue API requests through the API queue
    and will receive responses back. The worker never makes direct
    HTTP calls.
    """
    
    def __init__(self, task_id: str, task_func: Callable, task_name: str, *args, **kwargs):
        super().__init__(daemon=True, name=f"Worker-{task_name}")
        self.task_id = task_id
        self.task_func = task_func
        self.task_name = task_name
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.error = None
        self.completed = threading.Event()
        self.started_at = None
        self.completed_at = None
    
    def run(self):
        """Execute the task function"""
        self.started_at = time.time()
        logger.info(f"[{self.name}] Starting task: {self.task_name} (ID: {self.task_id})")
        
        try:
            # Pass task_id to the task function so it can check for cancellation
            self.result = self.task_func(self.task_id, *self.args, **self.kwargs)
            logger.info(f"[{self.name}] Task completed successfully")
        except Exception as e:
            self.error = e
            logger.error(f"[{self.name}] Task failed: {e}")
        finally:
            self.completed_at = time.time()
            elapsed = self.completed_at - self.started_at
            logger.info(f"[{self.name}] Task finished in {elapsed:.2f}s")
            self.completed.set()
            # Clean up cancellation registry
            _cancellation_registry.clear(self.task_id)
    
    def wait(self, timeout: Optional[float] = None) -> Any:
        """
        Wait for worker to complete and return result.
        
        Args:
            timeout: Maximum time to wait (seconds)
            
        Returns:
            Task result
            
        Raises:
            TimeoutError: If worker doesn't complete in time
            Exception: Whatever exception the task raised
        """
        if not self.completed.wait(timeout):
            raise TimeoutError(f"Worker {self.name} timed out after {timeout}s")
        
        if self.error:
            raise self.error
        
        return self.result
    
    def is_done(self) -> bool:
        """Check if worker has completed"""
        return self.completed.is_set()
    
    def cancel(self) -> bool:
        """
        Request cancellation of this worker's task.
        
        Returns:
            True if task was newly cancelled, False if already cancelled
        """
        return cancel_task(self.task_id)


class WorkerPool:
    """
    Pool of worker threads for executing tasks.
    
    Each task runs in its own worker thread. Workers can make API
    requests by queuing them through the API queue.
    """
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.workers: Dict[str, WorkerThread] = {}
        self.lock = threading.Lock()
        logger.info(f"Worker pool initialized with max {max_workers} workers")
    
    def submit(
        self, 
        task_func: Callable, 
        task_name: str,
        *args, 
        **kwargs
    ) -> tuple:
        """
        Submit a task to be executed in a worker thread.
        
        Args:
            task_func: Function to execute
            task_name: Human-readable task name
            *args: Arguments for task_func
            **kwargs: Keyword arguments for task_func
            
        Returns:
            (task_id, worker) tuple
            
        Raises:
            RuntimeError: If pool is at max capacity
        """
        with self.lock:
            # Check capacity
            active = sum(1 for w in self.workers.values() if not w.is_done())
            if active >= self.max_workers:
                raise RuntimeError(f"Worker pool at capacity ({self.max_workers} workers)")
            
            # Create unique task ID
            task_id = str(uuid.uuid4())[:8]
            
            # Create worker
            worker = WorkerThread(task_id, task_func, task_name, *args, **kwargs)
            self.workers[task_id] = worker
            
            logger.info(f"[POOL] Submitting task '{task_name}' (ID: {task_id})")
            worker.start()
            
            return task_id, worker
    
    def get_worker(self, task_id: str) -> Optional[WorkerThread]:
        """Get a worker by task ID"""
        with self.lock:
            return self.workers.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task by ID.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if task was cancelled, False if not found or already done
        """
        worker = self.get_worker(task_id)
        if worker and not worker.is_done():
            return worker.cancel()
        return False
    
    def wait_all(self, timeout: Optional[float] = None):
        """Wait for all active workers to complete"""
        with self.lock:
            workers = list(self.workers.values())
        
        for worker in workers:
            if not worker.is_done():
                worker.wait(timeout)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker pool statistics"""
        with self.lock:
            total = len(self.workers)
            active = sum(1 for w in self.workers.values() if not w.is_done())
            completed = total - active
            
            return {
                'total_workers': total,
                'active_workers': active,
                'completed_workers': completed,
                'max_workers': self.max_workers,
                'at_capacity': active >= self.max_workers
            }


# Global worker pool instance
_worker_pool: Optional[WorkerPool] = None


def get_worker_pool() -> WorkerPool:
    """Get the global worker pool instance"""
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = WorkerPool(max_workers=10)
    return _worker_pool


def submit_task(task_func: Callable, task_name: str, *args, **kwargs) -> tuple:
    """
    Convenience function to submit a task to the global worker pool.
    
    Args:
        task_func: Function to execute
        task_name: Human-readable task name
        *args: Arguments for task_func
        **kwargs: Keyword arguments for task_func
        
    Returns:
        (worker_id, worker) tuple
    """
    return get_worker_pool().submit(task_func, task_name, *args, **kwargs)
