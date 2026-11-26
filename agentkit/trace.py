"""Tracing / observability for agent runs.

Every LLM call and every tool call becomes a span. This is deliberately a small
in-house implementation so it has zero dependencies and can ship with the repo;
in production you would emit the same shape to OpenTelemetry / Langfuse.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Rough USD prices per 1M tokens; overridable via env, used for cost estimates only.
DEFAULT_PRICING = {"input_per_mtok": 0.28, "output_per_mtok": 0.42}


@dataclass
class Span:
    span_id: str
    parent_id: str | None
    kind: str                     # llm | tool | node | gate | guard | retriever
    name: str
    started_at: float
    duration_ms: float = 0.0
    status: str = "ok"            # ok | error | blocked
    inputs: Any = None
    outputs: Any = None
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None
    meta: dict = field(default_factory=dict)

    def cost_usd(self, pricing: dict | None = None) -> float:
        p = pricing or DEFAULT_PRICING
        return (self.tokens_in * p["input_per_mtok"] + self.tokens_out * p["output_per_mtok"]) / 1_000_000


class Trace:
    def __init__(self, name: str, run_id: str | None = None):
        self.name = name
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.started_at = time.time()
        self.spans: list[Span] = []
        self._stack: list[str] = []
        self.metadata: dict[str, Any] = {}

    def start(self, kind: str, name: str, inputs: Any = None, **meta) -> Span:
        span = Span(span_id=uuid.uuid4().hex[:10],
                    parent_id=self._stack[-1] if self._stack else None,
                    kind=kind, name=name, started_at=time.time(),
                    inputs=_clip(inputs), meta=meta)
        self.spans.append(span)
        self._stack.append(span.span_id)
        return span

    def end(self, span: Span, outputs: Any = None, *, status: str = "ok",
            error: str | None = None, tokens_in: int = 0, tokens_out: int = 0) -> None:
        span.duration_ms = (time.time() - span.started_at) * 1000
        span.outputs = _clip(outputs)
        span.status = status
        span.error = error
        span.tokens_in = tokens_in
        span.tokens_out = tokens_out
        if self._stack and self._stack[-1] == span.span_id:
            self._stack.pop()

    def span(self, kind: str, name: str, inputs: Any = None, **meta):
        """Context manager with a permissive failure path."""
        return _SpanContext(self, kind, name, inputs, **meta)

    def totals(self) -> dict[str, Any]:
        llm = [s for s in self.spans if s.kind == "llm"]
        tools = [s for s in self.spans if s.kind == "tool"]
        return {
            "run_id": self.run_id,
            "duration_ms": round((time.time() - self.started_at) * 1000, 1),
            "spans": len(self.spans),
            "llm_calls": len(llm),
            "tool_calls": len(tools),
            "tool_errors": sum(1 for s in tools if s.status != "ok"),
            "tokens_in": sum(s.tokens_in for s in self.spans),
            "tokens_out": sum(s.tokens_out for s in self.spans),
            "est_cost_usd": round(sum(s.cost_usd() for s in self.spans), 6),
            "blocked": sum(1 for s in self.spans if s.status == "blocked"),
        }

    def to_dict(self) -> dict:
        return {"name": self.name, "run_id": self.run_id, "started_at": self.started_at,
                "metadata": self.metadata, "totals": self.totals(),
                "spans": [asdict(s) for s in self.spans]}

    def to_markdown(self) -> str:
        t = self.totals()
        lines = [f"# Trace `{self.run_id}` — {self.name}", "",
                 "| # | kind | name | status | ms | tokens |", "|---:|---|---|---|---:|---:|"]
        for i, s in enumerate(self.spans, 1):
            lines.append(f"| {i} | {s.kind} | `{s.name}` | {s.status} | {s.duration_ms:.1f} | "
                         f"{s.tokens_in}+{s.tokens_out} |")
        lines += ["", f"**Totals**: {t['llm_calls']} LLM calls, {t['tool_calls']} tool calls, "
                  f"{t['tokens_in'] + t['tokens_out']} tokens, ~${t['est_cost_usd']}, "
                  f"{t['duration_ms']} ms, {t['blocked']} blocked.", ""]
        return "\n".join(lines)


class _SpanContext:
    def __init__(self, trace: Trace, kind: str, name: str, inputs: Any, **meta):
        self.trace, self.kind, self.name, self.inputs, self.meta = trace, kind, name, inputs, meta
        self.span: Span | None = None
        self.error: str | None = None
        self.status = "ok"
        self.outputs: Any = None
        self.tok_in = self.tok_out = 0

    def __enter__(self):
        self.span = self.trace.start(self.kind, self.name, self.inputs, **self.meta)
        return self

    def set(self, outputs: Any = None, *, status: str = "ok", error: str | None = None,
            tokens_in: int = 0, tokens_out: int = 0):
        self.outputs, self.status, self.error = outputs, status, error
        self.tok_in, self.tok_out = tokens_in, tokens_out

    def __exit__(self, exc_type, exc, tb):
        if exc and self.status == "ok":
            self.status, self.error = "error", f"{exc_type.__name__}: {exc}"
        if self.span:
            self.trace.end(self.span, self.outputs, status=self.status, error=self.error,
                           tokens_in=self.tok_in, tokens_out=self.tok_out)
        return False


def _clip(value: Any, limit: int = 1500) -> Any:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "...[clipped]"


class Tracer:
    def __init__(self, out_dir: str | Path | None = None, persist: bool = True):
        root = Path(__file__).resolve().parents[1]
        self.out_dir = Path(out_dir) if out_dir else root / "runs"
        self.persist = persist
        if persist:
            self.out_dir.mkdir(parents=True, exist_ok=True)
        self.traces: list[Trace] = []

    def new(self, name: str) -> Trace:
        t = Trace(name)
        self.traces.append(t)
        return t

    def save(self, trace: Trace) -> Path:
        path = self.out_dir / f"{trace.run_id}.json"
        path.write_text(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
        return path

    def summary(self) -> dict:
        if not self.traces:
            return {"runs": 0}
        totals = [t.totals() for t in self.traces]
        return {
            "runs": len(totals),
            "llm_calls": sum(x["llm_calls"] for x in totals),
            "tool_calls": sum(x["tool_calls"] for x in totals),
            "tool_errors": sum(x["tool_errors"] for x in totals),
            "tokens": sum(x["tokens_in"] + x["tokens_out"] for x in totals),
            "est_cost_usd": round(sum(x["est_cost_usd"] for x in totals), 6),
            "blocked": sum(x["blocked"] for x in totals),
        }
