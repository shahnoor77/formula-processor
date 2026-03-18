"""On-demand formula executor."""
import time
from datetime import datetime
from typing import List
import structlog

from core.formula_engine.formula_registry import get_formula
from infra.redis_client import redis_client
from infra.db_connection import db

logger = structlog.get_logger()


class FormulaExecutor:
    """Execute formulas on-demand for selected tags."""
    
    def __init__(self):
        self.logger = logger.bind(component="formula_executor")
    
    def execute_formula(self, formula_id: str, tag_ids: List[int]) -> dict:
        """
        Execute a formula on selected tags.
        
        Args:
            formula_id: ID of the formula to execute
            tag_ids: List of tag IDs to apply formula to
            
        Returns:
            Execution result with value and metadata
        """
        start_time = time.time()
        
        try:
            # Get formula definition
            formula_def = get_formula(formula_id)
            
            # Validate tag count
            if len(tag_ids) < formula_def.required_tags:
                raise ValueError(
                    f"Formula '{formula_def.name}' requires at least "
                    f"{formula_def.required_tags} tags, got {len(tag_ids)}"
                )
            
            # Fetch tag values from Redis
            tag_values = []
            tag_names = []
            for tag_id in tag_ids:
                tag_state = redis_client.get_tag_state(tag_id)
                if tag_state is None:
                    raise ValueError(f"Tag {tag_id} not found in Redis")
                tag_values.append(tag_state.value)
                tag_names.append(tag_state.tag_name)
            
            # Execute formula
            result = self._evaluate_formula(formula_def.expression, tag_values)
            
            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Store result in database
            calculated_at = datetime.utcnow()
            result_id = self._store_result(
                formula_id=formula_id,
                formula_name=formula_def.name,
                tag_ids=tag_ids,
                result_value=result,
                execution_time_ms=execution_time_ms,
                calculated_at=calculated_at
            )
            
            self.logger.info(
                "formula_executed",
                formula_id=formula_id,
                formula_name=formula_def.name,
                tag_count=len(tag_ids),
                result=result,
                execution_time_ms=execution_time_ms
            )
            
            return {
                "result_id": result_id,
                "formula_id": formula_id,
                "formula_name": formula_def.name,
                "tag_ids": tag_ids,
                "tag_names": tag_names,
                "result_value": result,
                "execution_time_ms": execution_time_ms,
                "calculated_at": calculated_at.isoformat()
            }
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "formula_execution_error",
                formula_id=formula_id,
                tag_ids=tag_ids,
                error=str(e),
                execution_time_ms=execution_time_ms
            )
            raise
    
    def _evaluate_formula(self, expression: str, tags: List[float]) -> float:
        """Safely evaluate formula expression."""
        # Create safe context
        safe_globals = {
            "sum": sum,
            "len": len,
            "max": max,
            "min": min,
            "abs": abs,
            "round": round,
            "tags": tags
        }
        
        # Evaluate expression
        try:
            result = eval(expression, {"__builtins__": {}}, safe_globals)
            return float(result)
        except Exception as e:
            raise ValueError(f"Formula evaluation failed: {e}")
    
    def _store_result(
        self,
        formula_id: str,
        formula_name: str,
        tag_ids: List[int],
        result_value: float,
        execution_time_ms: float,
        calculated_at: datetime
    ) -> int:
        """Store calculation result in database."""
        try:
            with db.cursor() as cursor:
                # Store in CalculatedTags with formula metadata
                cursor.execute("""
                    INSERT INTO CalculatedTags 
                    (formula_id, result_value, calculated_at, execution_time_ms, trigger_tag_id)
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?, ?)
                """, formula_id, result_value, calculated_at, execution_time_ms, tag_ids[0])
                
                result_id = cursor.fetchone()[0]
                db.commit()
                
                return result_id
                
        except Exception as e:
            db.rollback()
            self.logger.error("store_result_error", error=str(e))
            raise


# Global executor instance
formula_executor = FormulaExecutor()
