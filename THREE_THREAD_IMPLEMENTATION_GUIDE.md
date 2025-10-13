# Three-Thread Architecture - Implementation Guide

## 🎯 Goal

Transform the current 2-thread architecture into a clean 3-thread architecture:
- **Main Thread**: UI/UX only
- **Worker Threads**: Business logic (can have multiple!)
- **API Requestor Thread**: All HTTP requests (single thread)

---

## 📋 Implementation Steps

### Phase 1: Create Worker Pool Infrastructure ⭐ START HERE

**Estimated time: 1-2 hours**

#### Step 1.1: Create `worker_pool.py`

Copy the complete implementation from `THREE_THREAD_ARCHITECTURE_PLAN.md` into a new file:

```bash
# Create the file
touch worker_pool.py
```

Then paste the complete `WorkerThread` and `WorkerPool` classes.

#### Step 1.2: Test Worker Pool Independently

Create `test_worker_pool.py`:

```python
import time
import logging
from worker_pool import submit_task, get_worker_pool

logging.basicConfig(level=logging.INFO)

def simple_task(x, sleep_time=1):
    """Simple task for testing"""
    print(f"Task started with x={x}")
    time.sleep(sleep_time)
    result = x * 2
    print(f"Task completed with result={result}")
    return result

def test_single_worker():
    """Test single worker"""
    print("\n=== Test 1: Single Worker ===")
    worker_id, worker = submit_task(simple_task, "test1", 5, sleep_time=1)
    print(f"Submitted worker {worker_id}")
    
    result = worker.wait()
    print(f"Result: {result}")
    assert result == 10
    print("✅ Test 1 passed!")

def test_multiple_workers():
    """Test multiple workers in parallel"""
    print("\n=== Test 2: Multiple Workers ===")
    
    workers = []
    for i in range(3):
        worker_id, worker = submit_task(simple_task, f"test{i}", i, sleep_time=1)
        workers.append((worker_id, worker))
        print(f"Submitted worker {worker_id}")
    
    results = []
    for worker_id, worker in workers:
        result = worker.wait()
        results.append(result)
        print(f"Worker {worker_id} result: {result}")
    
    assert results == [0, 2, 4]
    print("✅ Test 2 passed!")

def test_worker_error():
    """Test worker error handling"""
    print("\n=== Test 3: Worker Error ===")
    
    def failing_task():
        raise ValueError("Test error")
    
    worker_id, worker = submit_task(failing_task, "error_test")
    
    try:
        worker.wait()
        assert False, "Should have raised exception"
    except ValueError as e:
        print(f"Caught expected error: {e}")
        print("✅ Test 3 passed!")

def test_worker_stats():
    """Test worker pool statistics"""
    print("\n=== Test 4: Worker Stats ===")
    
    pool = get_worker_pool()
    stats = pool.get_stats()
    print(f"Stats: {stats}")
    print("✅ Test 4 passed!")

if __name__ == "__main__":
    test_single_worker()
    test_multiple_workers()
    test_worker_error()
    test_worker_stats()
    print("\n🎉 All tests passed!")
```

Run tests:
```bash
python test_worker_pool.py
```

Expected output:
```
=== Test 1: Single Worker ===
Submitted worker abc123
Task started with x=5
Task completed with result=10
Result: 10
✅ Test 1 passed!

=== Test 2: Multiple Workers ===
Submitted worker def456
Submitted worker ghi789
Submitted worker jkl012
Task started with x=0
Task started with x=1
Task started with x=2
Task completed with result=0
Task completed with result=2
Task completed with result=4
✅ Test 2 passed!

... etc ...
```

---

### Phase 2: Refactor API Queue to HTTP-Only

**Estimated time: 2-3 hours**

#### Step 2.1: Update `api_queue.py` - Add HTTP Request Method

Add the new `queue_http_request()` method while keeping old `execute()` method:

