"""
Process manager for handling multiple concurrent trading processes.
Provides centralized management, monitoring, and cleanup of background processes.
"""

import threading
import time
import uuid
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging
from concurrent.futures import ThreadPoolExecutor

from config import config

logger = logging.getLogger(__name__)


class ProcessPriority(int, Enum):
    """Priority levels for processes."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ProcessMetrics:
    """Metrics for process performance monitoring."""
    start_time: datetime
    end_time: Optional[datetime] = None
    cpu_time: float = 0.0
    memory_usage: float = 0.0
    api_calls_made: int = 0
    orders_placed: int = 0
    errors_encountered: int = 0


class ProcessManager:
    """Centralized manager for background trading processes."""
    
    def __init__(self, max_concurrent_processes: int = 10):
        self.max_concurrent_processes = max_concurrent_processes
        self.processes: Dict[str, Dict] = {}
        self.process_threads: Dict[str, threading.Thread] = {}
        self.process_stop_events: Dict[str, threading.Event] = {}
        self.process_metrics: Dict[str, ProcessMetrics] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_processes)
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_processes, daemon=True)
        self.monitor_thread.start()
        
        # Load existing processes
        self._load_existing_processes()
    
    def register_process(
        self,
        process_id: str,
        process_type: str,
        process_data: Dict,
        priority: ProcessPriority = ProcessPriority.NORMAL
    ) -> bool:
        """
        Register a new process with the manager.
        
        Args:
            process_id: Unique identifier for the process
            process_type: Type of process (e.g., 'open_call_spread', 'close_call_spread')
            process_data: Process configuration and state data
            priority: Process priority level
            
        Returns:
            True if registered successfully, False otherwise
        """
        with self.lock:
            if len(self.processes) >= self.max_concurrent_processes:
                self.logger.warning(f"Maximum concurrent processes ({self.max_concurrent_processes}) reached")
                return False
            
            if process_id in self.processes:
                self.logger.warning(f"Process {process_id} already exists")
                return False
            
            self.processes[process_id] = {
                'id': process_id,
                'type': process_type,
                'priority': priority,
                'status': 'REGISTERED',
                'data': process_data,
                'created_at': datetime.now(),
                'last_update': datetime.now(),
                'messages': []
            }
            
            self.process_metrics[process_id] = ProcessMetrics(start_time=datetime.now())
            
            # Save to config
            self._save_process_state(process_id)
            
            self.logger.info(f"Registered process {process_id} ({process_type})")
            return True
    
    def start_process(
        self,
        process_id: str,
        process_function: Callable,
        *args,
        **kwargs
    ) -> bool:
        """
        Start a registered process.
        
        Args:
            process_id: Process identifier
            process_function: Function to execute for the process
            *args, **kwargs: Arguments to pass to the process function
            
        Returns:
            True if started successfully, False otherwise
        """
        with self.lock:
            if process_id not in self.processes:
                self.logger.error(f"Process {process_id} not registered")
                return False
            
            if process_id in self.process_threads:
                self.logger.warning(f"Process {process_id} already running")
                return False
            
            # Create stop event
            stop_event = threading.Event()
            self.process_stop_events[process_id] = stop_event
            
            # Create and start thread
            def process_wrapper():
                try:
                    self._update_process_status(process_id, 'STARTING')
                    process_function(process_id, stop_event, *args, **kwargs)
                except Exception as e:
                    self.logger.error(f"Process {process_id} failed: {e}")
                    self._update_process_status(process_id, 'FAILED')
                    self._add_process_message(process_id, f"Process failed: {str(e)}")
                finally:
                    self._cleanup_process_thread(process_id)
            
            thread = threading.Thread(target=process_wrapper, daemon=True)
            self.process_threads[process_id] = thread
            thread.start()
            
            self._update_process_status(process_id, 'RUNNING')
            self.logger.info(f"Started process {process_id}")
            return True
    
    def stop_process(self, process_id: str, timeout: float = 30.0) -> bool:
        """
        Stop a running process.
        
        Args:
            process_id: Process identifier
            timeout: Maximum time to wait for graceful shutdown
            
        Returns:
            True if stopped successfully, False otherwise
        """
        with self.lock:
            if process_id not in self.process_stop_events:
                self.logger.warning(f"Process {process_id} not running")
                return False
            
            # Signal stop
            self.process_stop_events[process_id].set()
            self._update_process_status(process_id, 'STOPPING')
            self._add_process_message(process_id, "Stop signal sent")
            
            # Wait for thread to finish
            if process_id in self.process_threads:
                thread = self.process_threads[process_id]
                thread.join(timeout=timeout)
                
                if thread.is_alive():
                    self.logger.warning(f"Process {process_id} did not stop gracefully within {timeout}s")
                    self._update_process_status(process_id, 'FORCE_STOPPED')
                    return False
            
            self._update_process_status(process_id, 'STOPPED')
            self.logger.info(f"Stopped process {process_id}")
            return True
    
    def stop_all_processes(self, timeout: float = 30.0) -> int:
        """
        Stop all running processes.
        
        Args:
            timeout: Maximum time to wait for each process
            
        Returns:
            Number of processes stopped
        """
        stopped_count = 0
        process_ids = list(self.process_threads.keys())
        
        for process_id in process_ids:
            if self.stop_process(process_id, timeout):
                stopped_count += 1
        
        return stopped_count
    
    def get_process_status(self, process_id: str) -> Optional[Dict]:
        """Get detailed status of a specific process."""
        with self.lock:
            if process_id not in self.processes:
                return None
            
            process = self.processes[process_id].copy()
            
            # Add runtime metrics
            if process_id in self.process_metrics:
                metrics = self.process_metrics[process_id]
                process['metrics'] = {
                    'runtime': self._calculate_runtime(metrics),
                    'api_calls': metrics.api_calls_made,
                    'orders_placed': metrics.orders_placed,
                    'errors': metrics.errors_encountered
                }
            
            # Add thread status
            process['is_running'] = process_id in self.process_threads
            
            return process
    
    def get_all_processes(self) -> Dict[str, Dict]:
        """Get status of all processes."""
        with self.lock:
            return {pid: self.get_process_status(pid) for pid in self.processes.keys()}
    
    def get_running_processes(self) -> Dict[str, Dict]:
        """Get only currently running processes."""
        all_processes = self.get_all_processes()
        return {
            pid: process for pid, process in all_processes.items()
            if process and process.get('is_running', False)
        }
    
    def cleanup_finished_processes(self, max_age_hours: int = 24) -> int:
        """
        Clean up old finished processes.
        
        Args:
            max_age_hours: Maximum age for finished processes to keep
            
        Returns:
            Number of processes cleaned up
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        with self.lock:
            finished_processes = []
            
            for process_id, process in self.processes.items():
                if (process['status'] in ['COMPLETED', 'FAILED', 'STOPPED', 'CANCELLED'] and
                    process['last_update'] < cutoff_time and
                    process_id not in self.process_threads):
                    finished_processes.append(process_id)
            
            for process_id in finished_processes:
                self._remove_process(process_id)
                cleaned_count += 1
        
        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} old processes")
        
        return cleaned_count
    
    def update_process_metrics(
        self,
        process_id: str,
        api_calls: int = 0,
        orders_placed: int = 0,
        errors: int = 0
    ) -> None:
        """Update metrics for a process."""
        if process_id in self.process_metrics:
            metrics = self.process_metrics[process_id]
            metrics.api_calls_made += api_calls
            metrics.orders_placed += orders_placed
            metrics.errors_encountered += errors
    
    def add_process_message(self, process_id: str, message: str) -> None:
        """Add a message to a process log."""
        self._add_process_message(process_id, message)
    
    def _update_process_status(self, process_id: str, status: str) -> None:
        """Update process status."""
        with self.lock:
            if process_id in self.processes:
                self.processes[process_id]['status'] = status
                self.processes[process_id]['last_update'] = datetime.now()
                self._save_process_state(process_id)
    
    def _add_process_message(self, process_id: str, message: str) -> None:
        """Add a timestamped message to process log."""
        with self.lock:
            if process_id in self.processes:
                timestamp = datetime.now().strftime("%H:%M:%S")
                formatted_message = f"[{timestamp}] {message}"
                self.processes[process_id]['messages'].append(formatted_message)
                
                # Keep only last 100 messages
                if len(self.processes[process_id]['messages']) > 100:
                    self.processes[process_id]['messages'] = self.processes[process_id]['messages'][-100:]
                
                self.processes[process_id]['last_update'] = datetime.now()
                self._save_process_state(process_id)
    
    def _cleanup_process_thread(self, process_id: str) -> None:
        """Clean up thread resources for a process."""
        with self.lock:
            if process_id in self.process_threads:
                del self.process_threads[process_id]
            
            if process_id in self.process_stop_events:
                del self.process_stop_events[process_id]
            
            # Mark end time in metrics
            if process_id in self.process_metrics:
                self.process_metrics[process_id].end_time = datetime.now()
    
    def _remove_process(self, process_id: str) -> None:
        """Completely remove a process and its data."""
        with self.lock:
            if process_id in self.processes:
                del self.processes[process_id]
            
            if process_id in self.process_metrics:
                del self.process_metrics[process_id]
            
            # Remove from config
            config.remove_background_process(process_id)
    
    def _save_process_state(self, process_id: str) -> None:
        """Save process state to persistent config."""
        if process_id in self.processes:
            process_data = self.processes[process_id].copy()
            # Convert datetime objects to ISO strings for JSON serialization
            process_data['created_at'] = process_data['created_at'].isoformat()
            process_data['last_update'] = process_data['last_update'].isoformat()
            process_data['priority'] = process_data['priority'].value
            
            config.add_background_process(process_id, process_data)
    
    def _load_existing_processes(self) -> None:
        """Load existing processes from persistent config."""
        try:
            saved_processes = config.get_background_processes()
            
            for process_id, process_data in saved_processes.items():
                # Convert ISO strings back to datetime objects
                if 'created_at' in process_data:
                    process_data['created_at'] = datetime.fromisoformat(process_data['created_at'])
                if 'last_update' in process_data:
                    process_data['last_update'] = datetime.fromisoformat(process_data['last_update'])
                if 'priority' in process_data:
                    process_data['priority'] = ProcessPriority(process_data['priority'])
                
                # Mark stale running processes as stopped
                if process_data.get('status') in ['RUNNING', 'STARTING', 'STOPPING']:
                    process_data['status'] = 'STOPPED'
                    process_data['last_update'] = datetime.now()
                    self._add_process_message(process_id, "Process marked as stopped due to restart")
                
                self.processes[process_id] = process_data
                self.process_metrics[process_id] = ProcessMetrics(
                    start_time=process_data['created_at']
                )
            
            self.logger.info(f"Loaded {len(saved_processes)} existing processes")
        
        except Exception as e:
            self.logger.error(f"Error loading existing processes: {e}")
    
    def _monitor_processes(self) -> None:
        """Background thread to monitor process health and cleanup."""
        while True:
            try:
                # Check for dead threads
                dead_threads = []
                with self.lock:
                    for process_id, thread in self.process_threads.items():
                        if not thread.is_alive():
                            dead_threads.append(process_id)
                
                # Clean up dead threads
                for process_id in dead_threads:
                    self._cleanup_process_thread(process_id)
                    if process_id in self.processes:
                        if self.processes[process_id]['status'] == 'RUNNING':
                            self._update_process_status(process_id, 'COMPLETED')
                
                # Periodic cleanup of old processes
                if datetime.now().minute == 0:  # Once per hour
                    self.cleanup_finished_processes()
                
                time.sleep(30)  # Check every 30 seconds
            
            except Exception as e:
                self.logger.error(f"Error in process monitor: {e}")
                time.sleep(60)  # Wait longer on error
    
    def _calculate_runtime(self, metrics: ProcessMetrics) -> str:
        """Calculate human-readable runtime for a process."""
        end_time = metrics.end_time or datetime.now()
        runtime = end_time - metrics.start_time
        
        total_seconds = int(runtime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def get_system_stats(self) -> Dict:
        """Get overall system statistics."""
        with self.lock:
            total_processes = len(self.processes)
            running_processes = len(self.process_threads)
            
            status_counts = {}
            for process in self.processes.values():
                status = process['status']
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                'total_processes': total_processes,
                'running_processes': running_processes,
                'max_concurrent': self.max_concurrent_processes,
                'status_breakdown': status_counts,
                'memory_usage': f"{len(self.processes)} processes in memory"
            }
    
    def shutdown(self, timeout: float = 60.0) -> None:
        """Gracefully shutdown the process manager."""
        self.logger.info("Shutting down process manager...")
        
        # Stop all processes
        stopped = self.stop_all_processes(timeout)
        self.logger.info(f"Stopped {stopped} processes")
        
        # Save final state
        for process_id in self.processes.keys():
            self._save_process_state(process_id)
        
        # Shutdown executor
        self.executor.shutdown(wait=True, timeout=timeout)
        
        self.logger.info("Process manager shutdown complete")


# Global process manager instance
process_manager = ProcessManager()
