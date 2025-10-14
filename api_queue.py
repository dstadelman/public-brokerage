"""
API Request Queue Manager

Centralized queue system for all API calls to prevent concurrency issues
and ensure proper throttling between requests.

THREE-THREAD ARCHITECTURE:
- Main Thread: UI/coordination
- Worker Threads: Business logic, verification loops
- API Requestor Thread: HTTP requests ONLY
"""

import time
import threading
import queue
import logging
from typing import Any, Callable, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import uuid
import requests

logger = logging.getLogger(__name__)


@dataclass
class ApiRequest:
    """Represents a queued API request (OLD - function-based)."""
    request_id: str
    func: Callable
    args: tuple
    kwargs: dict
    result_event: threading.Event
    http_method: str = "GET"  # Kept for backward compatibility
    result: Any = None
    error: Exception = None
    created_at: datetime = None
    processed_at: Optional[datetime] = None
    request_type: str = "FUNCTION"  # FUNCTION (old) vs HTTP (new)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class HttpApiRequest:
    """
    Represents an HTTP API request (NEW - three-thread architecture).
    
    This represents a single HTTP request with method, endpoint, data, etc.
    Workers queue these, API thread processes them immediately (NO DELAYS).
    """
    request_id: str
    method: str
    endpoint: str
    data: Optional[Dict] = None
    params: Optional[Dict] = None
    include_auth: bool = True
    auth_token: Optional[str] = None
    base_url_override: Optional[str] = None
    result_event: Optional[threading.Event] = None
    response: Optional[requests.Response] = None
    error: Optional[Exception] = None
    created_at: datetime = None
    processed_at: Optional[datetime] = None
    request_type: str = "HTTP"

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.result_event is None:
            self.result_event = threading.Event()


