"""Safe expression compiler using AST."""
import ast
import operator
from typing import Dict, Set, Callable, Any
import structlog

logger = structlog.get_logger()

# Safe operators
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

# Safe comparison operators
SAFE_COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

# Safe boolean operators
SAFE_BOOL_OPS = {
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
}


class ExpressionCompiler:
    """Compiles and validates expressions safely using AST."""
    
    def __init__(self):
        self.logger = logger.bind(component="expression_compiler")
    
    def compile(self, expression: str) -> Callable[[Dict[str, float]], float]:
        """
        Compile expression to executable function.
        
        Args:
            expression: Mathematical expression string
            
        Returns:
            Compiled function that takes variable dict and returns result
            
        Raises:
            ValueError: If expression is invalid or unsafe
        """
        try:
            # Parse expression
            tree = ast.parse(expression, mode='eval')
            
            # Validate safety
            variables = self._validate_and_extract_variables(tree)
            
            # Create evaluator function
            def evaluator(context: Dict[str, float]) -> float:
                return self._evaluate_node(tree.body, context)
            
            self.logger.info("expression_compiled", 
                           expression=expression, 
                           variables=list(variables))
            
            return evaluator
            
        except SyntaxError as e:
            self.logger.error("expression_syntax_error", 
                            expression=expression, 
                            error=str(e))
            raise ValueError(f"Invalid expression syntax: {e}")
        except Exception as e:
            self.logger.error("expression_compilation_error", 
                            expression=expression, 
                            error=str(e))
            raise ValueError(f"Failed to compile expression: {e}")
    
    def extract_variables(self, expression: str) -> Set[str]:
        """Extract variable names from expression."""
        try:
            tree = ast.parse(expression, mode='eval')
            return self._validate_and_extract_variables(tree)
        except Exception as e:
            raise ValueError(f"Failed to parse expression: {e}")
    
    def _validate_and_extract_variables(self, tree: ast.AST) -> Set[str]:
        """Validate expression safety and extract variables."""
        variables = set()
        
        for node in ast.walk(tree):
            # Check for unsafe operations
            if isinstance(node, ast.Call):
                raise ValueError("Function calls are not allowed")
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                raise ValueError("Imports are not allowed")
            if isinstance(node, ast.Attribute):
                raise ValueError("Attribute access is not allowed")
            if isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
                raise ValueError("Function definitions are not allowed")
            if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                raise ValueError("Comprehensions are not allowed")
            if isinstance(node, (ast.Yield, ast.YieldFrom, ast.Await)):
                raise ValueError("Async operations are not allowed")
            
            # Extract variable names
            if isinstance(node, ast.Name):
                variables.add(node.id)
        
        return variables
    
    def _evaluate_node(self, node: ast.AST, context: Dict[str, float]) -> Any:
        """Recursively evaluate AST node."""
        if isinstance(node, ast.Constant):
            # Python 3.8+ uses ast.Constant for all constants
            return node.value
        
        elif isinstance(node, ast.Name):
            # Variable lookup
            if node.id not in context:
                raise ValueError(f"Variable '{node.id}' not found in context")
            return context[node.id]
        
        elif isinstance(node, ast.BinOp):
            # Binary operation
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Operator {op_type.__name__} not allowed")
            
            left = self._evaluate_node(node.left, context)
            right = self._evaluate_node(node.right, context)
            
            # Handle division by zero
            if op_type == ast.Div and right == 0:
                raise ValueError("Division by zero")
            
            return SAFE_OPERATORS[op_type](left, right)
        
        elif isinstance(node, ast.UnaryOp):
            # Unary operation
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise ValueError(f"Operator {op_type.__name__} not allowed")
            
            operand = self._evaluate_node(node.operand, context)
            return SAFE_OPERATORS[op_type](operand)
        
        elif isinstance(node, ast.Compare):
            # Comparison operation
            left = self._evaluate_node(node.left, context)
            
            for op, comparator in zip(node.ops, node.comparators):
                op_type = type(op)
                if op_type not in SAFE_COMPARISONS:
                    raise ValueError(f"Comparison {op_type.__name__} not allowed")
                
                right = self._evaluate_node(comparator, context)
                result = SAFE_COMPARISONS[op_type](left, right)
                
                if not result:
                    return False
                left = right
            
            return True
        
        elif isinstance(node, ast.BoolOp):
            # Boolean operation (and, or)
            op_type = type(node.op)
            if op_type not in SAFE_BOOL_OPS:
                raise ValueError(f"Boolean operator {op_type.__name__} not allowed")
            
            values = [self._evaluate_node(v, context) for v in node.values]
            
            if op_type == ast.And:
                return all(values)
            elif op_type == ast.Or:
                return any(values)
        
        elif isinstance(node, ast.IfExp):
            # Ternary conditional (a if condition else b)
            test = self._evaluate_node(node.test, context)
            if test:
                return self._evaluate_node(node.body, context)
            else:
                return self._evaluate_node(node.orelse, context)
        
        else:
            raise ValueError(f"Unsupported node type: {type(node).__name__}")


# Global compiler instance
expression_compiler = ExpressionCompiler()
