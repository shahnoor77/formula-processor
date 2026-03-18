"""Core data models."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RawDataRecord(BaseModel):
    """Raw data record from MachineData table."""
    id: int
    nodeId: str
    value: float
    timestamp: datetime
    quality: str


class TagInfo(BaseModel):
    """Tag registry information."""
    tag_id: int
    tag_name: str
    created_at: datetime


class TagState(BaseModel):
    """Current state of a tag in Redis."""
    tag_id: int
    tag_name: str
    value: float
    timestamp: datetime
    quality: str


class TagUpdatedEvent(BaseModel):
    """Event published when a tag is updated."""
    tag_id: int
    tag_name: str
    value: float
    timestamp: datetime
    quality: str = "GOOD"


class ProcessingState(BaseModel):
    """Processing state tracker."""
    service_name: str
    last_processed_id: int


class BatchMetrics(BaseModel):
    """Metrics for batch processing."""
    batch_size: int
    processing_time_ms: float
    tags_updated: int
    events_published: int
    last_processed_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SystemStats(BaseModel):
    """System statistics."""
    total_tags: int
    last_processed_id: int
    db_lag: int
    batches_processed: int
    total_events_published: int
    avg_batch_time_ms: float
    tags_per_second: float
    uptime_seconds: float
