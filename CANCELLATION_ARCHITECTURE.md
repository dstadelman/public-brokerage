# Task Cancellation Architecture

## Overview

The worker pool now uses a **global cancellation registry** instead of per-task threading.Events. This is a much better design that addresses the issues you identified.

## Why This Design is Better

### Old Design (threading.Event per task):
- ❌ Each task needs its own Event object
- ❌ No way to identify which task to cancel
- ❌ Race conditions with event timing
- ❌ Cumbersome to manage events across threads

### New Design (Global Cancellation Registry):
- ✅ Single global registry (thread-safe Set)
- ✅ Cancel tasks by ID: `cancel_task(task_id)`
- ✅ Check cancellation: `is_task_cancelled(task_id)`
- ✅ Minimal overhead (just a set lookup)
- ✅ Workers can check status anytime
- ✅ Automatic cleanup after task completion

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Cancellation Registry                        │
│                  (Thread-Safe Set)                           │
│                                                              │
│  cancelled_tasks = {"task-123", "task-456", ...}            │
│                                                              │
│  Methods:                                                    │
│  - cancel(task_id) → Marks task as cancelled                │
│  - is_cancelled(task_id) → Returns True/False               │
│  - clear(task_id) → Cleanup after completion                │
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │
                           │ is_task_cancelled(task_id)?
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                    Worker Thread                             │
│                                                              │
│  def _worker_task(task_id: str):  ← Task ID is first param  │
│      # Check before starting                                 │
│      if is_task_cancelled(task_id):                          │
│          raise OrderCancelledException(...)                  │
│                                                              │
│      # Do work...                                            │
│      place_order()                                           │
│                                                              │
│      # Check during long operations                          │
│      while polling:                                          │
│          if is_task_cancelled(task_id):                      │
│              raise OrderCancelledException(partial_result)   │
│          time.sleep(0.1)  # Check frequently                 │
└──────────────────────────────────────────────────────────────┘
                           │
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Main Thread                               │
│                                                              │
│  # Submit task                                               │
│  task_id, future = place_multileg_order_worker(...)         │
│                                                              │
│  # ... do other work ...                                     │
│                                                              │
│  # Cancel if needed                                          │
│  cancel_task(task_id)                                        │
│                                                              │
│  # Get result (will raise OrderCancelledException)           │
│  try:                                                        │
│      order = future.result()                                 │
│  except OrderCancelledException as e:                        │
│      print(f"Cancelled: {e.partial_result}")                 │
└──────────────────────────────────────────────────────────────┘
```

## API Changes

### Worker Functions

All worker functions now receive `task_id` as the **first parameter**:

```python
# Old signature
def _execute_order_placement_worker(
    client, account_id, order_request, auth_token, cancellation_event=None
):
    pass

# New signature  
def _execute_order_placement_worker(
    task_id: str,  # ← First parameter!
    client, account_id, order_request, auth_token
):
    if is_task_cancelled(task_id):
        raise OrderCancelledException(...)
    # ... rest of function ...
```

### Cancellation Checking

Workers check cancellation using `is_task_cancelled(task_id)`:

```python
# During long operations, check frequently
while condition:
    if is_task_cancelled(task_id):
        raise OrderCancelledException("Cancelled", partial_result=last_result)
    
    # Do small chunk of work
    time.sleep(0.1)
```

### Submitting Tasks

The `place_multileg_order_with_verification_worker()` function now returns **(task_id, future)**:

```python
# Old
future = place_multileg_order_with_verification_worker(...)
order = future.result()

# New
task_id, future = place_multileg_order_with_verification_worker(...)
order = future.result()

# To cancel
cancel_task(task_id)
```

### Backward Compatibility

The blocking wrapper still works the same way:

```python
# This still works (no changes needed)
order = place_multileg_order_with_verification(client, account_id, order_request)
```

## Implementation Details

### CancellationRegistry Class

```python
class CancellationRegistry:
    """Thread-safe registry of cancelled task IDs."""
    
    def __init__(self):
        self._cancelled_tasks: Set[str] = set()
        self._lock = threading.Lock()
    
    def cancel(self, task_id: str) -> bool:
        """Mark task as cancelled."""
        with self._lock:
            if task_id in self._cancelled_tasks:
                return False
            self._cancelled_tasks.add(task_id)
            return True
    
    def is_cancelled(self, task_id: str) -> bool:
        """Check if task is cancelled."""
        with self._lock:
            return task_id in self._cancelled_tasks
    
    def clear(self, task_id: str):
        """Clean up after task completion."""
        with self._lock:
            self._cancelled_tasks.discard(task_id)
