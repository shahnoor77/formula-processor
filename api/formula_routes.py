"""Formula API routes."""
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import structlog

from core.formula_engine.formula_registry import get_all_formulas, get_formula
from core.formula_engine.formula_executor import formula_executor
from infra.db_connection import db

logger = structlog.get_logger()
router = APIRouter(prefix="/formulas", tags=["formulas"])


class ExecuteFormulaRequest(BaseModel):
    """Request to execute a formula."""
    formula_id: str
    tag_ids: List[int]


@router.get("")
async def list_formulas():
    """Get all available pre-defined formulas."""
    try:
        formulas = get_all_formulas()
        return [
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "expression": f.expression,
                "required_tags": f.required_tags
            }
            for f in formulas
        ]
    except Exception as e:
        logger.error("list_formulas_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list formulas")


@router.get("/{formula_id}")
async def get_formula_by_id(formula_id: str):
    """Get formula definition by ID."""
    try:
        formula = get_formula(formula_id)
        return {
            "id": formula.id,
            "name": formula.name,
            "description": formula.description,
            "expression": formula.expression,
            "required_tags": formula.required_tags
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("get_formula_error", formula_id=formula_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get formula")


@router.post("/execute")
async def execute_formula(request: ExecuteFormulaRequest):
    """
    Execute a formula on selected tags.
    
    Example payload:
    ```json
    {
        "formula_id": "sum",
        "tag_ids": [71, 72, 73]
    }
    ```
    """
    try:
        result = formula_executor.execute_formula(
            formula_id=request.formula_id,
            tag_ids=request.tag_ids
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("execute_formula_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to execute formula")


@router.get("/history/recent")
async def get_recent_calculations(limit: int = Query(50, ge=1, le=500)):
    """Get recent formula calculations."""
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT TOP (?) id, formula_id, result_value, calculated_at, 
                       execution_time_ms, trigger_tag_id
                FROM CalculatedTags
                ORDER BY calculated_at DESC
            """, limit)
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "formula_id": row[1],
                    "result_value": row[2],
                    "calculated_at": row[3].isoformat(),
                    "execution_time_ms": row[4],
                    "trigger_tag_id": row[5]
                })
            
            return results
    except Exception as e:
        logger.error("get_recent_calculations_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get calculations")
