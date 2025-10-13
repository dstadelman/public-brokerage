# Three-Thread Architecture Plan

## 🎯 Your Vision (100% Correct!)

```
┌─────────────────────────────────────────────────────────────────┐
│                          MAIN THREAD                            │
│  • User interface (shell.py)                                    │
│  • Start worker threads                                         │
│  • Collect results                                              │
│  • Display to user                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ start_worker()
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        WORKER THREAD                            │
│  • Execute order logic                                          │
│  • Verification loops                                           │
│  • Business logic                                               │
│  • Queue API requests → API thread                             │
│  • Wait for API responses                                       │
│  • Never makes HTTP calls directly!                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ queue_api_request()
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API REQUEST QUEUE                            │
│                    (thread-safe)                                │
│  [Request 1] → [Request 2] → [Request 3] ...                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ dequeue
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   API REQUESTOR THREAD                          │
│  • ONLY makes HTTP requests                                     │
│  • Enforces rate limiting                                       │
│  • Returns results to workers                                   │
│  • Never does business logic!                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS
                              ▼
                    ┌──────────────────┐
                    │  PUBLIC.COM API  │
                    └──────────────────┘
```

## ✅ Why This Is Better

### Current (2 threads) Problems:
1. ❌ Main thread blocked during verification
2. ❌ Direct HTTP calls bypass queue (inconsistent)
3. ❌ Verification can't be parallelized
4. ❌ Confusing threading model

### New (3 threads) Benefits:
1. ✅ **Clean separation of concerns**
   - Main: UI/UX
   - Worker: Business logic
   - API: HTTP requests only

2. ✅ **All API calls go through queue**
   - Consistent rate limiting
   - No direct HTTP calls
   - Single point of control

3. ✅ **Workers can run in parallel**
   - Multiple orders can verify simultaneously
   - Main thread stays responsive
   - Better performance

4. ✅ **Intuitive model**
   - Easy to understand
   - Easy to debug
   - Easy to extend

---

## 📋 Implementation Plan

### Phase 1: Refactor API Queue (No Breaking Changes)

**Current:**
```python
# api_queue.py
def execute(self, func, *args, **kwargs):
    # Queue ANY function
    # Worker executes it
    # Return result
```

**Problem:** This queues entire functions, not just API requests!

**New:**
```python
# api_queue.py
def queue_api_request(self, method, endpoint, data=None, params=None):
    """Queue an API REQUEST (not a function!)"""
    # Queue HTTP request details
    # API thread makes HTTP call
    # Return response
```

**Changes:**
- API queue only handles HTTP requests (method, endpoint, data)
- API thread only makes HTTP calls
- Returns raw `requests.Response` objects

### Phase 2: Create Worker Thread Pool

**New file: `worker_pool.py`**

```python
class WorkerThread(threading.Thread):
    """Worker thread that executes order logic"""
    
    def __init__(self, task_func, *args, **kwargs):
        super().__init__(daemon=True)
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.error = None
        self.completed = threading.Event()
    
    def run(self):
        """Execute the task (order logic)"""
        try:
            # This is where execute_order_with_verification runs!
            self.result = self.task_func(*self.args, **self.kwargs)
        except Exception as e:
            self.error = e
        finally:
            self.completed.set()
    
    def wait(self, timeout=None):
        """Wait for worker to complete"""
        self.completed.wait(timeout)
        if self.error:
            raise self.error
        return self.result


class WorkerPool:
    """Pool of worker threads for order execution"""
    
    def __init__(self, max_workers=5):
        self.max_workers = max_workers
        self.active_workers = {}
        self.lock = threading.Lock()
    
    def submit(self, task_func, *args, **kwargs):
        """Submit a task to a worker thread"""
        worker = WorkerThread(task_func, *args, **kwargs)
        
        with self.lock:
            worker_id = str(uuid.uuid4())[:8]
            self.active_workers[worker_id] = worker
        
        worker.start()
        return worker_id, worker
    
    def get_worker(self, worker_id):
        """Get a worker by ID"""
        with self.lock:
            return self.active_workers.get(worker_id)
```

### Phase 3: Update Order Placement Logic

**Current (in worker):**
```python
def execute_order_with_verification(...):
    # This runs in MAIN thread currently
    order_result = self.execute(order_func, ...)  # Queue and wait
    
    # Verification loop (MAIN thread)
    while not verified:
        result = get_order_direct(...)  # Direct HTTP
        if result:
            return result
        time.sleep(1.0)
```

