import ast
import operator
import math
from typing import Dict, Set, Callable, Any

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

SAFE_FUNCTIONS = {
    'abs': abs, 'round': round, 'min': min, 'max': max,
    'pow': pow, 'sqrt': math.sqrt, 'ceil': math.ceil,
    'floor': math.floor, 'log': math.log, 'log10': math.log10,
    'exp': math.exp, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
}


class ExpressionCompiler:
    def compile(self, expression: str) -> Callable[[Dict[str, float]], float]:
        try:
            tree = ast.parse(expression, mode='eval')
            self._validate(tree)

            def evaluator(context: Dict[str, float]) -> float:
                return self._eval(tree.body, context)

            return evaluator
        except SyntaxError as e:
            raise ValueError(f"Syntax error: {e}")
        except Exception as e:
            raise ValueError(f"Compile error: {e}")

    def extract_variables(self, expression: str) -> Set[str]:
        tree = ast.parse(expression, mode='eval')
        return self._validate(tree)

    def _validate(self, tree: ast.AST) -> Set[str]:
        variables = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCTIONS:
                    raise ValueError("Unsafe function call")
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
                raise ValueError("Unsafe function call")
            args = [self._eval(arg, context) for arg in node.args]
            return SAFE_FUNCTIONS[node.func.id](*args)
        else:
            raise ValueError(f"Unsupported node: {type(node).__name__}")


expression_compiler = ExpressionCompiler()
