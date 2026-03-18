"""Formula Engine data models."""
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FormulaMapping(BaseModel):
    """Mapping between formula variable and tag."""
    variable: str
    tag_id: int


class FormulaCreate(BaseModel):
    """Request model for creating a formula."""
    name: str
    expression: str
    mappings: List[FormulaMapping]


class FormulaUpdate(BaseModel):
    """Request model for updating a formula."""
    name: Optional[str] = None
    expression: Optional[str] = None
    mappings: Optional[List[FormulaMapping]] = None
    is_active: Optional[bool] = None


class Formula(BaseModel):
    """Formula model."""
    id: int
    name: str
    expression: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    mappings: List[FormulaMapping] = []


class FormulaStats(BaseModel):
    """Formula execution statistics."""
    formula_id: int
    formula_name: str
    execution_count: int
    avg_latency_ms: float
    max_latency_ms: float
    last_execution_time: Optional[datetime]
    error_count: int
    last_result: Optional[float] = None


class CalculatedTag(BaseModel):
    """Calculated tag result."""
    id: int
    formula_id: int
    result_value: float
    calculated_at: datetime
    execution_time_ms: float
    trigger_tag_id: Optional[int]


class ExecutionTask(BaseModel):
    """Task for formula execution."""
    formula_id: int
    trigger_tag_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
