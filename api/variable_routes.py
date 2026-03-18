from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import structlog

from core.formula_engine.formula_loader import formula_loader
from core.config import settings
from infra.db_connection import db

logger = structlog.get_logger()
router = APIRouter(prefix="/variables", tags=["variables"])


@router.get("/formulas")
async def list_formulas():
    try:
        with db.cursor() as cursor:
            cursor.execute(f"""
                SELECT VariableId, VariableName, PreSaveFormula, FormulaType, Time AS Interval
                FROM {settings.table_variables}
                WHERE IsDeleted = 0 AND FormulaType = 'SINGLE'
                ORDER BY VariableName
            """)
            rows = cursor.fetchall()
        return [
            {
                'variable_id': r.VariableId,
                'variable_name': r.VariableName,
                'formula': r.PreSaveFormula,
                'formula_type': r.FormulaType,
                'interval': r.Interval
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("list_formulas_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions")
async def get_executions(
    limit: int = Query(100, le=1000),
    alias: Optional[str] = Query(None)
):
    try:
        if alias:
            query = f"""
            SELECT TOP (?) e.Id, e.VariableId, v.VariableName, v.PreSaveFormula,
                e.Result, e.ResultOn, e.ProcessedOn, e.Interval, e.CreatedOn
            FROM {settings.table_executions} e
            LEFT JOIN {settings.table_variables} v ON e.VariableId = v.VariableId
            WHERE e.IsDeleted = 0 AND v.VariableName LIKE ?
            ORDER BY e.CreatedOn DESC
            """
            params = (limit, f"{alias}%")
        else:
            query = f"""
            SELECT TOP (?) e.Id, e.VariableId, v.VariableName, v.PreSaveFormula,
                e.Result, e.ResultOn, e.ProcessedOn, e.Interval, e.CreatedOn
            FROM {settings.table_executions} e
            LEFT JOIN {settings.table_variables} v ON e.VariableId = v.VariableId
            WHERE e.IsDeleted = 0
            ORDER BY e.CreatedOn DESC
            """
            params = (limit,)

        with db.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [
            {
                'id': r.Id,
                'variable_id': r.VariableId,
                'variable_name': r.VariableName,
                'formula': r.PreSaveFormula,
                'result': r.Result,
                'result_on': r.ResultOn.isoformat() if r.ResultOn else None,
                'processed_on': r.ProcessedOn.isoformat() if r.ProcessedOn else None,
                'interval': r.Interval,
                'created_on': r.CreatedOn.isoformat() if r.CreatedOn else None
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("get_executions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions/summary")
async def get_executions_summary():
    try:
        with db.cursor() as cursor:
            cursor.execute(f"""
                SELECT v.VariableName, v.PreSaveFormula, v.Time AS CurrentInterval,
                    COUNT(e.Id) AS TotalExecutions,
                    MAX(e.ProcessedOn) AS LastProcessedOn,
                    MAX(CAST(e.Result AS FLOAT)) AS LatestResult
                FROM {settings.table_variables} v
                LEFT JOIN {settings.table_executions} e ON e.VariableId = v.VariableId AND e.IsDeleted = 0
                WHERE v.IsDeleted = 0 AND v.FormulaType = 'SINGLE'
                GROUP BY v.VariableName, v.PreSaveFormula, v.Time
                ORDER BY v.VariableName
            """)
            rows = cursor.fetchall()
        return [
            {
                'variable_name': r.VariableName,
                'formula': r.PreSaveFormula,
                'current_interval': r.CurrentInterval,
                'total_executions': r.TotalExecutions,
                'last_processed_on': r.LastProcessedOn.isoformat() if r.LastProcessedOn else None,
                'latest_result': r.LatestResult
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("get_summary_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def refresh_formulas():
    try:
        formula_loader.load_formulas()
        return {'status': 'success', 'formula_counts': formula_loader.get_formula_count()}
    except Exception as e:
        logger.error("refresh_formulas_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-formula")
async def test_formula(payload: dict):
    try:
        from core.formula_engine.formula_executor import formula_executor
        formula = payload.get("formula", "")
        tags = payload.get("tags", {})

        if not formula:
            raise HTTPException(status_code=400, detail="formula is required")
        if not tags:
            raise HTTPException(status_code=400, detail="tags is required")

        resolved = formula
        for node_id, value in tags.items():
            bracketed = f'[{node_id}]' if not node_id.startswith('[') else node_id
            plain = node_id.strip('[]')
            resolved = resolved.replace(bracketed, str(value))
            resolved = resolved.replace(plain, str(value))

        first_value = list(tags.values())[0]
        result, error = formula_executor.execute_single(resolved, float(first_value))

        return {"formula": formula, "resolved": resolved, "tags": tags, "result": result, "error": error}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("test_formula_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
