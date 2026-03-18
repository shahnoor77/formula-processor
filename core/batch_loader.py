"""Batch loader for processing MachineData."""
import time
from datetime import datetime
from typing import List
import structlog

from core.config import settings
from core.models import RawDataRecord, TagUpdatedEvent, ProcessingState, BatchMetrics
from core.tag_registry import tag_registry
from core.event_bus import event_bus
from infra.db_connection import db
from infra.redis_client import redis_client

logger = structlog.get_logger()


class BatchLoader:
    """Continuous batch processor for MachineData."""
    
    def __init__(self):
        self.batch_size = settings.batch_size
        self.poll_interval_ms = settings.poll_interval_ms
        self.service_name = settings.service_name
        self._running = False
        self._last_processed_id = 0
        self._batches_processed = 0
        self._total_events = 0
        self._total_processing_time = 0.0
        self._start_time = time.time()
        self._ensure_state_table()
        self._load_state()
    
    def _ensure_state_table(self) -> None:
        """Create processing state table if it doesn't exist."""
        create_table_sql = """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ProcessingState')
        BEGIN
            CREATE TABLE ProcessingState (
                service_name NVARCHAR(100) PRIMARY KEY,
                last_processed_id BIGINT NOT NULL DEFAULT 0,
                updated_at DATETIME2 DEFAULT GETUTCDATE()
            );
        END
        """
        with db.cursor() as cursor:
            cursor.execute(create_table_sql)
            db.commit()
        logger.info("processing_state_table_ready")
    
    def _load_state(self) -> None:
        """Load last processed ID from database."""
        query = """
        SELECT last_processed_id FROM ProcessingState WHERE service_name = ?
        """
        with db.cursor() as cursor:
            cursor.execute(query, (self.service_name,))
            row = cursor.fetchone()
            if row:
                self._last_processed_id = row.last_processed_id
            else:
                # Initialize state
                insert_sql = """
                INSERT INTO ProcessingState (service_name, last_processed_id)
                VALUES (?, 0)
                """
                cursor.execute(insert_sql, (self.service_name,))
                db.commit()
        
        logger.info("state_loaded", last_processed_id=self._last_processed_id)
    
    def _fetch_batch(self) -> List[RawDataRecord]:
        """Fetch next batch of raw data."""
        query = """
        SELECT TOP (?) id, nodeId, value, timestamp, quality
        FROM MachineData WITH (NOLOCK)
        WHERE id > ?
        ORDER BY id ASC
        """
        with db.cursor() as cursor:
            cursor.execute(query, (self.batch_size, self._last_processed_id))
            rows = cursor.fetchall()
            return [
                RawDataRecord(
                    id=row.id,
                    nodeId=row.nodeId,
                    value=row.value,
                    timestamp=row.timestamp,
                    quality=row.quality
                )
                for row in rows
            ]
    
    def _process_batch(self, records: List[RawDataRecord]) -> BatchMetrics:
        """Process a batch of records."""
        start_time = time.time()
        
        if not records:
            return BatchMetrics(
                batch_size=0,
                processing_time_ms=0,
                tags_updated=0,
                events_published=0,
                last_processed_id=self._last_processed_id
            )
        
        # Track unique tags in this batch
        tag_updates = {}  # tag_name -> latest record
        
        # Process each record
        for record in records:
            # Keep only the latest value for each tag in this batch
            if record.nodeId not in tag_updates or record.id > tag_updates[record.nodeId].id:
                tag_updates[record.nodeId] = record
        
        # Update tag registry, Redis, and publish events
        events_published = 0
        for tag_name, record in tag_updates.items():
            # Get or create tag_id
            tag_id = tag_registry.get_or_create_tag_id(tag_name)
            
            # Update Redis state
            redis_client.set_tag_state(
                tag_id=tag_id,
                tag_name=tag_name,
                value=record.value,
                timestamp=record.timestamp,
                quality=record.quality
            )
            
            # Publish event
            event = TagUpdatedEvent(
                tag_id=tag_id,
                tag_name=tag_name,
                value=record.value,
                timestamp=record.timestamp,
                quality=record.quality
            )
            event_bus.publish(event)
            events_published += 1
        
        # Update processing state
        last_id = records[-1].id
        self._update_state(last_id)
        
        processing_time = (time.time() - start_time) * 1000
        
        metrics = BatchMetrics(
            batch_size=len(records),
            processing_time_ms=processing_time,
            tags_updated=len(tag_updates),
            events_published=events_published,
            last_processed_id=last_id
        )
        
        self._batches_processed += 1
        self._total_events += events_published
        self._total_processing_time += processing_time
        
        logger.info("batch_processed",
                   batch_size=metrics.batch_size,
                   tags_updated=metrics.tags_updated,
                   processing_time_ms=f"{processing_time:.2f}",
                   last_id=last_id)
        
        return metrics
    
    def _update_state(self, last_processed_id: int) -> None:
        """Update processing state in database."""
        update_sql = """
        UPDATE ProcessingState
        SET last_processed_id = ?, updated_at = GETUTCDATE()
        WHERE service_name = ?
        """
        with db.cursor() as cursor:
            cursor.execute(update_sql, (last_processed_id, self.service_name))
            db.commit()
        
        self._last_processed_id = last_processed_id
    
    def get_db_lag(self) -> int:
        """Calculate database lag (latest ID - last processed ID)."""
        query = "SELECT MAX(id) as max_id FROM MachineData WITH (NOLOCK)"
        with db.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            max_id = row.max_id if row.max_id else 0
            return max_id - self._last_processed_id
    
    def get_stats(self) -> dict:
        """Get processing statistics."""
        uptime = time.time() - self._start_time
        avg_batch_time = (
            self._total_processing_time / self._batches_processed
            if self._batches_processed > 0 else 0
        )
        tags_per_second = self._total_events / uptime if uptime > 0 else 0
        
        return {
            "total_tags": tag_registry.get_tag_count(),
            "last_processed_id": self._last_processed_id,
            "db_lag": self.get_db_lag(),
            "batches_processed": self._batches_processed,
            "total_events_published": self._total_events,
            "avg_batch_time_ms": round(avg_batch_time, 2),
            "tags_per_second": round(tags_per_second, 2),
            "uptime_seconds": round(uptime, 2)
        }
    
    def run_once(self) -> BatchMetrics:
        """Process one batch (for testing/manual execution)."""
        records = self._fetch_batch()
        return self._process_batch(records)
    
    def run(self) -> None:
        """Run continuous batch processing."""
        self._running = True
        logger.info("batch_loader_started", 
                   batch_size=self.batch_size,
                   poll_interval_ms=self.poll_interval_ms)
        
        while self._running:
            try:
                records = self._fetch_batch()
                
                if records:
                    self._process_batch(records)
                else:
                    # No data available, sleep
                    time.sleep(self.poll_interval_ms / 1000.0)
            
            except Exception as e:
                logger.error("batch_processing_error", error=str(e))
                time.sleep(1)  # Back off on error
    
    def stop(self) -> None:
        """Stop batch processing."""
        self._running = False
        logger.info("batch_loader_stopped")


# Global batch loader instance
batch_loader = BatchLoader()
