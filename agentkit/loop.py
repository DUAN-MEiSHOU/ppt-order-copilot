"""The agent loop, written by hand.

    while step < MAX_STEPS:
        response = llm.chat(messages, tools=TOOLS)
        if not response.tool_calls: return response.text
        for call in response.tool_calls:
            result = registry.call(...)
            messages.append(tool_result(...))
        step += 1
    raise StepLimitExceeded

The point is not to reinvent a framework, but to make the control flow, stop
conditions, error recovery and budgets explicit and testable. Swap `llm` for a
real endpoint and the exact same loop runs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .llm import BaseLLM, LLMResponse
from .tools import ToolRegistry
from .trace import Trace, Tracer


@dataclass
class AgentConfig:
    max_steps: int = 8
    max_tool_calls: int = 14
    max_total_tokens: int = 60_000
    allow_reflection: bool = True
    tool_result_chars: int = 6000


@dataclass
class AgentResult:
    answer: str
    status: str                        # done | step_limit | budget_exceeded | error
    steps: int = 0
    tool_calls: int = 0
    messages: list[dict] = field(default_factory=list)
    trace: Trace | None = None
    error: str | None = None

    @property
    def totals(self) -> dict:
        return self.trace.totals() if self.trace else {}


class AgentLoop:
    def __init__(self, llm: BaseLLM, registry: ToolRegistry, system_prompt: str,
                 tracer: Tracer | None = None, config: AgentConfig | None = None,
                 allowed_tools: list[str] | None = None,
                 on_observation: Any = None):
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.tracer = tracer or Tracer(persist=False)
        self.config = config or AgentConfig()
        self.allowed_tools = allowed_tools
        self.on_observation = on_observation   # optional callback(tool_name, result)

    def run(self, question: str, *, context: dict | None = None,
            extra_system: str = "") -> AgentResult:
        cfg = self.config
        trace = self.tracer.new(self.llm.name + ":agent-loop")
        trace.metadata.update({"question": question[:300], "llm": self.llm.name,
                               "context_keys": list((context or {}).keys())})
        system = self.system_prompt + (("\n\n" + extra_system) if extra_system else "")
        messages: list[dict] = [{"role": "system", "content": system},
                                {"role": "user", "content": question}]
        schemas = self.registry.schemas(self.allowed_tools)
        steps = tool_calls = tokens = 0
        recent_signatures: list[str] = []
        last_error: str | None = None

        while steps < cfg.max_steps:
            steps += 1
            try:
                with self.tracer_span(trace, "llm", f"step-{steps}", {"messages": len(messages)}) as sp:
                    response: LLMResponse = self.llm.chat(messages, tools=schemas)
                    sp.set({"content_snippet": (response.content or "")[:200],
                            "tool_calls": [c.name for c in response.tool_calls]},
                           tokens_in=response.usage.get("prompt_tokens", 0),
                           tokens_out=response.usage.get("completion_tokens", 0))
            except Exception as exc:  # noqa: BLE001
                return self._finish("", "error", steps, tool_calls, messages, trace, str(exc))

            tokens += sum(response.usage.values())
            if tokens > cfg.max_total_tokens:
                return self._finish(response.content or "", "budget_exceeded", steps, tool_calls,
                                    messages, trace, "token budget exhausted")

            if not response.tool_calls:
                answer = response.content or ""
                if not answer and messages[-1]["role"] == "tool":
                    answer = "No textual answer was produced. Last tool output:\n" + messages[-1]["content"][:800]
                return self._finish(answer, "done", steps, tool_calls, messages, trace)

            if tool_calls + len(response.tool_calls) > cfg.max_tool_calls:
                return self._finish(response.content or "", "budget_exceeded", steps, tool_calls,
                                    messages, trace, "tool-call budget exhausted")

            # Record the assistant turn (including its tool calls) so the transcript is replayable.
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name,
                                  "arguments": json.dumps(c.arguments, ensure_ascii=False)}}
                    for c in response.tool_calls]
            messages.append(assistant_msg)

            for call in response.tool_calls:
                tool_calls += 1
                with self.tracer_span(trace, "tool", call.name, call.arguments) as sp:
                    result = self.registry.call(call.name, call.arguments)
                    sp.set({"ok": result.ok, "error": result.error,
                            "preview": str(result.data)[:250] if result.ok else None},
                           status="ok" if result.ok else "error", error=result.error)
                if self.on_observation:
                    self.on_observation(call.name, result)
                if not result.ok:
                    last_error = result.error
                content = result.as_message_content(cfg.tool_result_chars)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

                signature = json.dumps([call.name, call.arguments], ensure_ascii=False, sort_keys=True)
                recent_signatures.append(signature)

            # Loop detection: identical consecutive tool calls usually means the model is stuck.
            if (cfg.allow_reflection and len(recent_signatures) >= 2
                    and recent_signatures[-1] == recent_signatures[-2]):
                messages.append({"role": "system", "content":
                    "You just repeated the exact same tool call. Do not repeat it. "
                    "Either change the arguments, use a different tool, or give your final answer."})
                trace.spans[-1].meta["reflection_injected"] = True

            if last_error and cfg.allow_reflection:
                # The error text is already in the tool message; make the recovery explicit.
                messages.append({"role": "system", "content":
                    "A tool returned an error. Read the error, fix the arguments or SQL, and retry. "
                    "If it cannot be fixed, explain the limitation in your final answer."})

        return self._finish("", "step_limit", steps, tool_calls, messages, trace,
                            f"stopped after {cfg.max_steps} steps")

    def tracer_span(self, trace: Trace, kind: str, name: str, inputs: Any):
        return trace.span(kind, name, inputs)

    def _finish(self, answer: str, status: str, steps: int, tool_calls: int,
                messages: list[dict], trace: Trace, error: str | None = None) -> AgentResult:
        trace.metadata["final_status"] = status
        if self.tracer.persist:
            self.tracer.save(trace)
        return AgentResult(answer=answer, status=status, steps=steps,
                           tool_calls=tool_calls, messages=messages,
                           trace=trace, error=error)