**New (in worker thread):**
```python
def execute_order_with_verification(...):
    # This runs in WORKER thread
    
    # Step 1: Place order via API queue
    response = api_queue.queue_api_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/order/multileg",
        data=order_request.model_dump()
    )
    order_result = parse_order_response(response)
    order_id = order_result.orderId
    
    # Step 2: Verification loop (WORKER thread)
    verification_start = time.time()
    while time.time() - verification_start < timeout:
        # Queue verification API request
        response = api_queue.queue_api_request(
            method="GET",
            endpoint=f"/userapigateway/trading/{account_id}/order/{order_id}"
        )
        
        if response.status_code == 200:
            order = parse_order(response)
            logger.info(f"Order {order_id} verified!")
            return order_result
        
        time.sleep(1.0)
    
    raise TimeoutError(f"Order {order_id} verification timed out")
```

### Phase 4: Update Main Thread

**Current:**
```python
# walk_limit_engine.py
order_id = place_multileg_order_with_verification(...)  # Blocks main thread!
```

**New:**
```python
# walk_limit_engine.py
worker_id, worker = worker_pool.submit(
    execute_order_with_verification,
    client, account_id, order_request, timeout=60
)

# Main thread continues, not blocked!
# Worker thread does all the work
# API thread handles all HTTP requests

# Later, when you need the result:
result = worker.wait(timeout=60)  # Block only when getting result
```

---

## 🔧 Detailed Implementation Steps

### Step 1: Create Worker Pool Module

**File: `worker_pool.py`**

```python
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
from typing import Callable, Any, Optional, Dict

logger = logging.getLogger(__name__)


class WorkerThread(threading.Thread):
    """
    Worker thread that executes a task function.
    
    The task function can queue API requests through the API queue
    and will receive responses back. The worker never makes direct
    HTTP calls.
    """
    
    def __init__(self, task_func: Callable, task_name: str, *args, **kwargs):
        super().__init__(daemon=True, name=f"Worker-{task_name}")
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
        logger.info(f"[WORKER {self.name}] Starting task: {self.task_name}")
        
        try:
            self.result = self.task_func(*self.args, **self.kwargs)
            logger.info(f"[WORKER {self.name}] Task completed successfully")
        except Exception as e:
            self.error = e
            logger.error(f"[WORKER {self.name}] Task failed: {e}")
        finally:
            self.completed_at = time.time()
            elapsed = self.completed_at - self.started_at
            logger.info(f"[WORKER {self.name}] Task finished in {elapsed:.2f}s")
            self.completed.set()
    
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
    ) -> tuple[str, WorkerThread]:
        """
        Submit a task to be executed in a worker thread.
        
        Args:
            task_func: Function to execute
            task_name: Human-readable task name
            *args: Arguments for task_func
            **kwargs: Keyword arguments for task_func
            
        Returns:
            (worker_id, worker) tuple
            
        Raises:
            RuntimeError: If pool is at max capacity
        """
        with self.lock:
            # Check capacity
            active = sum(1 for w in self.workers.values() if not w.is_done())
            if active >= self.max_workers:
                raise RuntimeError(f"Worker pool at capacity ({self.max_workers} workers)")
            
            # Create worker
            worker_id = str(uuid.uuid4())[:8]
            worker = WorkerThread(task_func, task_name, *args, **kwargs)
            self.workers[worker_id] = worker
            
            logger.info(f"[POOL] Submitting task '{task_name}' to worker {worker_id}")
            worker.start()
            
            return worker_id, worker
    
    def get_worker(self, worker_id: str) -> Optional[WorkerThread]:
        """Get a worker by ID"""
        with self.lock:
            return self.workers.get(worker_id)
    
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


def submit_task(task_func: Callable, task_name: str, *args, **kwargs) -> tuple[str, WorkerThread]:
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
```

### Step 2: Refactor API Queue to Handle HTTP Requests Only

**Update `api_queue.py`:**