class ApiRequestQueue:
    """
    Thread-safe API request queue (NO DELAYS - just HTTP execution).
    
    All API calls should go through this queue to prevent concurrency issues.
    The API thread executes requests as fast as possible with NO throttling.
    
    Business logic (verification loops, delays) belongs in WORKER threads.
    """
    
    def __init__(self):
        """
        Initialize the API request queue with NO delays.
        
        The API thread executes HTTP requests immediately.
        Workers handle business logic like verification delays.
        """
        self.request_queue = queue.Queue()
        self.is_running = False
        self.worker_thread = None
        self.total_requests = 0
        self.failed_requests = 0
        
        logger.info("API Request Queue initialized - NO DELAYS (workers handle timing)")
    
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
        
        OLD FUNCTION-BASED APPROACH - Use queue_http_request() for new code.
        
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
    
    def queue_http_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        include_auth: bool = True,
        auth_token: Optional[str] = None,
        base_url_override: Optional[str] = None,
        timeout: float = 30.0
    ) -> requests.Response:
        """
        Queue an HTTP request (NEW - three-thread architecture).
        
        Workers call this to queue HTTP requests. The API thread processes them.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/orders")
            data: JSON data for request body
            params: Query parameters
            include_auth: Whether to include auth headers
            auth_token: Authorization token (Bearer token)
            base_url_override: Override base URL (for testing)
            timeout: Maximum time to wait for result (seconds)
            
        Returns:
            The HTTP response object
            
        Raises:
            Exception: If the request fails or times out
        """
        if not self.is_running:
            self.start()
        
        # Create HTTP request
        request_id = str(uuid.uuid4())[:8]
        
        http_request = HttpApiRequest(
            request_id=request_id,
            method=method.upper(),
            endpoint=endpoint,
            data=data,
            params=params,
            include_auth=include_auth,
            auth_token=auth_token,
            base_url_override=base_url_override
        )
        
        # Queue the request
        self.request_queue.put(http_request)
        logger.debug(f"Queued HTTP request {request_id}: {method} {endpoint}")
        
        # Wait for result
        if http_request.result_event.wait(timeout=timeout):
            if http_request.error:
                logger.error(f"HTTP request {request_id} failed: {http_request.error}")
                raise http_request.error
            
            logger.debug(f"HTTP request {request_id} completed successfully")
            return http_request.response
        else:
            logger.error(f"HTTP request {request_id} timed out after {timeout}s")
            raise TimeoutError(f"HTTP request timed out after {timeout} seconds")
    
    def _process_queue(self):
        """Worker thread that processes queued API requests (NO DELAYS - immediate execution)."""
        logger.info("API Request Queue worker thread started - NO DELAYS")
        
        while self.is_running:
            try:
                # Get next request (with timeout to check is_running periodically)
                try:
                    api_request = self.request_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Execute immediately - NO THROTTLING, NO DELAYS
                try:
                    api_request.processed_at = datetime.now()
                    
                    if isinstance(api_request, HttpApiRequest):
                        # NEW: HTTP-based request
                        logger.debug(f"Executing HTTP request {api_request.request_id}: {api_request.method} {api_request.endpoint}")
                        api_request.response = self._execute_http_request(api_request)
                        logger.debug(f"HTTP request {api_request.request_id} succeeded")
                    else:
                        # OLD: Function-based request
                        logger.debug(f"Executing API request {api_request.request_id}: {api_request.func.__name__}")
                        api_request.result = api_request.func(*api_request.args, **api_request.kwargs)
                        logger.debug(f"API request {api_request.request_id} succeeded")
                    
                    self.total_requests += 1
                    
                except Exception as e:
                    api_request.error = e
                    self.failed_requests += 1
                    logger.error(f"Request {api_request.request_id} failed: {e}")
                
                finally:
                    # Signal completion immediately
                    api_request.result_event.set()
                    self.request_queue.task_done()
                
            except Exception as e:
                logger.error(f"Unexpected error in API queue worker: {e}")
        
        logger.info("API Request Queue worker thread stopped")
    
    def _execute_http_request(self, http_request: HttpApiRequest) -> requests.Response:
        """
        Execute an HTTP request.
        
        This is where the actual HTTP call happens in the API thread.
        Workers never call this directly - they queue HttpApiRequest objects.
        
        Args:
            http_request: The HTTP request to execute
            
        Returns:
            The HTTP response object
            
        Raises:
            Exception: If the request fails
        """
        # Get base URL
        base_url = http_request.base_url_override or "https://api.public.com"
        url = f"{base_url}{http_request.endpoint}"
        
        # Build headers
        headers = {"Content-Type": "application/json"}
        if http_request.include_auth and http_request.auth_token:
            headers["Authorization"] = f"Bearer {http_request.auth_token}"
        
        # Make the request
        response = requests.request(
            method=http_request.method,
            url=url,
            json=http_request.data,
            params=http_request.params,
            headers=headers
        )
        
        # Raise for HTTP errors
        response.raise_for_status()
        
        return response
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            'is_running': self.is_running,
            'queue_size': self.request_queue.qsize(),
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'success_rate': (self.total_requests - self.failed_requests) / max(1, self.total_requests) * 100
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
    
    OLD FUNCTION-BASED APPROACH - Use queue_http_request() for new code.
    
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


def queue_http_request(
    method: str,
    endpoint: str,
    data: Optional[Dict] = None,
    params: Optional[Dict] = None,
    include_auth: bool = True,
    auth_token: Optional[str] = None,
    base_url_override: Optional[str] = None,
    timeout: float = 30.0
) -> requests.Response:
    """
    Convenience function to queue an HTTP request (NEW - three-thread architecture).
    
    Workers call this to queue HTTP requests. The API thread processes them.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        endpoint: API endpoint (e.g., "/orders")
        data: JSON data for request body
        params: Query parameters
        include_auth: Whether to include auth headers
        auth_token: Authorization token (Bearer token)
        base_url_override: Override base URL (for testing)
        timeout: Maximum time to wait for result (seconds)
        
    Returns:
        The HTTP response object
    """
    api_queue = get_api_queue()
    return api_queue.queue_http_request(
        method=method,
        endpoint=endpoint,
        data=data,
        params=params,
        include_auth=include_auth,
        auth_token=auth_token,
        base_url_override=base_url_override,
        timeout=timeout
    )