```python
# In ApiRequestQueue class

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
    
    This is the NEW method that only handles HTTP requests.
    It can be called from ANY thread (main, worker, etc.)
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint (e.g., "/userapigateway/trading/{account_id}/order")
        data: Request body (for POST/PUT)
        params: Query parameters
        include_auth: Whether to include auth token
        timeout: Maximum time to wait for response
        
    Returns:
        requests.Response object
        
    Raises:
        TimeoutError: If request times out
        Exception: Any HTTP error
    """
    if not self.is_running:
        self.start()
    
    thread_name = threading.current_thread().name
    request_id = str(uuid.uuid4())[:8]
    result_event = threading.Event()
    
    # Create HTTP request object
    api_request = HttpApiRequest(  # New class!
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
    logger.debug(f"[{thread_name}] Queued {method} {endpoint} (ID: {request_id})")
    
    # Wait for response
    if not result_event.wait(timeout):
        raise TimeoutError(f"HTTP request {request_id} ({method} {endpoint}) timed out after {timeout}s")
    
    # Return response or raise error
    if api_request.error:
        raise api_request.error
    
    return api_request.response
```

#### Step 2.2: Create New Request Class

Add a new class for HTTP requests:

```python
class HttpApiRequest:
    """
    HTTP API request (not a function call!).
    
    This represents a single HTTP request with method, endpoint, data, etc.
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
        self.request_type = "HTTP"  # vs "FUNCTION" for old style
```

#### Step 2.3: Update Worker Thread to Handle Both Types

Update `_process_queue()` to handle both old function-based requests and new HTTP requests:

```python
def _process_queue(self):
    """Worker thread that processes queued requests"""
    logger.info("[API-REQUESTOR] Thread started")
    
    while self.is_running:
        try:
            try:
                api_request = self.request_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            # Apply rate limiting
            current_time = time.time()
            if self.delay_between_requests > 0:
                time_since_last = current_time - self.last_request_time
                if time_since_last < self.delay_between_requests:
                    sleep_time = self.delay_between_requests - time_since_last
                    logger.debug(f"[API-REQUESTOR] Rate limiting: sleep {sleep_time:.2f}s")
                    time.sleep(sleep_time)
            
            # Process request based on type
            try:
                api_request.processed_at = datetime.now()
                
                if isinstance(api_request, HttpApiRequest):
                    # NEW: Handle HTTP request
                    logger.debug(f"[API-REQUESTOR] Processing HTTP {api_request.method} {api_request.endpoint}")
                    
                    response = self.client._make_request_internal(
                        method=api_request.method,
                        endpoint=api_request.endpoint,
                        data=api_request.data,
                        params=api_request.params,
                        include_auth=api_request.include_auth
                    )
                    
                    api_request.response = response
                    logger.debug(f"[API-REQUESTOR] HTTP request succeeded (status {response.status_code})")
                
                else:
                    # OLD: Handle function call (deprecated)
                    logger.warning(f"[API-REQUESTOR] Processing deprecated function call: {api_request.func.__name__}")
                    result = api_request.func(*api_request.args, **api_request.kwargs)
                    api_request.result = result
                
                self.total_requests += 1
            
            except Exception as e:
                api_request.error = e
                self.failed_requests += 1
                logger.error(f"[API-REQUESTOR] Request {api_request.request_id} failed: {e}")
            
            finally:
                self.last_request_time = time.time()
                api_request.result_event.set()
                self.request_queue.task_done()
        
        except Exception as e:
            logger.error(f"[API-REQUESTOR] Unexpected error: {e}")
    
    logger.info("[API-REQUESTOR] Thread stopped")
```

#### Step 2.4: Test HTTP Request Method

Create `test_api_queue_http.py`:

