"""Execution worker pool for formula evaluation."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from queue import Queue, Empty
import threading
import time
import structlog

from core.formula_engine.models import ExecutionTask
from infra.db_connection import db

logger = structlog.get_logger()


class ExecutionWorker:
    """Worker pool for executing formulas asynchronously."""
    
    def __init__(self, worker_count: int = 4, batch_size: int = 100, batch_interval_ms: int = 50):
        self.worker_count = worker_count
        self.batch_size = batch_size
        self.batch_interval_ms = batch_interval_ms
        
        self._task_queue: Queue = Queue()
        self._result_buffer: List[Dict] = []
        self._buffer_lock = threading.Lock()
        self._workers: List[threading.Thread] = []
        self._running = False
        self._last_flush = time.time()
        
        self.logger = logger.bind(component="execution_worker")
    
    def start(self) -> None:
        """Start worker threads."""
        if self._running:
            return
        
        self._running = True
        
        # Start worker threads
        for i in range(self.worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"FormulaWorker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        # Start flush thread
        flush_thread = threading.Thread(
            target=self._flush_loop,
            name="FormulaFlusher",
            daemon=True
        )
        flush_thread.start()
        self._workers.append(flush_thread)
        
        self.logger.info("execution_workers_started", worker_count=self.worker_count)
    
    def stop(self) -> None:
        """Stop worker threads."""
        self._running = False
        
        # Flush remaining results
        self._flush_results()
        
        # Wait for workers
        for worker in self._workers:
            worker.join(timeout=2)
        
        self.logger.info("execution_workers_stopped")
    
    def submit_task(self, task: ExecutionTask) -> None:
        """Submit execution task to queue."""
        self._task_queue.put(task)
    
    def _worker_loop(self) -> None:
        """Worker thread main loop."""
        while self._running:
            try:
                # Get task with timeout
                task = self._task_queue.get(timeout=0.1)
                
                # Process task
                self._process_task(task)
                
                self._task_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                self.logger.error("worker_error", error=str(e))
    
    def _process_task(self, task: ExecutionTask) -> None:
        """Process a single execution task."""
        # This will be called by formula_engine with actual execution logic
        # For now, just log
        self.logger.debug("task_processed", formula_id=task.formula_id)
    
    def add_result(self, formula_id: int, result_value: float, 
                   execution_time_ms: float, trigger_tag_id: Optional[int] = None) -> None:
        """Add execution result to buffer."""
        result = {
            "formula_id": formula_id,
            "result_value": result_value,
            "calculated_at": datetime.utcnow(),
            "execution_time_ms": execution_time_ms,
            "trigger_tag_id": trigger_tag_id
        }
        
        with self._buffer_lock:
            self._result_buffer.append(result)
            
            # Flush if batch size reached
            if len(self._result_buffer) >= self.batch_size:
                self._flush_results()
    
    def _flush_loop(self) -> None:
        """Periodic flush loop."""
        while self._running:
            time.sleep(self.batch_interval_ms / 1000.0)
            
            # Check if flush interval elapsed
            elapsed_ms = (time.time() - self._last_flush) * 1000
            if elapsed_ms >= self.batch_interval_ms:
                with self._buffer_lock:
                    if self._result_buffer:
                        self._flush_results()
    
    def _flush_results(self) -> None:
        """Flush result buffer to database."""
        if not self._result_buffer:
            return
        
        try:
            # Copy buffer
            results = self._result_buffer.copy()
            self._result_buffer.clear()
            self._last_flush = time.time()
            
            # Batch insert
            with db.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO CalculatedTags 
                    (formula_id, result_value, calculated_at, execution_time_ms, trigger_tag_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            r["formula_id"],
                            r["result_value"],
                            r["calculated_at"],
                            r["execution_time_ms"],
                            r["trigger_tag_id"]
                        )
                        for r in results
                    ]
                )
                db.commit()
            
            self.logger.info("results_flushed", count=len(results))
            
        except Exception as e:
            self.logger.error("flush_error", error=str(e), count=len(results))
            # Re-add to buffer on error
            with self._buffer_lock:
                self._result_buffer.extend(results)
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self._task_queue.qsize()
    
    def get_buffer_size(self) -> int:
        """Get current buffer size."""
        with self._buffer_lock:
            return len(self._result_buffer)


# Global execution worker instance
execution_worker = ExecutionWorker()
