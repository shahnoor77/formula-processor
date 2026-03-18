"""System monitoring and health endpoints."""
from fastapi import APIRouter, HTTPException
import structlog

from core.batch_loader import batch_loader
from core.models import SystemStats

logger = structlog.get_logger()
router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "tag-processor"
    }


@router.get("/stats", response_model=SystemStats)
async def get_system_stats():
    """Get system statistics."""
    try:
        stats = batch_loader.get_stats()
        return SystemStats(**stats)
    except Exception as e:
        logger.error("get_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-batch")
async def trigger_batch_processing():
    """Manually trigger batch processing (for testing)."""
    try:
        metrics = batch_loader.run_once()
        return {
            "status": "success",
            "metrics": metrics.model_dump()
        }
    except Exception as e:
        logger.error("manual_batch_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