```python
from api_queue import get_api_queue
from public_brokerage.client import PublicBrokerageClient
import config

client = PublicBrokerageClient()
client.authenticate()

api_queue = get_api_queue()
api_queue.client = client  # Set client for _make_request_internal

# Test GET request
print("Testing GET /accounts...")
response = api_queue.queue_http_request(
    method="GET",
    endpoint="/userapigateway/accounts"
)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200]}")

print("\n✅ HTTP queue test passed!")
```

---

### Phase 3: Create Worker-Based Order Placement

**Estimated time: 2-3 hours**

#### Step 3.1: Create New Order Function (Worker Version)

Add to `orders.py`:

```python
def place_multileg_order_with_verification_worker(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest,
    timeout: float = 60.0
) -> str:
    """
    Place multileg order with verification.
    
    THIS RUNS IN A WORKER THREAD!
    All API calls go through the queue.
    
    Args:
        client: Authenticated client
        account_id: Account ID
        order_request: Order details
        timeout: Verification timeout
        
    Returns:
        Order ID
    """
    import threading
    from api_queue import get_api_queue
    
    thread_name = threading.current_thread().name
    api_queue = get_api_queue()
    
    logger.info(f"[{thread_name}] Placing multileg order with verification")
    
    # Step 1: Place order via API queue
    logger.info(f"[{thread_name}] Placing order...")
    response = api_queue.queue_http_request(
        method="POST",
        endpoint=f"/userapigateway/trading/{account_id}/order/multileg",
        data=order_request.model_dump(),
        timeout=30.0
    )
    
    # Parse response
    if response.status_code != 200:
        raise Exception(f"Order placement failed: {response.status_code} {response.text}")
    
    order_response = client._handle_response(response, OrderResponse)
    order_id = order_response.orderId
    logger.info(f"[{thread_name}] Order placed: {order_id}")
    
    # Step 2: Wait for database to settle
    time.sleep(1.0)
    
    # Step 3: Verification loop (runs in WORKER thread!)
    logger.info(f"[{thread_name}] Starting verification for order {order_id}")
    verification_start = time.time()
    check_count = 0
    
    while time.time() - verification_start < timeout:
        check_count += 1
        try:
            elapsed = time.time() - verification_start
            logger.info(f"[{thread_name}] Verification check #{check_count} for order {order_id} (elapsed: {elapsed:.1f}s)")
            
            # Queue verification request via API queue
            response = api_queue.queue_http_request(
                method="GET",
                endpoint=f"/userapigateway/trading/{account_id}/order/{order_id}",
                timeout=10.0
            )
            
            if response.status_code == 200:
                order = client._handle_response(response, Order)
                logger.info(f"[{thread_name}] ✅ Order {order_id} verified! Status: {order.status}")
                return order_id
            
            logger.debug(f"[{thread_name}] Order not found yet (status {response.status_code})")
        
        except Exception as e:
            logger.debug(f"[{thread_name}] Verification attempt failed: {e}")
        
        # Wait before next check
        time.sleep(1.0)
    
    raise TimeoutError(f"Order {order_id} verification timed out after {timeout}s ({check_count} checks)")
```

#### Step 3.2: Create User-Facing Function

Add wrapper function that uses worker pool:

```python
def place_multileg_order_with_verification(
    client: PublicBrokerageClient,
    account_id: str,
    order_request: OrderRequest,
    timeout: float = 60.0,
    async_mode: bool = False
) -> Union[str, tuple]:
    """
    Place a multileg order with verification.
    
    This is the user-facing function that submits work to a worker thread.
    
    Args:
        client: Authenticated client
        account_id: Account ID
        order_request: Order details
        timeout: Verification timeout
        async_mode: If True, return (worker_id, worker) immediately
                    If False, wait for result (synchronous)
        
    Returns:
        If async_mode=False: Order ID (blocks until verified)
        If async_mode=True: (worker_id, worker) tuple (returns immediately)
    """
    from worker_pool import submit_task
    
    # Submit to worker pool
    worker_id, worker = submit_task(
        place_multileg_order_with_verification_worker,
        f"place_order_{order_request.symbol}",
        client, account_id, order_request, timeout
    )
    
    if async_mode:
        # Return immediately (async)
        return worker_id, worker
    else:
        # Wait for result (sync)
        return worker.wait(timeout=timeout + 5)
```

