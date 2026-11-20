"""Tools the model may call. Pure functions: no network, no DB, no eval()."""

import ast
import operator
from collections.abc import Callable

from mnemonic.schemas import ToolCall, ToolSpec

MAX_EXPRESSION_LENGTH = 100
MAX_EXPONENT = 100
MAX_INT_BITS = 2000  # ~600 digits: big enough for any study question, too small to hog the CPU

CALCULATOR = ToolSpec(
    name="calculator",
    description=(
        "Evaluates an arithmetic expression: numbers, + - * / // % **, parentheses. "
        "Use it for any calculation instead of computing in your head."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {"expression": {"type": "STRING", "description": "e.g. 3*12 + 2*7"}},
        "required": ["expression"],
    },
)

_BINARY: dict[type[ast.operator], Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


class CalculatorError(Exception):
    """A bad expression; the message goes back to the model as the tool result."""


def _check(value: int | float) -> int | float:
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CalculatorError("the result is not a finite number")
    elif value.bit_length() > MAX_INT_BITS:
        raise CalculatorError("the number is too large")
    return value


def _eval(node: ast.AST) -> int | float:
    """Whitelist walk over the syntax tree: any node type not listed here is rejected."""
    match node:
        case ast.Constant(value=v) if type(v) in (int, float):  # bool and complex excluded
            return _check(v)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return _check(-_eval(operand))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BINARY:
            a, b = _eval(left), _eval(right)
            if isinstance(op, ast.Pow) and abs(b) > MAX_EXPONENT:
                raise CalculatorError(
                    f"the exponent must be at most {MAX_EXPONENT} in absolute value"
                )
            result = _BINARY[type(op)](a, b)
            if isinstance(result, complex):  # (-8) ** 0.5
                raise CalculatorError("the result is not a real number")
            return _check(result)
        case _:
            raise CalculatorError(f"not allowed: {type(node).__name__}")


def calculate(expression: str) -> str:
    """Evaluate `expression`; returns the result or an error text (never raises)."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        return f"Error: the expression is longer than {MAX_EXPRESSION_LENGTH} characters"
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        value = _eval(tree.body)
    except CalculatorError as e:
        return f"Error: {e}"
    except ZeroDivisionError:
        return "Error: division by zero"
    except (SyntaxError, ValueError):
        return "Error: invalid expression"
    except (OverflowError, RecursionError, MemoryError):
        return "Error: the number is too large"
    return str(value) if isinstance(value, int) else f"{value:.12g}"


def run_tool(call: ToolCall) -> str:
    """Run a tool call from the model. An unknown tool or bad args is also just a text result."""
    if call.name == CALCULATOR.name:
        expression = call.args.get("expression")
        if not isinstance(expression, str):
            return "Error: the 'expression' argument (a string) is required"
        return calculate(expression)
    return f"Error: unknown tool {call.name!r}"