```python
class ApiRequest:
    """
    API request details (HTTP request, not a function!)
    """
    def __init__(
        self,
        request_id: str,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        include_auth: bool = True,
        result_event: Optional[threading.Event] = None
    ):
        self.request_id = request_id
        self.method = method
        self.endpoint = endpoint
        self.data = data
        self.params = params
        self.include_auth = include_auth
        self.result_event = result_event or threading.Event()
        self.response: Optional[requests.Response] = None
        self.error: Optional[Exception] = None
        self.queued_at = datetime.now()
        self.processed_at: Optional[datetime] = None


class ApiRequestQueue:
    """
    Thread-safe queue for HTTP API requests.
    
    API Requestor Thread (single thread):
    - Dequeues HTTP requests
    - Makes HTTP calls
    - Returns responses
    - Enforces rate limiting
    
    Does NOT execute arbitrary functions!
    """
    
    def queue_http_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        include_auth: bool = True,
        timeout: float = 30.0
    ) -> requests.Response:
        """
        Queue an HTTP request and wait for response.
        
        This can be called from ANY thread (main, worker, etc.)
        The API thread will process it and return the response.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request body
            params: Query parameters
            include_auth: Whether to include auth token
            timeout: Maximum time to wait
            
        Returns:
            requests.Response object
            
        Raises:
            TimeoutError: If request times out
            Exception: Any HTTP error
        """
        # Start queue if needed
        if not self.is_running:
            self.start()
        
        # Create request
        request_id = str(uuid.uuid4())[:8]
        result_event = threading.Event()
        
        api_request = ApiRequest(
            request_id=request_id,
            method=method,
            endpoint=endpoint,
            data=data,
            params=params,
            include_auth=include_auth,
            result_event=result_event
        )
        
        # Queue it
        self.request_queue.put(api_request)
        thread_name = threading.current_thread().name
        logger.debug(f"[{thread_name}] Queued {method} {endpoint} (ID: {request_id})")
        
        # Wait for response
        if not result_event.wait(timeout):
            raise TimeoutError(f"API request {request_id} timed out after {timeout}s")
        
        # Return response or raise error
        if api_request.error:
            raise api_request.error
        
        return api_request.response
    
    def _process_queue(self):
        """
        API Requestor Thread main loop.
        
        This thread ONLY makes HTTP requests. No business logic!
        """
        logger.info("[API-REQUESTOR] Thread started")
        
        while self.is_running:
            try:
                # Get next request
                try:
                    api_request = self.request_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Apply rate limiting
                if self.delay_between_requests > 0:
                    current_time = time.time()
                    time_since_last = current_time - self.last_request_time
                    if time_since_last < self.delay_between_requests:
                        sleep_time = self.delay_between_requests - time_since_last
                        logger.debug(f"[API-REQUESTOR] Rate limiting: sleep {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                
                # Make HTTP request
                try:
                    logger.debug(f"[API-REQUESTOR] Processing {api_request.method} {api_request.endpoint}")
                    api_request.processed_at = datetime.now()
                    
                    # Call the actual HTTP method (from PublicBrokerageClient)
                    response = self.client._make_request_internal(
                        method=api_request.method,
                        endpoint=api_request.endpoint,
                        data=api_request.data,
                        params=api_request.params,
                        include_auth=api_request.include_auth
                    )
                    
                    api_request.response = response
                    self.total_requests += 1
                    logger.debug(f"[API-REQUESTOR] Request {api_request.request_id} succeeded (status {response.status_code})")
                
                except Exception as e:
                    api_request.error = e
                    self.failed_requests += 1
                    logger.error(f"[API-REQUESTOR] Request {api_request.request_id} failed: {e}")
                
                finally:
                    # Signal completion
                    self.last_request_time = time.time()
                    api_request.result_event.set()
                    self.request_queue.task_done()
            
            except Exception as e:
                logger.error(f"[API-REQUESTOR] Unexpected error: {e}")
        
        logger.info("[API-REQUESTOR] Thread stopped")
```

### Step 3: Update Order Placement to Use Workers

**Update `orders.py`:**

```python
def place_multileg_order_with_verification_worker(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest,
    timeout: float = 60.0
) -> str:
    """
    Place a multileg order with verification.
    
    THIS RUNS IN A WORKER THREAD!
    
    Args:
        client: Authenticated client
        account_id: Account ID
        order_request: Order details
        timeout: Verification timeout
        
    Returns:
        Order ID
    """
    from api_queue import get_api_queue
    import threading
    
    api_queue = get_api_queue()
    thread_name = threading.current_thread().name
    
    logger.info(f"[{thread_name}] Placing multileg order with verification")
    
    # Step 1: Place order via API queue
    logger.info(f"[{thread_name}] Placing order...")
    response = api_queue.queue_http_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/order/multileg",
        data=order_request.model_dump()
    )
    
    # Parse response
    order_response = client._handle_response(response, OrderResponse)
    order_id = order_response.orderId
    logger.info(f"[{thread_name}] Order placed: {order_id}")
    
    # Step 2: Wait for database
    time.sleep(1.0)
    
    # Step 3: Verification loop (runs in worker thread!)
    logger.info(f"[{thread_name}] Starting verification for order {order_id}")
    verification_start = time.time()
    
    while time.time() - verification_start < timeout:
        try:
            # Queue verification request via API queue
            response = api_queue.queue_http_request(
                method="GET",
                endpoint=f"/userapigateway/trading/{account_id}/order/{order_id}"
            )
            
            if response.status_code == 200:
                order = client._handle_response(response, Order)
                logger.info(f"[{thread_name}] Order {order_id} verified! Status: {order.status}")
                return order_id
            
            logger.debug(f"[{thread_name}] Order not found yet (status {response.status_code})")
        
        except Exception as e:
            logger.debug(f"[{thread_name}] Verification attempt failed: {e}")
        
        # Wait before next check
        time.sleep(1.0)
    
    raise TimeoutError(f"Order {order_id} verification timed out after {timeout}s")


def place_multileg_order_with_verification(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest,
    timeout: float = 60.0
) -> str:
    """
    Place a multileg order with verification (user-facing function).
    
    This submits the work to a worker thread and waits for the result.
    
    Args:
        client: Authenticated client
        account_id: Account ID
        order_request: Order details
        timeout: Verification timeout
        
    Returns:
        Order ID
    """
    from worker_pool import submit_task
    
    # Submit to worker pool
    worker_id, worker = submit_task(
        place_multileg_order_with_verification_worker,
        f"place_order_{order_request.symbol}",
        client, account_id, order_request, timeout
    )
    
    # Wait for worker to complete
    return worker.wait(timeout=timeout + 5)  # Extra 5 seconds for overhead
```

