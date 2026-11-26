"""Pluggable LLM layer.

The rest of the codebase only depends on `BaseLLM.chat`, so the *same* agent loop
runs against a real OpenAI-compatible endpoint (DeepSeek / OpenAI / Ollama / vLLM)
or against a deterministic scripted policy used for offline demos and evals.

No third-party SDK: the HTTP client uses urllib from the standard library.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

CTX = ssl.create_default_context()


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})
    model: str = "unknown"
    raw: dict[str, Any] | None = None

    @property
    def finished(self) -> bool:
        return not self.tool_calls


class BaseLLM:
    name = "base"

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.0, json_mode: bool = False) -> LLMResponse:
        raise NotImplementedError

    def chat_json(self, messages: list[dict], hint: str = "", temperature: float = 0.0) -> Any:
        """Structured output with a repair round-trip (a tiny, explicit version)."""
        msgs = list(messages)
        if hint:
            msgs = [{"role": "system", "content": hint}] + msgs
        resp = self.chat(msgs, temperature=temperature, json_mode=True)
        parsed = _extract_json(resp.content or "")
        if parsed is not None:
            return parsed
        repair = msgs + [
            {"role": "assistant", "content": resp.content or ""},
            {"role": "user", "content": "Your previous reply was not valid JSON. "
                                        "Reply with ONLY a JSON object, no prose, no code fences."},
        ]
        return _extract_json(self.chat(repair, temperature=temperature, json_mode=True).content or "")


def _extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _rough_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars/token for English, ~1.5 chars/token for CJK."""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return max(1, int(len(text) / 4 + cjk * 0.4))


class OpenAICompatibleLLM(BaseLLM):
    """Any endpoint speaking the OpenAI chat-completions + function-calling dialect."""

    name = "openai-compatible"

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: int = 60, max_retries: int = 2):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or
                         "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY") or ""
        self.model = model or os.getenv("LLM_MODEL") or "deepseek-chat"
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.0, json_mode: bool = False) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    self.base_url + "/chat/completions", data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout, context=CTX) as resp:
                    data = json.load(resp)
                msg = data["choices"][0]["message"]
                calls = []
                for c in msg.get("tool_calls") or []:
                    fn = c.get("function", {})
                    args = fn.get("arguments") or "{}"
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    calls.append(ToolCall(id=c.get("id") or uuid.uuid4().hex[:8],
                                          name=fn.get("name", ""), arguments=args))
                usage = data.get("usage") or {}
                return LLMResponse(
                    content=msg.get("content"), tool_calls=calls,
                    usage={"prompt_tokens": usage.get("prompt_tokens", 0),
                           "completion_tokens": usage.get("completion_tokens", 0)},
                    model=self.model, raw=data)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                last_error = RuntimeError(f"HTTP {exc.code}: {detail}")
                if exc.code < 500 and exc.code not in (408, 429):
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after {self.max_retries + 1} attempts: {last_error}")


class ScriptedLLM(BaseLLM):
    """Deterministic test double.

    A `policy(messages, ctx) -> dict` decides the next action. It can return:
      {"tool_calls": [{"name": "...", "arguments": {...}}]}
      {"content": "final answer"}
      {"json": {...}}                     # structured final answer
    Keeping the policy in the *project* makes the offline demo a readable,
    fully reproducible execution of the real agent loop (not a mocked result).
    """

    name = "scripted"

    def __init__(self, policy: Callable[[list[dict], dict], dict],
                 model: str = "scripted-policy-v1", ctx: dict | None = None):
        self.policy = policy
        self.model = model
        self.ctx = ctx if ctx is not None else {}

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.0, json_mode: bool = False) -> LLMResponse:
        action = self.policy(messages, self.ctx) or {}
        serialized = json.dumps(messages, ensure_ascii=False, default=str)
        prompt_tokens = _rough_tokens(serialized)
        if action.get("tool_calls"):
            calls = [ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=c["name"],
                              arguments=c.get("arguments", {}))
                     for c in action["tool_calls"]]
            content = action.get("content")
            return LLMResponse(content=content, tool_calls=calls,
                               usage={"prompt_tokens": prompt_tokens,
                                      "completion_tokens": _rough_tokens(json.dumps(action, ensure_ascii=False))},
                               model=self.model, raw={"scripted": True})
        if "json" in action:
            text = json.dumps(action["json"], ensure_ascii=False)
        else:
            text = action.get("content") or json.dumps(action, ensure_ascii=False)
        return LLMResponse(content=text,
                           usage={"prompt_tokens": prompt_tokens,
                                  "completion_tokens": _rough_tokens(text)},
                           model=self.model, raw={"scripted": True})


def load_api_llm() -> OpenAICompatibleLLM | None:
    """Return a real LLM if credentials exist, otherwise None (caller falls back to scripted)."""
    if os.getenv("LLM_API_KEY") or os.getenv("LLM_BASE_URL", "").startswith("http://"):
        return OpenAICompatibleLLM()
    return None


def load_dotenv(path: str | None = None) -> None:
    """Minimal .env loader so we don't need python-dotenv for the core path."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    env = Path(path) if path else root / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