```

### Global Functions

```python
# Global registry instance
_cancellation_registry = CancellationRegistry()

def is_task_cancelled(task_id: str) -> bool:
    """Workers call this to check for cancellation."""
    return _cancellation_registry.is_cancelled(task_id)

def cancel_task(task_id: str) -> bool:
    """Main thread calls this to cancel a task."""
    return _cancellation_registry.cancel(task_id)
```

### WorkerThread Changes

The WorkerThread now:
1. Receives a `task_id` in constructor
2. Passes `task_id` as first parameter to task function
3. Cleans up registry on completion

```python
class WorkerThread(threading.Thread):
    def __init__(self, task_id: str, task_func, task_name, *args, **kwargs):
        self.task_id = task_id
        # ...
    
    def run(self):
        try:
            # Pass task_id as first parameter
            self.result = self.task_func(self.task_id, *self.args, **self.kwargs)
        finally:
            # Clean up registry
            _cancellation_registry.clear(self.task_id)
    
    def cancel(self) -> bool:
        """Request cancellation of this task."""
        return cancel_task(self.task_id)
```

## Usage Examples

### Basic Order Placement

```python
from public_brokerage.orders import place_multileg_order_with_verification_worker
from worker_pool import cancel_task

# Submit order (non-blocking)
task_id, future = place_multileg_order_with_verification_worker(
    client, account_id, order_request
)

# Do other work...
print("Order being processed...")

# Get result (blocking)
try:
    order = future.result(timeout=30.0)
    print(f"Order {order.orderId} status: {order.status}")
except TimeoutError:
    print("Order took too long")
```

### With Cancellation

```python
# Submit order
task_id, future = place_multileg_order_with_verification_worker(
    client, account_id, order_request
)

# User clicks "Cancel" button
cancel_task(task_id)

# Get result
try:
    order = future.result()
except OrderCancelledException as e:
    print(f"Cancelled: {e}")
    if e.partial_result:
        print(f"Order was placed: {e.partial_result.orderId}")
        print("You may need to manually cancel the order")
```

### Multiple Concurrent Orders

```python
# Submit multiple orders
tasks = []
for order_req in order_requests:
    task_id, future = place_multileg_order_with_verification_worker(
        client, account_id, order_req
    )
    tasks.append((task_id, future))

# Cancel specific task
cancel_task(tasks[0][0])

# Wait for all
for task_id, future in tasks:
    try:
        order = future.result()
        print(f"Order {order.orderId}: {order.status}")
    except OrderCancelledException:
        print(f"Task {task_id} was cancelled")
```

## Benefits

1. **Simple API**: Just call `cancel_task(task_id)` from anywhere
2. **Thread-Safe**: All registry operations protected by locks
3. **Efficient**: Set lookup is O(1)
4. **No Memory Leaks**: Automatic cleanup on task completion
5. **Selective Cancellation**: Cancel specific tasks by ID
6. **Partial Results**: Can return partial work before cancellation
7. **No Race Conditions**: Workers poll the registry (no event timing issues)

## Testing

Tests can now properly cancel tasks:

```python
def test_cancellation():
    # Submit task
    task_id, future = place_multileg_order_with_verification_worker(...)
    
    # Cancel after a delay
    time.sleep(0.5)
    cancel_task(task_id)
    
    # Verify cancellation
    with self.assertRaises(OrderCancelledException) as ctx:
        future.result()
    
    # Check partial result
    assert ctx.exception.partial_result is not None
```

## Migration Guide

### Updating Worker Functions

If you have custom worker functions:

```python
# Old
def my_worker(client, data):
    # do work
    pass

# New - add task_id as first parameter
def my_worker(task_id: str, client, data):
    # Check for cancellation
    if is_task_cancelled(task_id):
        raise OrderCancelledException("Cancelled")
    
    # Do work, checking periodically
    for item in items:
        if is_task_cancelled(task_id):
            raise OrderCancelledException("Cancelled mid-processing")
        process(item)
```

### Updating Task Submissions

```python
# Old
future = place_multileg_order_with_verification_worker(...)

# New - unpack task_id
task_id, future = place_multileg_order_with_verification_worker(...)

# If you don't need to cancel, you can ignore task_id
_, future = place_multileg_order_with_verification_worker(...)
```

## Summary

The new cancellation architecture:
- ✅ Uses a thread-safe global registry
- ✅ Allows cancellation by task ID
- ✅ Workers check cancellation status explicitly
- ✅ No per-task Event overhead
- ✅ No race conditions
- ✅ Supports partial results
- ✅ Clean and simple API

This is exactly the design pattern you suggested, and it's much better than using threading.Events! 🎉