---

## 🎯 Migration Strategy

### Option A: Big Bang (Risky)
- Replace everything at once
- High risk of breaking things
- But cleaner result

### Option B: Gradual Migration (Safer) ⭐ RECOMMENDED

**Phase 1: Add worker pool (this week)**
- Create `worker_pool.py`
- Keep current API queue working
- Test worker pool separately

**Phase 2: Refactor API queue (next week)**
- Change `execute()` to `queue_http_request()`
- Update API thread to only do HTTP
- Keep old `execute()` as deprecated

**Phase 3: Update order placement (week after)**
- Update orders.py to use workers
- Test thoroughly
- Remove old code

**Phase 4: Cleanup (final week)**
- Remove deprecated functions
- Remove direct HTTP calls
- Update all documentation

---

## 🧪 Testing Plan

### Test 1: Worker Pool
```python
def test_worker_pool():
    def simple_task(x):
        time.sleep(1)
        return x * 2
    
    worker_id, worker = submit_task(simple_task, "test", 5)
    result = worker.wait()
    assert result == 10
```

### Test 2: API Queue (HTTP only)
```python
def test_api_queue():
    response = api_queue.queue_http_request(
        method="GET",
        endpoint="/userapigateway/accounts"
    )
    assert response.status_code == 200
```

### Test 3: Order with Verification (Worker)
```python
def test_order_placement():
    order_id = place_multileg_order_with_verification(
        client, account_id, order_request, timeout=60
    )
    assert order_id is not None
```

---

## 📊 Performance Comparison

### Current (2 threads):
```
Main thread: [========BLOCKED========] 3-5s
Worker thread: [Work][Idle..................]
```

### New (3 threads):
```
Main thread:   [Submit][Free...............]
Worker thread:        [Work][Verify][Done]
API thread:           [HTTP][HTTP][HTTP]
```

**Benefits:**
- Main thread returns immediately
- Multiple workers can run in parallel
- API thread stays busy (better throughput)

---

## 🚀 Expected Results

### Before (Current):
```
place_order()  →  [BLOCKS 5 seconds]  →  Returns
```

### After (Three Threads):
```
place_order()  →  [Returns immediately]
                 ↓
              [Worker runs in background]
                 ↓
              [Get result when needed]
```

**Async by default, sync when you want it!**

---

## 💡 Key Benefits

1. **Clean Architecture**
   - Each thread has one job
   - Easy to understand
   - Easy to debug

2. **Better Performance**
   - Parallel verification
   - Main thread never blocks
   - API thread stays busy

3. **Consistent API Access**
   - All HTTP goes through queue
   - Proper rate limiting everywhere
   - No special cases

4. **Extensible**
   - Easy to add more workers
   - Easy to add priorities
   - Easy to add cancellation

---

## ✅ Next Steps

1. **Review this plan** - Make sure it makes sense
2. **Create worker_pool.py** - Start with the infrastructure
3. **Test worker pool** - Make sure threading works
4. **Refactor API queue** - Change to HTTP-only
5. **Update one order function** - Test with real orders
6. **Migrate everything** - Once proven to work
7. **Remove old code** - Clean up

---

## 🎉 This Is The Right Architecture!

Your instinct was correct - three threads make much more sense:

- **Main**: UI/coordination
- **Workers**: Business logic
- **API**: HTTP requests only

This is how production systems work! Clean separation of concerns, better performance, easier to understand.

**Let's build it! 🚀**

