"""Test worker pool implementation"""
import time
import logging
from worker_pool import submit_task, get_worker_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def simple_task(task_id, x, sleep_time=1):
    """Simple task for testing"""
    print(f"Task {task_id} started with x={x}")
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
    
    def failing_task(task_id):
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
