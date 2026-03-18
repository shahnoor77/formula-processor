"""Tag-related API endpoints."""
from typing import List
from fastapi import APIRouter, HTTPException
import structlog

from core.models import TagInfo, TagState
from core.tag_registry import tag_registry
from infra.redis_client import redis_client

logger = structlog.get_logger()
router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("/", response_model=List[TagInfo])
async def list_tags():
    """List all registered tags."""
    try:
        tags = tag_registry.get_all_tags()
        return tags
    except Exception as e:
        logger.error("list_tags_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live", response_model=List[TagState])
async def get_live_tags():
    """Get live tag values from Redis."""
    try:
        states = redis_client.get_all_tag_states()
        return states
    except Exception as e:
        logger.error("get_live_tags_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tag_id}", response_model=TagState)
async def get_tag_state(tag_id: int):
    """Get specific tag state."""
    try:
        state = redis_client.get_tag_state(tag_id)
        if not state:
            raise HTTPException(status_code=404, detail="Tag not found")
        return state
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_tag_state_error", tag_id=tag_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
