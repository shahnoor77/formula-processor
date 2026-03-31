import re
import ast
import operator
import math
from typing import Dict, Set, Callable, Any


# ── Safe operators ────────────────────────────────────────────────────────────

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

def _avg(*args):
    if len(args) == 1:
        # AVG of a single value just returns that value
        return float(args[0])
    return sum(args) / len(args) if args else 0.0

def _iif(condition, true_val, false_val):
    return true_val if condition else false_val

def _sum(*args):
    if len(args) == 1 and hasattr(args[0], '__iter__'):
        return sum(args[0])
    return sum(args)

SAFE_FUNCTIONS = {
    # Math
    'abs': abs, 'round': round, 'min': min, 'max': max,
    'pow': pow, 'sqrt': math.sqrt, 'ceil': math.ceil,
    'floor': math.floor, 'log': math.log, 'log10': math.log10,
    'exp': math.exp, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    # Aggregates
    'avg': _avg, 'AVG': _avg, 'average': _avg, 'AVERAGE': _avg,
    'sum': _sum, 'SUM': _sum,
    # Conditional helpers
    'iif': _iif, 'IIF': _iif,
}


# ── Formula normalizer ────────────────────────────────────────────────────────

def _normalize(formula: str) -> str:
    """
    Normalize various formula syntaxes to valid Python expressions.

    Handles:
    - IF (cond) THEN x ELSE y          → (x) if (cond) else (y)
    - IF cond THEN x ELSE y            → (x) if (cond) else (y)
    - expr + IF (cond) THEN x ELSE y   → inline ternary
    - IIF(cond, x, y)                  → kept as iif(cond, x, y)
    - AVG(a, b, c)                     → avg(a, b, c)
    - AVERAGE(a, b, c)                 → avg(a, b, c)
    - SUM(a, b)                        → sum([a, b])
    - ^ (XOR/power)                    → ** (power)
    - None / null / empty              → raises ValueError
    - String literals in results       → raises ValueError (non-numeric)
    """
    if not formula:
        raise ValueError("Empty formula")

    f = formula.strip()

    # Skip null/none placeholders
    if f.lower() in ('none', 'null', ''):
        raise ValueError("Null formula")

    # Normalize case-insensitive function names to lowercase equivalents
    f = re.sub(r'\bAVERAGE\b', 'avg', f, flags=re.IGNORECASE)
    f = re.sub(r'\bAVG\b', 'avg', f, flags=re.IGNORECASE)
    f = re.sub(r'\bSUM\b', 'sum', f, flags=re.IGNORECASE)
    f = re.sub(r'\bIIF\b', 'iif', f, flags=re.IGNORECASE)

    # Convert ^ to ** (power operator)
    f = re.sub(r'\^', '**', f)

    # Normalize IF/THEN/ELSE — handle both inline and standalone
    # Pattern: IF (cond) THEN expr ELSE expr  OR  IF cond THEN expr ELSE expr
    # We do multiple passes to handle nested/chained IF expressions
    f = _normalize_if_then_else(f)

    # If formula contains string literals (quoted), it returns non-numeric — skip
    if re.search(r'["\']', f):
        raise ValueError("Formula returns string value — not supported")

    return f


def _normalize_if_then_else(formula: str) -> str:
    """
    Iteratively convert IF/THEN/ELSE to Python ternary.
    Handles both standalone and inline occurrences.
    """
    # Match: IF (optional paren) condition THEN true_expr ELSE false_expr
    # We use a greedy approach working from innermost outward
    pattern = re.compile(
        r'IF\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*THEN\s*(.*?)\s*ELSE\s*(.*?)(?=\s*(?:\bIF\b|$))',
        re.IGNORECASE | re.DOTALL
    )

    # Also handle IF without parens around condition
    pattern_no_paren = re.compile(
        r'IF\s+([^()]+?)\s+THEN\s+(.*?)\s+ELSE\s+(.*?)(?=\s*(?:\bIF\b|$))',
        re.IGNORECASE | re.DOTALL
    )

    result = formula
    for _ in range(10):  # max 10 nested IFs
        prev = result

        # Try with parens first
        m = pattern.search(result)
        if m:
            cond = m.group(1).strip()
            then_e = m.group(2).strip()
            else_e = m.group(3).strip()
            replacement = f'(({then_e}) if ({cond}) else ({else_e}))'
            result = result[:m.start()] + replacement + result[m.end():]
            continue

        # Try without parens
        m = pattern_no_paren.search(result)
        if m:
            cond = m.group(1).strip()
            then_e = m.group(2).strip()
            else_e = m.group(3).strip()
            replacement = f'(({then_e}) if ({cond}) else ({else_e}))'
            result = result[:m.start()] + replacement + result[m.end():]
            continue

        if result == prev:
            break

    return result


# ── Expression compiler ───────────────────────────────────────────────────────

class ExpressionCompiler:
    def compile(self, expression: str) -> Callable[[Dict[str, float]], float]:
        normalized = _normalize(expression)

        try:
            tree = ast.parse(normalized, mode='eval')
            self._validate(tree)

            def evaluator(context: Dict[str, float]) -> float:
                return self._eval(tree.body, context)

            return evaluator
        except SyntaxError as e:
            raise ValueError(f"Syntax error: {e}")
        except Exception as e:
            raise ValueError(f"Compile error: {e}")

    def extract_variables(self, expression: str) -> Set[str]:
        normalized = _normalize(expression)
        tree = ast.parse(normalized, mode='eval')
        return self._validate(tree)

    def _validate(self, tree: ast.AST) -> Set[str]:
        variables = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCTIONS:
                    raise ValueError(f"Unsafe function: {getattr(node.func, 'id', '?')}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValueError("Imports not allowed")
            if isinstance(node, ast.Attribute):
                raise ValueError("Attribute access not allowed")
            if isinstance(node, (ast.Lambda, ast.FunctionDef)):
                raise ValueError("Function definitions not allowed")
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                parent = None
                for n in ast.walk(tree):
                    for child in ast.iter_child_nodes(n):
                        if child is node:
                            parent = n
                            break
                if not isinstance(parent, ast.Call) or parent.func is not node:
                    variables.add(node.id)
        return variables

    def _eval(self, node: ast.AST, context: Dict[str, float]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id not in context:
                raise ValueError(f"Variable '{node.id}' not in context")
            return context[node.id]
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Operator not allowed: {op_type.__name__}")
            left = self._eval(node.left, context)
            right = self._eval(node.right, context)
            if op_type == ast.Div and right == 0:
                raise ValueError("Division by zero")
            return SAFE_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Operator not allowed: {op_type.__name__}")
            return SAFE_OPERATORS[op_type](self._eval(node.operand, context))
        elif isinstance(node, ast.Compare):
            left = self._eval(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                op_type = type(op)
                if op_type not in SAFE_COMPARISONS:
                    raise ValueError(f"Comparison not allowed: {op_type.__name__}")
                right = self._eval(comparator, context)
                if not SAFE_COMPARISONS[op_type](left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            values = [self._eval(v, context) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        elif isinstance(node, ast.IfExp):
            test = self._eval(node.test, context)
            return self._eval(node.body, context) if test else self._eval(node.orelse, context)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCTIONS:
                raise ValueError(f"Unsafe function call")
            args = [self._eval(arg, context) for arg in node.args]
            return SAFE_FUNCTIONS[node.func.id](*args)
        else:
            raise ValueError(f"Unsupported node: {type(node).__name__}")


expression_compiler = ExpressionCompiler()
