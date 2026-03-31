import re
from typing import List, Dict, Optional
from datetime import datetime
import structlog

from infra.db_connection import db
from core.config import settings

logger = structlog.get_logger()


class FormulaInfo:
    def __init__(self, variable_id: int, formula: str, formula_type: str,
                 time_window: int = 0, time_interval: Optional[datetime] = None):
        self.variable_id = variable_id
        self.formula = formula
        self.formula_type = formula_type
        self.time_window = time_window
        self.time_interval = time_interval

    @property
    def is_windowed(self) -> bool:
        """Windowed if Time > 0, regardless of formula syntax."""
        return self.time_window > 0

    @property
    def is_due(self) -> bool:
        if not self.is_windowed:
            return True
        if self.time_interval is None:
            return True
        deadline = self.time_interval
        if hasattr(deadline, 'tzinfo') and deadline.tzinfo:
            deadline = deadline.replace(tzinfo=None)
        return datetime.utcnow() >= deadline


class FormulaLoader:
    def __init__(self):
        self.single_formulas: List[FormulaInfo] = []
        self.pair_formulas: List[FormulaInfo] = []
        self._last_refresh = datetime.min

    def load_formulas(self) -> None:
        query = f"""
        SELECT VariableId, PreSaveFormula, FormulaType,
               ISNULL(Time, 0) AS TimeWindow,
               TimeInterval
        FROM {settings.table_variables}
        WHERE IsDeleted = 0
          AND PreSaveFormula IS NOT NULL
          AND PreSaveFormula != ''
        """
        with db.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

            self.single_formulas.clear()
            self.pair_formulas.clear()

            for row in rows:
                info = FormulaInfo(
                    variable_id=row.VariableId,
                    formula=row.PreSaveFormula,
                    formula_type=row.FormulaType or 'SINGLE',
                    time_window=int(row.TimeWindow) if row.TimeWindow else 0,
                    time_interval=row.TimeInterval
                )
                self.single_formulas.append(info)

            self._last_refresh = datetime.utcnow()
            logger.info("formulas_loaded", total=len(self.single_formulas))

    def refresh_if_needed(self, refresh_interval_seconds: int = 30) -> None:
        elapsed = (datetime.utcnow() - self._last_refresh).total_seconds()
        if elapsed >= refresh_interval_seconds:
            self.load_formulas()

    def get_single_formulas(self) -> List[FormulaInfo]:
        return self.single_formulas

    def get_pair_formulas(self) -> List[FormulaInfo]:
        return self.pair_formulas

    def get_formula_count(self) -> Dict[str, int]:
        return {
            'single': len(self.single_formulas),
            'pair': len(self.pair_formulas),
            'total': len(self.single_formulas) + len(self.pair_formulas)
        }


formula_loader = FormulaLoader()
