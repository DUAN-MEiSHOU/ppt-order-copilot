"""Tool contracts: JSON-Schema generation, argument validation, least-privilege gates.

A well-described tool is half of agent reliability. This module makes the tool
boundary explicit and testable instead of hiding it inside a framework.
"""
from __future__ import annotations

import inspect
import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def as_message_content(self, max_chars: int = 6000) -> str:
        """Tool output is DATA, never instructions. Wrap and truncate it."""
        payload = {"ok": self.ok}
        if self.ok:
            payload["result"] = self.data
        else:
            payload["error"] = self.error
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > max_chars:
            text = text[:max_chars] + "...[truncated]"
        return "<tool_output>" + text + "</tool_output>"


class Tool:
    def __init__(self, func: Callable, name: str | None = None,
                 description: str | None = None, parameters: dict | None = None,
                 permission: str = "read", side_effect: bool = False,
                 timeout_s: float | None = None):
        self.func = func
        self.name = name or func.__name__
        self.description = description or (inspect.getdoc(func) or "").strip() or self.name
        self.parameters = parameters or _schema_from_signature(func)
        self.permission = permission          # read | write | external
        self.side_effect = side_effect        # needs human approval when True
        self.timeout_s = timeout_s

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def validate(self, args: dict) -> str | None:
        return _validate_args(args, self.parameters)

    def run(self, args: dict) -> ToolResult:
        started = time.perf_counter()
        try:
            problem = self.validate(args)
            if problem:
                return ToolResult(False, error=f"invalid arguments: {problem}",
                                  duration_ms=(time.perf_counter() - started) * 1000)
            out = self.func(**args) if args else self.func()
            return ToolResult(True, data=out, duration_ms=(time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001 - tool errors must never kill the loop
            return ToolResult(False, error=f"{type(exc).__name__}: {exc}",
                              duration_ms=(time.perf_counter() - started) * 1000)


def _python_type(t: str) -> str:
    return {"str": "string", "int": "integer", "float": "number",
            "bool": "boolean", "list": "array", "dict": "object"}.get(t, "string")


def _schema_from_signature(func: Callable) -> dict:
    sig = inspect.signature(func)
    props: dict[str, dict] = {}
    required: list[str] = []
    for pname, p in sig.parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        ann = p.annotation
        if isinstance(ann, str):
            t = _python_type(ann)
        elif ann is int:
            t = "integer"
        elif ann is float:
            t = "number"
        elif ann is bool:
            t = "boolean"
        elif getattr(ann, "__origin__", None) is list:
            t = "array"
        else:
            t = "string"
        prop: dict[str, Any] = {"type": t, "description": f"Parameter `{pname}`"}
        if t == "array":
            prop["items"] = {"type": "string"}
        props[pname] = prop
        if p.default is inspect.Parameter.empty:
            required.append(pname)
    return {"type": "object", "properties": props, "required": required}


def _validate_args(args: dict, schema: dict) -> str | None:
    if not isinstance(args, dict):
        return "arguments must be an object"
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            return f"missing required field '{key}'"
    for key, value in args.items():
        if key not in props:
            return f"unknown field '{key}' (allowed: {', '.join(props) or 'none'})"
        expected = props[key].get("type", "string")
        ok = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
        }.get(expected, lambda v: True)(value)
        if not ok:
            return f"field '{key}' must be {expected}, got {type(value).__name__}"
        if "enum" in props[key] and value not in props[key]["enum"]:
            return f"field '{key}' must be one of {props[key]['enum']}"
    return None


class PermissionError_(Exception):
    pass


class ToolRegistry:
    """Registry + enforcement point for tool permissions."""

    def __init__(self, allowed_permissions: tuple[str, ...] = ("read",)):
        self._tools: dict[str, Tool] = {}
        self.allowed_permissions = tuple(allowed_permissions)
        self.call_log: list[dict] = []

    def register(self, func: Callable | None = None, **kwargs) -> Callable:
        def decorator(f: Callable):
            self.add(Tool(f, **kwargs))
            return f
        return decorator(func) if func else decorator

    def add(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self, only: list[str] | None = None) -> list[dict]:
        names = only or self.names()
        return [self._tools[n].schema() for n in names if n in self._tools]

    def call(self, name: str, args: dict, *, allow_side_effect: bool = False) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            result = ToolResult(False, error=f"unknown tool '{name}'. Available: {', '.join(self.names())}")
        elif tool.permission not in self.allowed_permissions:
            result = ToolResult(False, error=f"permission denied: tool '{name}' needs '{tool.permission}', "
                                            f"agent is limited to {self.allowed_permissions}")
        elif tool.side_effect and not allow_side_effect:
            result = ToolResult(False, error=f"tool '{name}' has side effects and requires human approval")
        else:
            result = tool.run(args)
        self.call_log.append({"tool": name, "args": args, "ok": result.ok,
                              "error": result.error, "duration_ms": round(result.duration_ms, 2)})
        return result

    def describe(self) -> str:
        lines = []
        for name, t in self._tools.items():
            lines.append(f"- {name}({', '.join(t.parameters.get('properties', {}))}) "
                         f"[{t.permission}{'+side_effect' if t.side_effect else ''}]: {t.description}")
        return "\n".join(lines)
