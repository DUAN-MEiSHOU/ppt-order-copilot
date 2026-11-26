"""Run the real-model team; generated replies are drafts for a human to send."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agentkit import load_api_llm, load_dotenv  # noqa: E402
from projects.p5_ppt_order_copilot.graph_team import OrderGraph  # noqa: E402
from projects.p5_ppt_order_copilot.team import OrderTeam  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("chat", nargs="?", help="customer chat text, or path to a UTF-8 text file")
    parser.add_argument("--feedback", default="", help="customer revision request")
    parser.add_argument("--previous", type=Path, help="previous order JSON for revisions")
    parser.add_argument("--thread", help="order ID for resuming or revising a durable order")
    parser.add_argument("--resume", help="customer's answer to a clarification request")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    parser.add_argument("--database", type=Path, help="SQLite checkpoint file")
    parser.add_argument("--env", type=Path, help="model configuration file (can reuse the research agent's .env)")
    args = parser.parse_args()
    load_dotenv(str(args.env) if args.env else None)
    llm = load_api_llm()
    if llm is None:
        parser.error("Set LLM_API_KEY and LLM_BASE_URL for a real model run")
    if args.previous:
        if not args.chat:
            parser.error("chat is required with --previous")
        chat_path = Path(args.chat)
        try:
            chat = chat_path.read_text(encoding="utf-8") if chat_path.is_file() else args.chat
        except OSError:
            chat = args.chat
        result = OrderTeam(llm).run(chat, args.output, feedback=args.feedback,
                                    previous_state=args.previous)
    else:
        graph = OrderGraph(llm, args.database or args.output / "orders.sqlite")
        if args.resume:
            if not args.thread:
                parser.error("--resume requires --thread")
            result = graph.resume(args.thread, args.resume)
        elif args.feedback and args.thread:
            result = graph.revise(args.thread, args.feedback)
        else:
            if args.feedback:
                parser.error("--feedback requires --thread for a durable order")
            if not args.chat:
                parser.error("chat is required to start an order")
            chat_path = Path(args.chat)
            try:
                chat = chat_path.read_text(encoding="utf-8") if chat_path.is_file() else args.chat
            except OSError:
                chat = args.chat
            result = graph.start(chat, args.output, args.thread)
    print(json.dumps({key: value for key, value in result.items() if key != "trace"},
                     ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("draft_ready", "needs_clarification") else 1


if __name__ == "__main__":
    raise SystemExit(main())