#### Step 3.3: Test New Order Function

Create `test_order_worker.py`:

```python
from public_brokerage.client import PublicBrokerageClient
from public_brokerage.orders import place_multileg_order_with_verification
from public_brokerage.models.order import OrderRequest, OrderLeg
import config
import logging

logging.basicConfig(level=logging.INFO)

client = PublicBrokerageClient()
client.authenticate()

account_id = config.get_default_account()

# Create test order
order_request = OrderRequest(
    symbol="SPY",
    legs=[
        OrderLeg(
            symbol="SPY251017C00590000",
            action="SELL",
            quantity=1,
            position_effect="OPEN"
        ),
        OrderLeg(
            symbol="SPY251121C00595000",
            action="BUY",
            quantity=1,
            position_effect="OPEN"
        )
    ],
    duration="DAY",
    order_type="NET_CREDIT",
    limit_price=0.50
)

print("Testing synchronous mode...")
order_id = place_multileg_order_with_verification(
    client,
    account_id,
    order_request,
    timeout=60,
    async_mode=False  # Block until verified
)
print(f"✅ Order placed: {order_id}")

print("\nTesting asynchronous mode...")
worker_id, worker = place_multileg_order_with_verification(
    client,
    account_id,
    order_request,
    timeout=60,
    async_mode=True  # Return immediately
)
print(f"✅ Worker submitted: {worker_id}")
print("Main thread is free! Can do other things...")
# ... do other stuff ...
print("Now getting result...")
order_id = worker.wait()
print(f"✅ Order placed: {order_id}")
```

---

### Phase 4: Update Walk Limit Engine

**Estimated time: 1-2 hours**

#### Step 4.1: Update Walk Limit Engine to Use Workers

Update `walk_limit_engine.py`:

```python
from worker_pool import get_worker_pool

class WalkLimitEngine:
    def __init__(self, client):
        self.client = client
        self.processes = {}
        self.workers = {}  # NEW: Track worker threads
        self.worker_pool = get_worker_pool()
    
    def start_open_call_spread_process(
        self,
        symbol: str,
        short_expiration: str,
        short_strike: float,
        long_expiration: str,
        long_strike: float,
        quantity: int,
        account_id: str,
        max_wait_time: float = 60.0,
        execute_mode: bool = False
    ) -> str:
        """Start process (now uses worker threads!)"""
        
        process_id = str(uuid.uuid4())[:8]
        
        # Create process state
        process = {
            'process_id': process_id,
            'type': 'OPEN_CALL_SPREAD',
            'symbol': symbol,
            'status': 'PREFLIGHT',
            # ... other fields ...
        }
        
        self.processes[process_id] = process
        
        if execute_mode:
            # Submit to worker pool (async!)
            worker_id, worker = place_multileg_order_with_verification(
                self.client,
                account_id,
                order_request,
                timeout=max_wait_time,
                async_mode=True  # Don't block!
            )
            
            # Store worker
            self.workers[process_id] = worker
            process['worker_id'] = worker_id
            process['status'] = 'EXECUTING'
            
            logger.info(f"Process {process_id} submitted to worker {worker_id}")
        
        return process_id
    
    def get_process_status(self, process_id: str) -> dict:
        """Get process status (check worker if still running)"""
        process = self.processes.get(process_id)
        if not process:
            return None
        
        # Check worker status
        worker = self.workers.get(process_id)
        if worker:
            if worker.is_done():
                # Worker completed!
                try:
                    result = worker.wait(timeout=0.1)
                    process['status'] = 'FILLED'
                    process['order_id'] = result
                except Exception as e:
                    process['status'] = 'FAILED'
                    process['error'] = str(e)
            else:
                # Still running
                process['status'] = 'EXECUTING'
        
        return process
```

