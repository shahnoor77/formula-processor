import math
from typing import Tuple, Optional

from core.formula_engine.expression_compiler import ExpressionCompiler


class FormulaExecutor:
    def __init__(self):
        self.compiler = ExpressionCompiler()
        self._cache = {}

    def _validate(self, value: any) -> Tuple[bool, Optional[str]]:
        if value is None:
            return False, "NULL_VALUE"
        if not isinstance(value, (int, float)):
            return False, "INVALID_TYPE"
        if math.isnan(value):
            return False, "NAN_VALUE"
        if math.isinf(value):
            return False, "INFINITE_VALUE"
        return True, None

    def execute_single(self, formula: str, input_value: float) -> Tuple[Optional[float], Optional[str]]:
        try:
            is_valid, error = self._validate(input_value)
            if not is_valid:
                return None, error

            if formula not in self._cache:
                try:
                    self._cache[formula] = self.compiler.compile(formula)
                except Exception as e:
                    return None, f"COMPILE_ERROR: {e}"

            result = self._cache[formula]({})

            is_valid, error = self._validate(result)
            if not is_valid:
                return None, f"RESULT_{error}"

            return float(result), None

        except ZeroDivisionError:
            return None, "DIVISION_BY_ZERO"
        except OverflowError:
            return None, "OVERFLOW"
        except ValueError as e:
            return None, f"VALUE_ERROR: {e}"
        except Exception as e:
            return None, f"EXECUTION_ERROR: {e}"


formula_executor = FormulaExecutor()
