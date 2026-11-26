"""agentkit — a dependency-free agent engineering core used by every project.

Modules:
  llm    pluggable LLM (OpenAI-compatible HTTP / deterministic scripted policy)
  tools  tool registry, JSON Schema, argument validation, least privilege
  loop   hand-written ReAct-style agent loop with budgets and error recovery
  state  stateful workflow graph with conditional edges, checkpoint, HITL
  rag    BM25 + TF-IDF hybrid retrieval, RRF, MMR, citations, IR metrics
  guard  SQL allow-list, prompt-injection detection, PII redaction, policy gate
  trace  spans, token/cost accounting, JSON traces and Markdown export
  eval   versioned eval sets, numeric metrics, regression gate, HTML reports
"""
from .guard import assess_ticket, detect_prompt_injection, enforce_limit, redact_pii, sanitize_external_text, validate_sql
from .llm import BaseLLM, LLMResponse, OpenAICompatibleLLM, ScriptedLLM, ToolCall, load_api_llm, load_dotenv
from .loop import AgentConfig, AgentLoop, AgentResult
from .rag import (Chunk, Corpus, Hit, HybridRetriever, expand_query, expansion_terms,
                  groundedness, retrieval_metrics, tokenize)
from .state import Graph, GraphResult, Interrupt
from .tools import Tool, ToolRegistry, ToolResult
from .trace import Span, Trace, Tracer

__all__ = [
    "BaseLLM", "LLMResponse", "OpenAICompatibleLLM", "ScriptedLLM", "ToolCall",
    "load_api_llm", "load_dotenv", "Tool", "ToolRegistry", "ToolResult",
    "AgentConfig", "AgentLoop", "AgentResult", "Graph", "GraphResult", "Interrupt",
    "Corpus", "Chunk", "Hit", "HybridRetriever", "groundedness", "retrieval_metrics",
    "tokenize", "expand_query", "expansion_terms",
    "validate_sql", "enforce_limit", "detect_prompt_injection", "redact_pii",
    "assess_ticket", "sanitize_external_text", "Trace", "Span", "Tracer",
]
__version__ = "1.0.0"
