from fastapi import APIRouter, Query
import structlog

from core.formula_processor_service import formula_processor_service
from core.config import settings
from infra.db_connection import db

logger = structlog.get_logger()
router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


@router.get("/stats")
async def get_system_stats():
    return formula_processor_service.get_stats()


@router.get("/raw-data")
async def get_raw_data(limit: int = Query(20, le=200)):
    try:
        with db.cursor() as cursor:
            cursor.execute(f"SELECT TOP (?) Id, NodeId, value, timestamp, quality FROM {settings.table_source} ORDER BY Id DESC", (limit,))
            rows = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {settings.table_source} WHERE timestamp >= DATEADD(SECOND, -1, GETUTCDATE())")
            rate = cursor.fetchone()
            cursor.execute(f"SELECT COUNT(DISTINCT NodeId) as n FROM {settings.table_source}")
            nodes = cursor.fetchone()

        return {
            "tags_per_second": rate.cnt if rate else 0,
            "distinct_nodes": nodes.n if nodes else 0,
            "rows": [
                {
                    "id": r.Id,
                    "node_id": r.NodeId,
                    "alias": r.NodeId.split(".")[-1] if r.NodeId else "",
                    "value": float(r.value) if r.value is not None else None,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "quality": r.quality
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("raw_data_error", error=str(e))
        return {"tags_per_second": 0, "distinct_nodes": 0, "rows": []}
