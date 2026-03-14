"""Lightweight voice-enabled calculator backend.

This version removes server-side microphone/text-to-speech dependencies and
relies on the browser for voice capture. The backend focuses solely on safely
evaluating math expressions sent from the client.
"""

from __future__ import annotations

import ast
import operator
import re
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Map text phrases to math operators; ordered longest-first for clean replaces.
PHRASE_REPLACEMENTS = [
    ("to the power of", "**"),
    ("raised to", "**"),
    ("power", "**"),
    ("divided by", "/"),
    ("divide by", "/"),
    ("over", "/"),
    ("times", "*"),
    ("multiplied by", "*"),
    ("multiply by", "*"),
    ("into", "*"),
    ("x", "*"),
    ("plus", "+"),
    ("add", "+"),
    ("minus", "-"),
    ("negative", "-"),
]

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

ALLOWED_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

ALLOWED_UNARY_OPS = {
    ast.UAdd: lambda x: x,
    ast.USub: operator.neg,
}


def _words_to_numbers(text: str) -> str:
    tokens = text.split()
    converted = [str(NUMBER_WORDS.get(tok, tok)) for tok in tokens]
    return " ".join(converted)


def normalize_command(command: str) -> str:
    """Convert spoken text to a math-ready expression string."""

    cleaned = command.lower()
    # Remove filler words that speech recognition often adds.
    cleaned = re.sub(r"\b(what is|calculate|solve|equals?)\b", "", cleaned)
    cleaned = _words_to_numbers(cleaned)

    for phrase, symbol in sorted(PHRASE_REPLACEMENTS, key=lambda x: len(x[0]), reverse=True):
        pattern = rf"\b{re.escape(phrase)}\b"
        cleaned = re.sub(pattern, f" {symbol} ", cleaned)

    # Strip any character that is not a digit, operator, dot, space, or parenthesis.
    cleaned = re.sub(r"[^0-9\+\-\*/\*\*\.\(\)\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def safe_eval(expression: str):
    """Evaluate a simple math expression safely using AST."""

    if not expression:
        raise ValueError("No expression detected.")
    if len(expression) > 200:
        raise ValueError("Expression is too long.")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Only numbers are allowed.")
        if isinstance(node, ast.Num):  # Py<3.8 compatibility
            return node.n
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BIN_OPS:
            return ALLOWED_BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPS:
            return ALLOWED_UNARY_OPS[type(node.op)](_eval(node.operand))
        raise ValueError("Unsupported expression. Use numbers with +, -, *, /, or **.")

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid math expression.") from exc

    result = _eval(parsed)
    return result


@app.route("/")
def home():
    return render_template("index.html")


@app.post("/calculate")
def calculate_route():
    data = request.get_json(silent=True) or {}
    command = str(data.get("command", "")).strip()

    try:
        expression = normalize_command(command)
        result = safe_eval(expression)
    except ValueError as exc:
        return jsonify({"command": command, "error": str(exc)}), 400
    except ZeroDivisionError:
        return jsonify({"command": command, "error": "Cannot divide by zero."}), 400

    return jsonify({"command": command, "expression": expression, "result": result})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
