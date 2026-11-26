"""Project 5 — Xianyu/WeChat PPT-order copilot (human-in-the-loop).

SCOPE DECISION (documented, deliberate):
  Xianyu (Goofish) exposes no public personal-developer messaging/order API,
  and personal WeChat accounts have no compliant bot API. Scraping / reversing /
  simulating a logged-in client would be unstable and risky. So this project
  DOES NOT touch any platform API. Chat transcripts are IMPORTED; the agent owns
  everything after that; a human copies the generated wording into the chat.

Workflow: intake(redact) -> extract -> clarify -> quote -> [HUMAN approves the
price] -> production brief -> revision policy -> handoff wording -> report.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentkit import (Graph, GraphResult, Interrupt, Tracer, detect_prompt_injection,  # noqa: E402
                      load_api_llm, load_dotenv, redact_pii)
from projects.p5_ppt_order_copilot.pricing import (FREE_REVISIONS, PRICE_MAX,  # noqa: E402
                                                   PRICE_MIN, Requirements, clarify,
                                                   draft_handoff, extract_requirements,
                                                   quote, revision_policy)

CHATS = ROOT / "data" / "ppt_chats_sample.json"


def load_chats() -> list[dict]:
    return json.loads(CHATS.read_text(encoding="utf-8"))["chats"]


def chat_by_id(chat_id: str) -> dict | None:
    return next((c for c in load_chats() if c["id"] == chat_id), None)


def chat_text(chat: dict | str) -> str:
    if isinstance(chat, str):
        return chat
    return "\n".join(f"{m.get('role', '?')}: {m.get('text', '')}" for m in chat.get("messages", []))


@dataclass
class OrderRun:
    chat_id: str
    task_type: str
    task_label: str
    pages: int | None
    style: str | None
    extras: list
    price: int | None
    clamped: bool
    breakdown: list
    questions: list
    missing: list
    urgent: bool
    injections: list
    redactions: list
    revision: dict
    approval: dict
    interrupted: bool
    status: str
    visited: list[str]
    handoff: str
    report: str
    mermaid: str


def build_graph(ctx: dict) -> Graph:
    def intake(state: dict, c: dict) -> dict:
        raw = chat_text(state["chat"])
        findings = detect_prompt_injection(raw)
        clean, redactions = redact_pii(raw)
        return {"raw_chars": len(raw), "chat_clean": clean,
                "injections": findings, "redactions": redactions,
                "revision_round": int(state.get("revision_round", 0))}

    def extract(state: dict, c: dict) -> dict:
        req = extract_requirements(state["chat_clean"])
        # Graph persists state as JSON at checkpoints: keep it plain-dict only.
        return {"req_dict": asdict(req), "task_type": req.task_type, "task_label": req.task_label,
                "pages": req.pages, "style": req.style, "urgent": req.urgent,
                "extras": req.extras, "missing": req.missing,
                "confidence": req.confidence}

    def clarify_node(state: dict, c: dict) -> dict:
        return {"questions": clarify(Requirements(**state["req_dict"]))}

    def quote_node(state: dict, c: dict) -> dict:
        return {"quote": quote(Requirements(**state["req_dict"]))}

    def approval_gate(state: dict, c: dict) -> dict:
        q = state["quote"]
        state["quote"] = q        # keep the computed quote in the checkpoint
        return Interrupt(
            reason=("报价需人工确认：¥" + str(q.get("price")) +
                    "（区间 10–60 元）。对外承诺金额前必须由人拍板。"),
            payload={"chat_id": state.get("chat_id"), "price": q.get("price"),
                     "breakdown": q.get("breakdown"), "questions": state.get("questions")},
            resume_node="brief")

    def brief(state: dict, c: dict) -> dict:
        q, req = state["quote"], Requirements(**state["req_dict"])
        lines = ["## 制作 brief（给执行者）", "",
                 f"- 任务类型：{req.task_label}", f"- 页数：{req.pages or '待确认'}",
                 f"- 风格：{req.style or '待确认'}",
                 f"- 交付：{req.deadline or '待确认'}{'（加急）' if req.urgent else ''}",
                 f"- 附加项：{', '.join(req.extras) or '无'}",
                 f"- 报价：¥{q.get('price')}",
                 f"- 需求置信度：{req.confidence}", "",
                 "执行清单：", "1. 接收并归档素材（初版 PPT / 演讲稿 / 视觉参考）；",
                 "2. 按页数搭结构，逐页标注内容来源；",
                 "3. 统一母版、字体与配色；", "4. 自查错别字、图片版权与导出兼容性；",
                 "5. 交付 PDF + 源文件，记录本轮修改点。"]
        return {"brief": "\n".join(lines)}

    def revision(state: dict, c: dict) -> dict:
        return {"revision": revision_policy(state["revision_round"],
                                            state["quote"].get("price") or 0)}

    def handoff(state: dict, c: dict) -> dict:
        return {"handoff": draft_handoff(Requirements(**state["req_dict"]), state["quote"],
                                         state["questions"], state["revision"])}

    def done(state: dict, c: dict) -> dict:
        q, req, rev = state["quote"], Requirements(**state["req_dict"]), state["revision"]
        lines = [f"# PPT 接单 Copilot · 需求确认单 · {state.get('chat_id', 'chat')}", "",
                 "> **边界**：本系统不接入闲鱼 / 微信任何接口。聊天记录为导入/粘贴，"
                 "Agent 只产出需求单、报价单、制作 brief 与话术，**对外发送由人工完成**。", "",
                 "## 1. 需求抽取", "",
                 f"- 任务类型：**{req.task_label}**（{req.task_type}）",
                 f"- 页数：{req.pages or '待确认'}；风格：{req.style or '待确认'}",
                 f"- 交付：{req.deadline or '待确认'}；加急：{'是' if req.urgent else '否'}",
                 f"- 附加项：{', '.join(req.extras) or '无'}；置信度：{req.confidence}", "",
                 "## 2. 可解释报价", "",
                 "| 项目 | 金额（元） |", "| --- | ---: |"]
        for item in q.get("breakdown", []):
            lines.append(f"| {item['item']} | {item['amount']:+.0f} |")
        lines += ["", f"**合计 ¥{q.get('price')}**（规则钳制区间 ¥{PRICE_MIN}–¥{PRICE_MAX}；"
                  f"钳制生效：{'是' if q.get('clamped') else '否'}）", "",
                  f"公式：`{q.get('rule', '')}`", "",
                  "## 3. 待确认问题（信息不足时主动追问）", ""]
        lines += [f"{i}. {x}" for i, x in enumerate(state["questions"], 1)] or ["- 无，信息完整"]
        lines += ["", "## 4. 修改轮次", "", rev["message"],
                  f"（免费 {FREE_REVISIONS} 轮，超出每轮 +¥{5}）", "",
                  "## 5. 人工审批", "", f"- 审批结果：{state.get('approval')}",
                  f"- 提示注入信号：{', '.join(state['injections']) or '无'}",
                  f"- 已脱敏字段：{', '.join(state['redactions']) or '无'}", "",
                  "## 6. 对外话术（人工复制到闲鱼 / 微信）", "", "```text",
                  state["handoff"], "```", "",
                  "## 7. 制作 brief", "", state["brief"], "",
                  "## 8. 流程轨迹", "", " → ".join(state.get("visited", [])) or "__VISITED__", ""]
        return {"report": "\n".join(lines)}

    g = Graph("p5_ppt_order_copilot", max_steps=16)
    for name, fn in (("intake", intake), ("extract", extract), ("clarify", clarify_node),
                     ("quote", quote_node), ("approval_gate", approval_gate),
                     ("brief", brief), ("revision", revision), ("handoff", handoff)):
        g.add_node(name, fn)
    g.add_node("done", done, terminal=True)
    for a, b in (("intake", "extract"), ("extract", "clarify"), ("clarify", "quote"),
                 ("quote", "approval_gate"), ("approval_gate", "brief"),
                 ("brief", "revision"), ("revision", "handoff"), ("handoff", "done")):
        g.add_edge(a, b)
    g.set_entry("intake")
    return g


def run_order(chat: dict | str, *, auto_approve: bool = True, revision_round: int = 0,
              use_api: bool = False, persist: bool = True) -> OrderRun:
    if use_api:
        raise ValueError("run_order is the offline quote demo; use OrderTeam or run_team.py for live model work")
    load_dotenv()
    ctx = {}
    graph = build_graph(ctx)
    state: dict = {"chat": chat, "revision_round": revision_round,
                   "chat_id": chat.get("id", "ad-hoc") if isinstance(chat, dict) else "ad-hoc"}
    result: GraphResult = graph.run(state, ctx=ctx, tracer=Tracer(persist=persist))
    interrupted = result.status == "needs_approval"
    if interrupted and auto_approve:
        result = graph.resume(result.checkpoint, approved=True,
                              reviewer="human:seller", ctx=ctx, tracer=Tracer(persist=False))
    final = result.state
    report = str(final.get("report", "")).replace("__VISITED__", " → ".join(result.visited))
    if not report and interrupted:
        report = "# 待人工确认报价\n\n" + str(result.interrupt.reason if result.interrupt else "")
    req = final.get("req")
    q = final.get("quote", {})
    return OrderRun(
        chat_id=str(final.get("chat_id", "")),
        task_type=final.get("task_type", ""), task_label=final.get("task_label", ""),
        pages=final.get("pages"), style=final.get("style"),
        extras=final.get("extras", []), price=q.get("price"),
        clamped=bool(q.get("clamped")), breakdown=q.get("breakdown", []),
        questions=final.get("questions", []), missing=final.get("missing", []),
        urgent=bool(final.get("urgent")), injections=final.get("injections", []),
        redactions=final.get("redactions", []), revision=final.get("revision", {}),
        approval=final.get("approval", {}), interrupted=interrupted,
        status=result.status, visited=result.visited,
        handoff=final.get("handoff", ""), report=report, mermaid=graph.mermaid())
