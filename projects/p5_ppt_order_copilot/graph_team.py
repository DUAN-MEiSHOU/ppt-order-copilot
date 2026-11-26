"""Durable customer-service, supervisor, and designer order workflow."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agentkit.guard import redact_pii
from .deck import save_deck
from .team import OrderTeam


class OrderState(TypedDict, total=False):
    chat: str
    feedback: str
    output_dir: str
    requirements: dict
    slides: list[dict]
    theme: dict
    trace: list[dict]
    customer_reply: str
    route: str
    status: str
    pptx: str | None
    revision_round: int


class OrderGraph:
    def __init__(self, llm, database: Path):
        self.roles = OrderTeam(llm)
        self.database = Path(database)

    def _ask(self, state: OrderState, role: str, prompt: str, payload: dict) -> tuple[dict, list]:
        self.roles.trace = list(state.get("trace", []))
        answer = self.roles._ask(role, prompt, payload)
        return answer, list(self.roles.trace)

    @staticmethod
    def _reply(answer: dict) -> str:
        content = answer.get("content")
        if isinstance(content, dict):
            reply = answer.get("reply") or content.get("message")
            if reply:
                return str(reply)
            return "\n".join(str(content[key]) for key in ("summary", "next_step")
                             if content.get(key))
        return str(answer.get("reply") or content or answer.get("message") or "")

    def _service(self, state: OrderState) -> dict:
        answer, trace = self._ask(state, "customer_service",
            "Extract requirements: topic, audience, style, pages, deadline, source materials, "
            "revision requests and missing_information. Return requirements object and reply. "
            "Ask only for facts needed to start design. Delivery format defaults to editable PPTX; "
            "an approximate deadline is sufficient to start. Do not quote a price.",
            {"customer_chat": state["chat"], "feedback": state.get("feedback", ""),
             "previous_requirements": state.get("requirements", {}),
             "previous_slides": state.get("slides", [])})
        requirements = answer.get("requirements")
        if not isinstance(requirements, dict):
            raise ValueError("customer_service must return requirements object")
        return {"requirements": requirements, "customer_reply": self._reply(answer),
                "trace": trace}

    def _route(self, state: OrderState) -> dict:
        answer, trace = self._ask(state, "supervisor",
            "Return action='clarify' if topic, audience, pages, promised materials or required "
            "chart data are missing; otherwise action='design'. An approximate deadline is enough "
            "and delivery format defaults to PPTX. Include reason and blocker, one of "
            "topic, audience, pages, promised_materials, chart_data, or null. "
            "Never promise a price or send a message externally.",
            {"requirements": state["requirements"], "customer_reply": state["customer_reply"],
             "feedback": state.get("feedback", "")})
        requirements = state["requirements"]
        missing_fields = any(not requirements.get(field) for field in ("topic", "audience", "pages"))
        blocker = answer.get("blocker")
        missing_material = blocker in ("promised_materials", "chart_data")
        critical_blocker = blocker in ("topic", "audience", "pages")
        action = "clarify" if missing_fields or missing_material or critical_blocker else "design"
        return {"route": action, "status": "needs_clarification" if action == "clarify" else "designing",
                "trace": trace}

    @staticmethod
    def _wait_for_customer(state: OrderState) -> dict:
        reply = interrupt({"customer_reply": state["customer_reply"],
                           "requirements": state["requirements"]})
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("customer reply must be non-empty text")
        clean, _ = redact_pii(reply)
        return {"chat": state["chat"] + "\n顾客补充：" + clean, "feedback": "",
                "status": "processing"}

    def _design(self, state: OrderState) -> dict:
        answer, trace = self._ask(state, "designer",
            "Return theme object with background, text, accent six-digit hex colors and slides "
            "array with title and bullets. Use only supplied facts; obey revision feedback.",
            {"requirements": state["requirements"], "feedback": state.get("feedback", ""),
             "previous_slides": state.get("slides", [])})
        slides = answer.get("slides")
        if (not isinstance(slides, list) or not 1 <= len(slides) <= 60 or
            any(not isinstance(slide, dict) or not isinstance(slide.get("title"), str)
                or not isinstance(slide.get("bullets"), list) for slide in slides)):
            raise ValueError("designer returned invalid slides")
        return {"slides": slides, "theme": answer.get("theme", {}), "trace": trace}

    def _review(self, state: OrderState) -> dict:
        answer, trace = self._ask(state, "supervisor",
            "Review slides against requirements and feedback. Return approved boolean and issues "
            "array. Compare every factual bullet with the customer text and reject unsupported "
            "additions or missing required content.",
            {"requirements": state["requirements"], "feedback": state.get("feedback", ""),
             "customer_chat": state["chat"], "slides": state["slides"]})
        approved = answer.get("approved") is True
        return {"route": "deliver" if approved else "stop",
                "status": "reviewing" if approved else "needs_design_revision",
                "customer_reply": str(answer.get("issues", [])) if not approved else state["customer_reply"],
                "trace": trace}

    def _deliver(self, state: OrderState) -> dict:
        path = Path(state["output_dir"])
        path.mkdir(parents=True, exist_ok=True)
        deck_path = path / f"order_{uuid.uuid4().hex[:10]}.pptx"
        save_deck(state["slides"], deck_path, state.get("theme"))
        answer, trace = self._ask(state, "customer_service",
            "Return reply: say an editable PPT draft is ready, summarize it and invite specific "
            "revision requests. Do not claim it was sent or promise a price.",
            {"requirements": state["requirements"],
             "slide_titles": [slide["title"] for slide in state["slides"]],
             "feedback": state.get("feedback", "")})
        return {"pptx": str(deck_path), "customer_reply": self._reply(answer),
                "status": "draft_ready", "trace": trace}

    def _build(self, checkpointer):
        graph = StateGraph(OrderState)
        for name, node in (("service", self._service), ("route", self._route),
                           ("wait_for_customer", self._wait_for_customer),
                           ("design", self._design), ("review", self._review),
                           ("deliver", self._deliver)):
            graph.add_node(name, node)
        graph.add_edge(START, "service")
        graph.add_edge("service", "route")
        graph.add_conditional_edges("route", lambda s: s["route"],
                                    {"clarify": "wait_for_customer", "design": "design"})
        graph.add_edge("wait_for_customer", "service")
        graph.add_edge("design", "review")
        graph.add_conditional_edges("review", lambda s: s["route"],
                                    {"deliver": "deliver", "stop": END})
        graph.add_edge("deliver", END)
        return graph.compile(checkpointer=checkpointer)

    def _invoke(self, thread_id: str, input_state) -> dict:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        config = {"configurable": {"thread_id": thread_id}}
        with SqliteSaver.from_conn_string(str(self.database)) as checkpointer:
            graph = self._build(checkpointer)
            state = graph.invoke(input_state, config=config)
            if "__interrupt__" in state:
                state = {key: value for key, value in state.items() if key != "__interrupt__"}
            path = Path(state["output_dir"]) / f"order_{uuid.uuid4().hex[:10]}.json"
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {**state, "thread_id": thread_id, "state_file": str(path)}

    def start(self, chat: str, output_dir: Path, thread_id: str | None = None) -> dict:
        thread_id = thread_id or uuid.uuid4().hex
        if self.database.exists():
            config = {"configurable": {"thread_id": thread_id}}
            with SqliteSaver.from_conn_string(str(self.database)) as saver:
                if self._build(saver).get_state(config).values:
                    raise ValueError("order thread already exists")
        clean, _ = redact_pii(chat)
        return self._invoke(thread_id, {"chat": clean, "feedback": "",
                                        "output_dir": str(Path(output_dir).resolve()),
                                        "trace": [], "revision_round": 0, "status": "processing"})

    def resume(self, thread_id: str, customer_message: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            snapshot = self._build(saver).get_state(config)
        if "wait_for_customer" not in snapshot.next:
            raise ValueError("order is not waiting for customer information")
        return self._invoke(thread_id, Command(resume=customer_message))

    def revise(self, thread_id: str, feedback: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            snapshot = self._build(saver).get_state(config)
        state = snapshot.values
        if state.get("status") not in ("draft_ready", "needs_design_revision"):
            raise ValueError("order is not ready for revision")
        clean, _ = redact_pii(feedback)
        return self._invoke(thread_id, {"feedback": clean,
                                        "revision_round": state.get("revision_round", 0) + 1,
                                        "status": "processing"})
