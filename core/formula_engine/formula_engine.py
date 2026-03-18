"""Main Formula Engine implementation."""
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
from collections import defaultdict
import structlog

from core.models import TagUpdatedEvent
from core.event_bus import event_bus
from core.formula_engine.models import Formula, FormulaMapping, FormulaStats
from core.formula_engine.expression_compiler import expression_compiler
from core.formula_engine.dependency_graph import dependency_graph
from core.formula_engine.execution_worker import execution_worker
from infra.db_connection import db
from infra.redis_client import redis_client

logger = structlog.get_logger()


class FormulaEngine:
    """Main formula engine for dynamic expression evaluation."""
    
    def __init__(self):
        # Compiled formulas: formula_id -> (evaluator_func, variable_to_tag_id)
        self._compiled_formulas: Dict[int, tuple[Callable, Dict[str, int]]] = {}
        
        # Formula metadata: formula_id -> Formula
        self._formulas: Dict[int, Formula] = {}
        
        # Statistics: formula_id -> stats
        self._stats: Dict[int, Dict] = defaultdict(lambda: {
            "execution_count": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "last_execution_time": None,
            "error_count": 0,
            "last_result": None
        })
        
        self._initialized = False
        self.logger = logger.bind(component="formula_engine")
    
    def initialize(self) -> None:
        """Initialize formula engine."""
        if self._initialized:
            return
        
        try:
            # Load formulas from database
            self._load_formulas()
            
            # Subscribe to tag update events
            event_bus.subscribe(self._handle_tag_update)
            
            # Start execution workers
            execution_worker.start()
            
            self._initialized = True
            self.logger.info("formula_engine_initialized", 
                           formula_count=len(self._formulas))
            
        except Exception as e:
            self.logger.error("formula_engine_init_error", error=str(e))
            raise
    
    def shutdown(self) -> None:
        """Shutdown formula engine."""
        execution_worker.stop()
        self._initialized = False
        self.logger.info("formula_engine_shutdown")
    
    def _load_formulas(self) -> None:
        """Load all active formulas from database."""
        try:
            with db.cursor() as cursor:
                # Load formulas
                cursor.execute("""
                    SELECT id, name, expression, is_active, created_at, updated_at
                    FROM Formula
                    WHERE is_active = 1
                """)
                
                for row in cursor.fetchall():
                    formula_id = row[0]
                    
                    # Load mappings
                    cursor.execute("""
                        SELECT variable_name, tag_id
                        FROM FormulaTagMapping
                        WHERE formula_id = ?
                    """, formula_id)
                    
                    mappings = [
                        FormulaMapping(variable=r[0], tag_id=r[1])
                        for r in cursor.fetchall()
                    ]
                    
                    formula = Formula(
                        id=formula_id,
                        name=row[1],
                        expression=row[2],
                        is_active=bool(row[3]),
                        created_at=row[4],
                        updated_at=row[5],
                        mappings=mappings
                    )
                    
                    # Compile and register
                    self._compile_and_register(formula)
            
            self.logger.info("formulas_loaded", count=len(self._formulas))
            
        except Exception as e:
            self.logger.error("formula_load_error", error=str(e))
            raise
    
    def _compile_and_register(self, formula: Formula) -> None:
        """Compile formula and register dependencies."""
        try:
            # Compile expression
            evaluator = expression_compiler.compile(formula.expression)
            
            # Build variable to tag_id mapping
            var_to_tag = {m.variable: m.tag_id for m in formula.mappings}
            
            # Store compiled formula
            self._compiled_formulas[formula.id] = (evaluator, var_to_tag)
            self._formulas[formula.id] = formula
            
            # Register dependencies
            tag_ids = [m.tag_id for m in formula.mappings]
            dependency_graph.add_formula(formula.id, tag_ids)
            
            self.logger.info("formula_compiled",
                           formula_id=formula.id,
                           name=formula.name,
                           variables=list(var_to_tag.keys()))
            
        except Exception as e:
            self.logger.error("formula_compile_error",
                            formula_id=formula.id,
                            error=str(e))
            raise
    
    def _handle_tag_update(self, event: TagUpdatedEvent) -> None:
        """Handle tag update event."""
        try:
            # Get affected formulas
            formula_ids = dependency_graph.get_affected_formulas(event.tag_id)
            
            if not formula_ids:
                return
            
            # Execute each affected formula
            for formula_id in formula_ids:
                self._execute_formula(formula_id, event.tag_id)
            
        except Exception as e:
            self.logger.error("tag_update_handler_error",
                            tag_id=event.tag_id,
                            error=str(e))
    
    def _execute_formula(self, formula_id: int, trigger_tag_id: int) -> None:
        """Execute a single formula."""
        start_time = time.time()
        
        try:
            # Get compiled formula
            if formula_id not in self._compiled_formulas:
                self.logger.warning("formula_not_found", formula_id=formula_id)
                return
            
            evaluator, var_to_tag = self._compiled_formulas[formula_id]
            
            # Fetch tag values from Redis
            context = {}
            for variable, tag_id in var_to_tag.items():
                tag_state = redis_client.get_tag_state(tag_id)
                if tag_state is None:
                    self.logger.warning("tag_state_not_found",
                                      formula_id=formula_id,
                                      tag_id=tag_id)
                    return
                context[variable] = tag_state.value
            
            # Execute formula
            result = evaluator(context)
            
            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Update statistics
            self._update_stats(formula_id, execution_time_ms, result)
            
            # Add result to worker buffer
            execution_worker.add_result(
                formula_id=formula_id,
                result_value=float(result),
                execution_time_ms=execution_time_ms,
                trigger_tag_id=trigger_tag_id
            )
            
            self.logger.debug("formula_executed",
                            formula_id=formula_id,
                            result=result,
                            execution_time_ms=execution_time_ms)
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self._stats[formula_id]["error_count"] += 1
            
            self.logger.error("formula_execution_error",
                            formula_id=formula_id,
                            error=str(e),
                            execution_time_ms=execution_time_ms)
    
    def _update_stats(self, formula_id: int, execution_time_ms: float, result: float) -> None:
        """Update formula execution statistics."""
        stats = self._stats[formula_id]
        
        stats["execution_count"] += 1
        stats["total_latency_ms"] += execution_time_ms
        stats["avg_latency_ms"] = stats["total_latency_ms"] / stats["execution_count"]
        stats["max_latency_ms"] = max(stats["max_latency_ms"], execution_time_ms)
        stats["last_execution_time"] = datetime.utcnow()
        stats["last_result"] = result
    
    def add_formula(self, name: str, expression: str, 
                   mappings: List[FormulaMapping]) -> int:
        """Add new formula."""
        try:
            # Validate expression
            variables = expression_compiler.extract_variables(expression)
            mapping_vars = {m.variable for m in mappings}
            
            if variables != mapping_vars:
                raise ValueError(
                    f"Variable mismatch. Expression uses {variables}, "
                    f"but mappings provide {mapping_vars}"
                )
            
            # Insert into database
            with db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO Formula (name, expression, is_active, created_at, updated_at)
                    VALUES (?, ?, 1, GETDATE(), GETDATE())
                """, name, expression)
                
                cursor.execute("SELECT @@IDENTITY")
                formula_id = int(cursor.fetchone()[0])
                
                # Insert mappings
                for mapping in mappings:
                    cursor.execute("""
                        INSERT INTO FormulaTagMapping (formula_id, variable_name, tag_id)
                        VALUES (?, ?, ?)
                    """, formula_id, mapping.variable, mapping.tag_id)
                
                db.commit()
            
            # Load and compile formula
            formula = Formula(
                id=formula_id,
                name=name,
                expression=expression,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                mappings=mappings
            )
            
            self._compile_and_register(formula)
            
            self.logger.info("formula_added", formula_id=formula_id, name=name)
            
            return formula_id
            
        except Exception as e:
            db.rollback()
            self.logger.error("formula_add_error", error=str(e))
            raise
    
    def update_formula(self, formula_id: int, name: Optional[str] = None,
                      expression: Optional[str] = None,
                      mappings: Optional[List[FormulaMapping]] = None) -> None:
        """Update existing formula."""
        try:
            with db.cursor() as cursor:
                if name is not None:
                    cursor.execute("""
                        UPDATE Formula
                        SET name = ?, updated_at = GETDATE()
                        WHERE id = ?
                    """, name, formula_id)
                
                if expression is not None or mappings is not None:
                    # Remove from runtime
                    self._remove_formula_runtime(formula_id)
                    
                    if expression is not None:
                        cursor.execute("""
                            UPDATE Formula
                            SET expression = ?, updated_at = GETDATE()
                            WHERE id = ?
                        """, expression, formula_id)
                    
                    if mappings is not None:
                        # Delete old mappings
                        cursor.execute("""
                            DELETE FROM FormulaTagMapping
                            WHERE formula_id = ?
                        """, formula_id)
                        
                        # Insert new mappings
                        for mapping in mappings:
                            cursor.execute("""
                                INSERT INTO FormulaTagMapping (formula_id, variable_name, tag_id)
                                VALUES (?, ?, ?)
                            """, formula_id, mapping.variable, mapping.tag_id)
                    
                    # Reload formula
                    cursor.execute("""
                        SELECT id, name, expression, is_active, created_at, updated_at
                        FROM Formula
                        WHERE id = ?
                    """, formula_id)
                    
                    row = cursor.fetchone()
                    if row:
                        cursor.execute("""
                            SELECT variable_name, tag_id
                            FROM FormulaTagMapping
                            WHERE formula_id = ?
                        """, formula_id)
                        
                        mappings_loaded = [
                            FormulaMapping(variable=r[0], tag_id=r[1])
                            for r in cursor.fetchall()
                        ]
                        
                        formula = Formula(
                            id=row[0],
                            name=row[1],
                            expression=row[2],
                            is_active=bool(row[3]),
                            created_at=row[4],
                            updated_at=row[5],
                            mappings=mappings_loaded
                        )
                        
                        self._compile_and_register(formula)
                
                db.commit()
            
            self.logger.info("formula_updated", formula_id=formula_id)
            
        except Exception as e:
            db.rollback()
            self.logger.error("formula_update_error", formula_id=formula_id, error=str(e))
            raise
    
    def toggle_formula(self, formula_id: int, is_active: bool) -> None:
        """Enable or disable formula."""
        try:
            with db.cursor() as cursor:
                cursor.execute("""
                    UPDATE Formula
                    SET is_active = ?, updated_at = GETDATE()
                    WHERE id = ?
                """, is_active, formula_id)
                db.commit()
            
            if is_active:
                # Reload formula
                self._load_single_formula(formula_id)
            else:
                # Remove from runtime
                self._remove_formula_runtime(formula_id)
            
            self.logger.info("formula_toggled", formula_id=formula_id, is_active=is_active)
            
        except Exception as e:
            db.rollback()
            self.logger.error("formula_toggle_error", formula_id=formula_id, error=str(e))
            raise
    
    def _load_single_formula(self, formula_id: int) -> None:
        """Load a single formula from database."""
        try:
            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, expression, is_active, created_at, updated_at
                    FROM Formula
                    WHERE id = ? AND is_active = 1
                """, formula_id)
                
                row = cursor.fetchone()
                if not row:
                    return
                
                cursor.execute("""
                    SELECT variable_name, tag_id
                    FROM FormulaTagMapping
                    WHERE formula_id = ?
                """, formula_id)
                
                mappings = [
                    FormulaMapping(variable=r[0], tag_id=r[1])
                    for r in cursor.fetchall()
                ]
                
                formula = Formula(
                    id=row[0],
                    name=row[1],
                    expression=row[2],
                    is_active=bool(row[3]),
                    created_at=row[4],
                    updated_at=row[5],
                    mappings=mappings
                )
                
                self._compile_and_register(formula)
                
        except Exception as e:
            self.logger.error("formula_load_single_error", formula_id=formula_id, error=str(e))
            raise
    
    def _remove_formula_runtime(self, formula_id: int) -> None:
        """Remove formula from runtime."""
        if formula_id in self._compiled_formulas:
            del self._compiled_formulas[formula_id]
        if formula_id in self._formulas:
            del self._formulas[formula_id]
        dependency_graph.remove_formula(formula_id)
    
    def delete_formula(self, formula_id: int) -> None:
        """Delete formula."""
        try:
            # Remove from runtime
            self._remove_formula_runtime(formula_id)
            
            # Delete from database (cascade will handle mappings and results)
            with db.cursor() as cursor:
                cursor.execute("DELETE FROM Formula WHERE id = ?", formula_id)
                db.commit()
            
            self.logger.info("formula_deleted", formula_id=formula_id)
            
        except Exception as e:
            db.rollback()
            self.logger.error("formula_delete_error", formula_id=formula_id, error=str(e))
            raise
    
    def get_formula(self, formula_id: int) -> Optional[Formula]:
        """Get formula by ID."""
        return self._formulas.get(formula_id)
    
    def get_all_formulas(self) -> List[Formula]:
        """Get all formulas."""
        return list(self._formulas.values())
    
    def get_formula_stats(self, formula_id: int) -> Optional[FormulaStats]:
        """Get formula execution statistics."""
        if formula_id not in self._formulas:
            return None
        
        formula = self._formulas[formula_id]
        stats = self._stats[formula_id]
        
        return FormulaStats(
            formula_id=formula_id,
            formula_name=formula.name,
            execution_count=stats["execution_count"],
            avg_latency_ms=stats["avg_latency_ms"],
            max_latency_ms=stats["max_latency_ms"],
            last_execution_time=stats["last_execution_time"],
            error_count=stats["error_count"],
            last_result=stats["last_result"]
        )
    
    def get_all_stats(self) -> List[FormulaStats]:
        """Get statistics for all formulas."""
        return [
            self.get_formula_stats(formula_id)
            for formula_id in self._formulas.keys()
        ]


# Global formula engine instance
formula_engine = FormulaEngine()
