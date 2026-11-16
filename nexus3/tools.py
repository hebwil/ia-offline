"""Ferramentas com allowlist, desligadas por padrão.

Diferente da v2.0 (que podia expor built-in tools do llama-server), aqui
nenhuma ferramenta de sistema de arquivos ou shell é disponibilizada ao
modelo. As duas únicas ferramentas são determinísticas e locais.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "document_search",
            "description": "Busca trechos nos documentos indexados pelo usuário neste projeto.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Avalia uma expressão aritmética simples com números e operadores + - * / ( ).",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]

_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
}


def calculator(expression: str) -> str:
    try:
        node = ast.parse(expression, mode="eval").body
    except (SyntaxError, ValueError) as exc:
        return f"Expressão inválida: {type(exc).__name__}"

    def evaluate(item: ast.AST) -> float:
        if isinstance(item, ast.Constant) and isinstance(item.value, (int, float)):
            return float(item.value)
        if isinstance(item, ast.BinOp) and type(item.op) in _OPERATORS:
            return float(_OPERATORS[type(item.op)](evaluate(item.left), evaluate(item.right)))
        if isinstance(item, ast.UnaryOp) and type(item.op) in _OPERATORS:
            return float(_OPERATORS[type(item.op)](evaluate(item.operand)))
        raise ValueError("Expressão contém operação não permitida.")

    try:
        value = evaluate(node)
        return f"{value:.10g}"
    except ValueError as exc:
        return f"Expressão inválida ou não permitida: {exc}"
    except (ZeroDivisionError, OverflowError) as exc:
        return f"Não foi possível calcular: {type(exc).__name__}"


class ToolRuntime:
    def __init__(self, config, store=None):
        self.config = config
        self.store = store
        allowed = set(config.get("tools.allowlist") or [])
        self.available = [t for t in TOOL_DEFINITIONS if t["function"]["name"] in allowed]

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("tools.enabled"))

    def definitions(self) -> list[dict[str, Any]]:
        return self.available if self.enabled else []

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if not self.enabled:
            return "Ferramentas desativadas nesta instalação."
        if name not in {tool["function"]["name"] for tool in self.available}:
            return f"Ferramenta não autorizada: {name}"
        if name == "calculator":
            return calculator(str(arguments.get("expression", "")))
        if name == "document_search" and self.store:
            results = self.store.search(str(arguments.get("query", "")), int(arguments.get("top_k", 5)))
            return "\n\n".join(f"[{r.citation()}]\n{r.text}" for r in results) or "Nenhum trecho encontrado."
        return "Ferramenta indisponível no momento."
