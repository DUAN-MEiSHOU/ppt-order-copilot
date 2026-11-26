"""A tiny stateful workflow graph with conditional edges, checkpoints and HITL.

This is the "workflow" half of workflow-vs-agent: the developer owns control
flow. It implements the concepts LangGraph exposes (explicit state, nodes,
conditional edges, interrupts, resume) without requiring the dependency, so the
same project also ships a LangGraph adapter in projects/03_support_swarm.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .trace import Trace, Tracer


@dataclass
class Interrupt:
    """A node asks a human to approve an irreversible / high-risk action."""
    reason: str
    payload: dict = field(default_factory=dict)
    resume_node: str | None = None


@dataclass
class GraphResult:
    state: dict
    status: str                 # done | needs_approval | step_limit | error
    visited: list[str] = field(default_factory=list)
    trace: Trace | None = None
    checkpoint: str | None = None
    interrupt: Interrupt | None = None
    error: str | None = None


class Graph:
    def __init__(self, name: str, max_steps: int = 24):
        self.name = name
        self.max_steps = max_steps
        self.nodes: dict[str, Callable] = {}
        self.edges: dict[str, str] = {}
        self.conditional: dict[str, tuple[Callable, dict[str, str]]] = {}
        self.entry: str | None = None
        self.finish: set[str] = set()
        self.checkpoint_dir = Path(__file__).resolve().parents[1] / "runs" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def add_node(self, name: str, fn: Callable, *, terminal: bool = False) -> "Graph":
        self.nodes[name] = fn
        if terminal:
            self.finish.add(name)
        return self

    def add_edge(self, src: str, dst: str) -> "Graph":
        self.edges[src] = dst
        return self

    def add_conditional_edge(self, src: str, router: Callable[[dict], str],
                             mapping: dict[str, str]) -> "Graph":
        self.conditional[src] = (router, mapping)
        return self

    def set_entry(self, name: str) -> "Graph":
        self.entry = name
        return self

    def _next(self, current: str, state: dict, decision: str | None) -> str | None:
        if decision and decision in self.nodes:
            return decision
        if current in self.conditional:
            router, mapping = self.conditional[current]
            key = router(state)
            if key not in mapping:
                raise KeyError(f"router at '{current}' returned '{key}'; expected {list(mapping)}")
            return mapping[key]
        return self.edges.get(current)

    def run(self, state: dict, *, ctx: dict | None = None,
            tracer: Tracer | None = None, start_node: str | None = None,
            visited: list[str] | None = None, checkpoint_id: str | None = None) -> GraphResult:
        tracer = tracer or Tracer(persist=False)
        trace = tracer.new(self.name)
        ctx = ctx or {}
        current = start_node or self.entry
        if current is None:
            raise ValueError("graph has no entry node")
        visited = list(visited or [])
        error = None

        while current and current not in self.finish and len(visited) < self.max_steps:
            if current not in self.nodes:
                return GraphResult(state, "error", visited, trace, error=f"unknown node '{current}'")
            visited.append(current)
            try:
                with trace.span("node", current, {"state_keys": list(state)}) as sp:
                    out = self.nodes[current](state, ctx)
                    patch: dict = {}
                    decision: str | None = None
                    if isinstance(out, Interrupt):
                        cp = self._write_checkpoint(state, visited, current, out, checkpoint_id)
                        sp.set({"interrupt": out.reason}, status="blocked")
                        return GraphResult(state, "needs_approval", visited, trace, cp, out)
                    if isinstance(out, tuple):
                        patch, decision = out[0], out[1]
                    elif isinstance(out, dict):
                        patch = out
                    state.update(patch)
                    sp.set({"patch_keys": list(patch), "decision": decision})
            except Exception as exc:  # noqa: BLE001
                error = f"node '{current}' failed: {type(exc).__name__}: {exc}"
                return GraphResult(state, "error", visited, trace, error=error)
            current = self._next(current, state, decision)

        if current in self.finish:
            visited.append(current)
            with trace.span("node", current, {"state_keys": list(state)}) as sp:
                out = self.nodes[current](state, ctx)
                if isinstance(out, dict):
                    state.update(out)
                sp.set({"terminal": True})
            current = None
        status = "done" if current is None else "step_limit"
        if tracer.persist:
            tracer.save(trace)
        return GraphResult(state, status, visited, trace)

    def _write_checkpoint(self, state: dict, visited: list[str], node: str,
                          interrupt: Interrupt, checkpoint_id: str | None) -> str:
        import uuid
        cid = checkpoint_id or uuid.uuid4().hex[:12]
        path = self.checkpoint_dir / f"{cid}.json"
        path.write_text(json.dumps({
            "graph": self.name, "node": node, "visited": visited, "state": state,
            "interrupt": {"reason": interrupt.reason, "payload": interrupt.payload,
                          "resume_node": interrupt.resume_node},
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(path)

    def resume(self, checkpoint: str | Path, *, approved: bool,
               reviewer: str = "human", tracer: Tracer | None = None,
               ctx: dict | None = None) -> GraphResult:
        """Resume an interrupted run after a human decision."""
        data = json.loads(Path(checkpoint).read_text(encoding="utf-8"))
        state = data["state"]
        state["approval"] = {"approved": approved, "reviewer": reviewer,
                             "reason": data["interrupt"]["reason"]}
        visited = data["visited"]
        node = data["node"]
        start = data["interrupt"].get("resume_node")
        if start is None:
            # Continue with the edge that follows the interrupting node.
            start = self.edges.get(node) or (self.conditional.get(node) or (None, {}))[1].get(
                (self.conditional.get(node) or (lambda s: "", {}))[0](state))
        if start is None:
            start = self.entry
        result = self.run(state, ctx=ctx, tracer=tracer, start_node=start,
                          visited=visited, checkpoint_id=Path(checkpoint).stem)
        Path(checkpoint).unlink(missing_ok=True)
        return result

    def mermaid(self) -> str:
        lines = ["flowchart TD"]
        for a, b in self.edges.items():
            lines.append(f"  {a} --> {b}")
        for src, (_, mapping) in self.conditional.items():
            for label, dst in mapping.items():
                lines.append(f"  {src} -->|{label}| {dst}")
        if self.entry:
            lines.append(f"  start([USER]) --> {self.entry}")
        for f in self.finish:
            lines.append(f"  {f} --> finish([DONE])")
        return "\n".join(lines)