---

### Phase 5: Testing & Migration

**Estimated time: 2-3 hours**

#### Step 5.1: Side-by-Side Testing

Test both old and new implementations:

```python
# Test old implementation (2 threads)
order_id_old = place_multileg_order_with_verification_old(...)

# Test new implementation (3 threads)
order_id_new = place_multileg_order_with_verification(...)

# Compare results
assert order_id_old and order_id_new
```

#### Step 5.2: Performance Testing

Test parallel execution:

```python
import time

# Test sequential (old way)
start = time.time()
order1 = place_order_old(...)
order2 = place_order_old(...)
order3 = place_order_old(...)
sequential_time = time.time() - start
print(f"Sequential: {sequential_time:.2f}s")

# Test parallel (new way)
start = time.time()
w1_id, w1 = place_order_new(..., async_mode=True)
w2_id, w2 = place_order_new(..., async_mode=True)
w3_id, w3 = place_order_new(..., async_mode=True)
order1 = w1.wait()
order2 = w2.wait()
order3 = w3.wait()
parallel_time = time.time() - start
print(f"Parallel: {parallel_time:.2f}s")

print(f"Speedup: {sequential_time / parallel_time:.2f}x")
```

#### Step 5.3: Gradual Migration

1. **Week 1**: Keep both implementations, test new one
2. **Week 2**: Use new implementation for non-critical operations
3. **Week 3**: Switch critical operations to new implementation
4. **Week 4**: Remove old implementation

---

## ✅ Checklist

### Phase 1: Worker Pool
- [ ] Create `worker_pool.py`
- [ ] Implement `WorkerThread` class
- [ ] Implement `WorkerPool` class
- [ ] Create `test_worker_pool.py`
- [ ] All tests pass

### Phase 2: API Queue Refactor
- [ ] Add `HttpApiRequest` class to `api_queue.py`
- [ ] Add `queue_http_request()` method
- [ ] Update `_process_queue()` to handle both types
- [ ] Create `test_api_queue_http.py`
- [ ] Test HTTP queueing

### Phase 3: Worker-Based Orders
- [ ] Create `place_multileg_order_with_verification_worker()`
- [ ] Update `place_multileg_order_with_verification()`
- [ ] Add `async_mode` parameter
- [ ] Create `test_order_worker.py`
- [ ] Test both sync and async modes

### Phase 4: Update Walk Limit Engine
- [ ] Add worker pool support
- [ ] Update `start_open_call_spread_process()`
- [ ] Update `get_process_status()`
- [ ] Test with real orders

### Phase 5: Testing & Migration
- [ ] Side-by-side testing
- [ ] Performance testing
- [ ] Gradual migration plan
- [ ] Remove old code
- [ ] Update documentation

---

## 🎯 Success Criteria

When done, you should have:

1. ✅ **Three distinct threads**
   - Main: UI only
   - Workers: Business logic
   - API: HTTP only

2. ✅ **All API calls through queue**
   - No direct HTTP calls
   - Consistent rate limiting
   - Single point of control

3. ✅ **Parallel execution**
   - Multiple orders verify simultaneously
   - Main thread never blocked
   - Better performance

4. ✅ **Clean code**
   - Easy to understand
   - Easy to debug
   - Easy to extend

---

## 📚 Documentation Updates Needed

After implementation:

1. Update `API_QUEUE_THREADING_ARCHITECTURE.md`
2. Update `API_QUEUE_DIAGRAMS.md`
3. Create `WORKER_POOL_GUIDE.md`
4. Update `README.md` with new architecture
5. Update `TROUBLESHOOTING.md` with new debugging tips

---

## 🚀 Let's Build It!

This is the right architecture. Clean, scalable, maintainable.

**Start with Phase 1 (worker pool) - it's independent and can be tested separately.**

