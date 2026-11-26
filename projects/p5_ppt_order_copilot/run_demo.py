#!/usr/bin/env python3
"""CLI demo for project 5.

    python projects/p5_ppt_order_copilot/run_demo.py
    python projects/p5_ppt_order_copilot/run_demo.py --chat c05_urgent_clamp
    python projects/p5_ppt_order_copilot/run_demo.py --chat c08_revision_round3 --revision 3
    python projects/p5_ppt_order_copilot/run_demo.py --no-approve       # stop at price approval
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from projects.p5_ppt_order_copilot.workflow import chat_by_id, chat_text, load_chats, run_order  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat", help="chat id from data/ppt_chats_sample.json")
    ap.add_argument("--list", action="store_true", help="list available chats")
    ap.add_argument("--revision", type=int, default=0, help="which revision round")
    ap.add_argument("--no-approve", action="store_true", help="stop at the human price gate")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    if args.list:
        for c in load_chats():
            print(f"  {c['id']:28} {len(c['messages'])} 条消息")
        return 0
    chat = chat_by_id(args.chat or "c01_speech_to_ppt")
    if chat is None:
        print("Unknown chat id; use --list")
        return 1
    if args.api:
        import json
        from agentkit import load_api_llm, load_dotenv
        from projects.p5_ppt_order_copilot.graph_team import OrderGraph
        load_dotenv()
        llm = load_api_llm()
        if llm is None:
            ap.error("Set LLM_API_KEY and LLM_BASE_URL for a live run")
        result = OrderGraph(llm, ROOT / "outputs" / "orders.sqlite").start(
            chat_text(chat), ROOT / "outputs")
        print(json.dumps({k: v for k, v in result.items() if k != "trace"},
                         ensure_ascii=False, indent=2))
        return 0 if result["status"] in ("draft_ready", "needs_clarification") else 1
    run = run_order(chat, auto_approve=not args.no_approve,
                    revision_round=args.revision)
    print("=" * 78)
    print(f"CHAT={run.chat_id} TYPE={run.task_type} PAGES={run.pages} "
          f"PRICE=¥{run.price} CLAMPED={run.clamped} "
          f"APPROVAL_GATE={run.interrupted} STATUS={run.status}")
    print("=" * 78)
    print(run.report)
    if not args.no_approve:
        print("\n--- 对外话术（人工复制发送）---\n")
        print(run.handoff)
    print("\n--- 状态图 ---")
    print(run.mermaid)
    if args.save:
        out = ROOT / "evals" / "reports" / "ppt_order_report.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(run.report + "\n\n## 状态图\n\n```mermaid\n" + run.mermaid + "\n```\n",
                       encoding="utf-8")
        print(f"\nSaved to {out}")
    return 0 if run.status in ("done", "needs_approval") else 1


if __name__ == "__main__":
    sys.exit(main())
