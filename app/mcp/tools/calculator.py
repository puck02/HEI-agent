"""
Calculator tool — evaluate mathematical expressions safely.
"""

from __future__ import annotations

import math
import re


def calculate(expression: str) -> str:
    """
    Safely evaluate a math expression.
    Supports basic arithmetic, power, sqrt, common math functions.
    """
    # Clean the expression
    expr = expression.strip()

    # Whitelist of allowed names for eval
    allowed_names = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": pow,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "pi": math.pi,
        "e": math.e,
        "ceil": math.ceil,
        "floor": math.floor,
    }

    # Security: block dangerous builtins
    forbidden = re.compile(r"(import|exec|eval|open|os\.|sys\.|__)", re.IGNORECASE)
    if forbidden.search(expr):
        return "错误：表达式包含不允许的操作"

    try:
        result = eval(expr, {"__builtins__": {}}, allowed_names)
        if isinstance(result, float):
            # Format nicely
            if result == int(result):
                return str(int(result))
            return f"{result:.4f}".rstrip("0").rstrip(".")
        return str(result)
    except ZeroDivisionError:
        return "错误：除以零"
    except Exception as e:
        return f"计算错误：{e}"
