"""
API Request Queue Manager

Centralized queue system for all API calls to prevent concurrency issues
and ensure proper throttling between requests.
"""

import time
import threading
import queue
import logging
from typing import Any, Callable, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


@dataclass
class ApiRequest:
    """Represents a queued API request."""
    request_id: str
    func: Callable
    args: tuple
    kwargs: dict
    result_event: threading.Event
    http_method: str = "GET"  # Default to GET for safety
    result: Any = None
    error: Exception = None
    created_at: datetime = None
    processed_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def is_write_operation(self) -> bool:
        """Check if this is a write operation that needs longer delay."""
        return self.http_method.upper() in ['POST', 'PUT', 'DELETE', 'PATCH']


class ApiRequestQueue:
    """
    Thread-safe API request queue with throttling.
    
    All API calls should go through this queue to prevent concurrency issues
    and ensure proper rate limiting.
    """
    
    def __init__(self, read_delay: float = 0.0, write_delay: float = 5.0):
        """
        Initialize the API request queue with method-based throttling.
        
        Args:
            read_delay: Seconds to wait between GET requests (default: 0.0)
            write_delay: Seconds to wait between POST/PUT/DELETE requests (default: 5.0)
        """
        self.read_delay = read_delay
        self.write_delay = write_delay
        self.request_queue = queue.Queue()
        self.is_running = False
        self.worker_thread = None
        self.last_request_time = 0
        self.total_requests = 0
        self.failed_requests = 0
        
        logger.info(f"API Request Queue initialized - READ delay: {read_delay}s, WRITE delay: {write_delay}s")
    
    def start(self):
        """Start the queue processing thread."""
        if self.is_running:
            logger.warning("API Request Queue is already running")
            return
            
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        logger.info("API Request Queue started")
    
    def stop(self):
        """Stop the queue processing thread."""
        if not self.is_running:
            return
            
        self.is_running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
        logger.info("API Request Queue stopped")
    
    def execute(self, func: Callable, *args, http_method: str = "GET", timeout: float = 30.0, **kwargs) -> Any:
        """
        Execute an API call through the queue with method-based throttling.
        
        Args:
            func: The function to call
            *args: Function arguments
            http_method: HTTP method (GET, POST, PUT, DELETE) for smart throttling
            timeout: Maximum time to wait for result (seconds)
            **kwargs: Function keyword arguments
            
        Returns:
            The result of the function call
            
        Raises:
            Exception: If the API call fails or times out
        """
        if not self.is_running:
            self.start()
        
        # Create request
        request_id = str(uuid.uuid4())[:8]
        result_event = threading.Event()
        
        api_request = ApiRequest(
            request_id=request_id,
            func=func,
            args=args,
            kwargs=kwargs,
            result_event=result_event,
            http_method=http_method.upper()
        )
        
        # Queue the request
        self.request_queue.put(api_request)
        logger.debug(f"Queued API request {request_id}: {func.__name__}")
        
        # Wait for result
        if result_event.wait(timeout=timeout):
            if api_request.error:
                logger.error(f"API request {request_id} failed: {api_request.error}")
                raise api_request.error
            
            logger.debug(f"API request {request_id} completed successfully")
            return api_request.result
        else:
            logger.error(f"API request {request_id} timed out after {timeout}s")
            raise TimeoutError(f"API request timed out after {timeout} seconds")
    
    def _process_queue(self):
        """Worker thread that processes queued API requests."""
        logger.info("API Request Queue worker thread started")
        
        while self.is_running:
            try:
                # Get next request (with timeout to check is_running periodically)
                try:
                    api_request = self.request_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Determine delay based on HTTP method
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                
                # Smart throttling: different delays for read vs write operations
                if api_request.is_write_operation():
                    required_delay = self.write_delay
                    operation_type = "WRITE"
                else:
                    required_delay = self.read_delay
                    operation_type = "READ"
                
                if time_since_last < required_delay:
                    sleep_time = required_delay - time_since_last
                    logger.debug(f"Throttling {operation_type} ({api_request.http_method}): sleeping {sleep_time:.2f}s before next API call")
                    time.sleep(sleep_time)
                else:
                    logger.debug(f"Processing {operation_type} ({api_request.http_method}) request immediately")
                
                # Execute the API call
                try:
                    logger.debug(f"Executing API request {api_request.request_id}: {api_request.func.__name__}")
                    api_request.processed_at = datetime.now()
                    
                    result = api_request.func(*api_request.args, **api_request.kwargs)
                    api_request.result = result
                    
                    self.total_requests += 1
                    logger.debug(f"API request {api_request.request_id} succeeded")
                    
                except Exception as e:
                    api_request.error = e
                    self.failed_requests += 1
                    logger.error(f"API request {api_request.request_id} failed: {e}")
                
                finally:
                    # Update timing and signal completion
                    self.last_request_time = time.time()
                    api_request.result_event.set()
                    self.request_queue.task_done()
                
            except Exception as e:
                logger.error(f"Unexpected error in API queue worker: {e}")
        
        logger.info("API Request Queue worker thread stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            'is_running': self.is_running,
            'queue_size': self.request_queue.qsize(),
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'success_rate': (self.total_requests - self.failed_requests) / max(1, self.total_requests) * 100,
            'read_delay': self.read_delay,
            'write_delay': self.write_delay,
            'last_request_time': self.last_request_time
        }


# Global instance
_api_queue = None


def get_api_queue() -> ApiRequestQueue:
    """Get the global API request queue instance."""
    global _api_queue
    if _api_queue is None:
        _api_queue = ApiRequestQueue()
    return _api_queue


def queue_api_call(func: Callable, *args, http_method: str = "GET", timeout: float = 30.0, **kwargs) -> Any:
    """
    Convenience function to queue an API call with method-based throttling.
    
    Args:
        func: The function to call
        *args: Function arguments  
        http_method: HTTP method (GET, POST, PUT, DELETE) for smart throttling
        timeout: Maximum time to wait for result (seconds)
        **kwargs: Function keyword arguments
        
    Returns:
        The result of the function call
    """
    api_queue = get_api_queue()
    return api_queue.execute(func, *args, http_method=http_method, timeout=timeout, **kwargs)