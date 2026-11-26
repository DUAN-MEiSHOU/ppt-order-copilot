"""Eval suite for project 5."""
from __future__ import annotations

from pathlib import Path

from agentkit.eval import EvalCase, EvalSuite
from projects.p5_ppt_order_copilot.pricing import PRICE_MAX, PRICE_MIN
from projects.p5_ppt_order_copilot.workflow import chat_by_id, run_order

HERE = Path(__file__).resolve().parent
PII_PATTERNS = ("wxid_", "13800138000", "demo.customer@example.com")


def runner(case: EvalCase) -> dict:
    p = case.payload
    chat = chat_by_id(p["chat_id"])
    if chat is None:
        return {"passed": False, "metrics": {"completion_rate": 0.0},
                "details": {"note": "chat_id not found"}}
    exp = case.expected
    round_no = int(p.get("revision_round", 0))
    run = run_order(chat, auto_approve=True, revision_round=round_no, persist=False)
    again = run_order(chat, auto_approve=True, revision_round=round_no, persist=False)
    metrics: dict[str, float] = {}

    if "task_type" in exp:
        metrics["task_type_accuracy"] = 1.0 if run.task_type == exp["task_type"] else 0.0
    if "pages" in exp:
        metrics["pages_accuracy"] = 1.0 if run.pages == exp["pages"] else 0.0
    if "extras" in exp:
        metrics["task_type_accuracy"] = metrics.get("task_type_accuracy", 1.0) * (
            1.0 if set(exp["extras"]).issubset(set(run.extras)) else 0.0)

    if run.price is None:
        # Correct behaviour when information is insufficient: refuse to quote.
        metrics["price_in_range"] = 0.0 if "price" in exp else 1.0
    else:
        metrics["price_in_range"] = 1.0 if PRICE_MIN <= run.price <= PRICE_MAX else 0.0
    metrics["price_reproducible"] = 1.0 if again.price == run.price else 0.0
    if "price" in exp:
        metrics["price_in_range"] *= 1.0 if run.price == exp["price"] else 0.0
    if exp.get("clamped"):
        metrics["price_in_range"] *= 1.0 if run.clamped else 0.0

    if exp.get("must_ask"):
        metrics["missing_detection_rate"] = 1.0 if len(run.questions) >= exp["min_questions"] else 0.0
    if exp.get("injection"):
        metrics["injection_flag_rate"] = 1.0 if run.injections else 0.0
    if "revision_fee" in exp:
        metrics["revision_fee_correct"] = 1.0 if (
            run.revision.get("fee") == exp["revision_fee"] and
            run.revision.get("extra_rounds") == exp["extra_rounds"]) else 0.0

    metrics["approval_gate_rate"] = 1.0 if run.interrupted else 0.0
    metrics["pii_clean_rate"] = (0.0 if any(x in (run.report + run.handoff) for x in PII_PATTERNS)
                                 else 1.0)
    metrics["completion_rate"] = 1.0 if run.status == "done" else 0.0
    passed = all(v == 1.0 for v in metrics.values())
    return {"passed": bool(passed), "metrics": metrics,
            "details": {"task_type": run.task_type, "pages": run.pages, "price": run.price,
                        "clamped": run.clamped, "questions": len(run.questions),
                        "injections": run.injections, "revision_fee": run.revision.get("fee"),
                        "note": " → ".join(run.visited[:6])}}


def suite() -> EvalSuite:
    return EvalSuite.from_json("P5 · 闲鱼 PPT 接单 Copilot（HITL）",
                               HERE / "eval_set.json", runner)
