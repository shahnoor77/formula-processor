from typing import List, Dict
from datetime import datetime
import structlog

from infra.db_connection import db
from core.config import settings

logger = structlog.get_logger()


class FormulaInfo:
    def __init__(self, variable_id: int, formula: str, formula_type: str):
        self.variable_id = variable_id
        self.formula = formula
        self.formula_type = formula_type


class FormulaLoader:
    def __init__(self):
        self.single_formulas: List[FormulaInfo] = []
        self.pair_formulas: List[FormulaInfo] = []
        self._last_refresh = datetime.min

    def load_formulas(self) -> None:
        query = f"""
        SELECT VariableId, PreSaveFormula, FormulaType
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
                    formula_type=row.FormulaType or 'SINGLE'
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
