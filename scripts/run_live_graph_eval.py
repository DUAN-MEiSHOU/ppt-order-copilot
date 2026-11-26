"""Real-model sample for the durable PPT order graph."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentkit import load_api_llm, load_dotenv  # noqa: E402
from projects.p5_ppt_order_copilot.graph_team import OrderGraph  # noqa: E402


def summary(name: str, result: dict) -> dict:
    models = sorted({step["model"] for step in result["trace"]})
    if not models or any(model.startswith("scripted") for model in models):
        raise RuntimeError("sample lacks a real model trajectory")
    if result.get("pptx"):
        from pptx import Presentation
        Presentation(result["pptx"])
        if not result.get("customer_reply", "").strip():
            raise RuntimeError("draft has no customer handoff wording")
    return {"case": name, "status": result["status"], "thread_id": result["thread_id"],
            "models": models, "roles": [step["role"] for step in result["trace"]],
            "pptx": result.get("pptx"), "state_file": result["state_file"]}


def main() -> int:
    load_dotenv()
    llm = load_api_llm()
    if llm is None:
        raise SystemExit("Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL")
    output = ROOT / "runs" / "graph_live"
    graph = OrderGraph(llm, output / "orders.sqlite")
    complete = ("请制作3页中文PPT，主题RAG切块入门，受众是大学生，蓝白简约风格，明天下午交付。"
                "全部内容在这里：第1页‘什么是切块’，要点‘把长文档拆成较短片段’；"
                "第2页‘常见方法’，要点‘固定长度’、‘按标题分段’；"
                "第3页‘检查点’，要点‘保留来源’、‘检查上下文是否完整’。无需图表或额外素材。")
    first = graph.start(complete, output)
    cases = [summary("complete_brief", first)]
    if first["status"] == "draft_ready":
        revised = graph.revise(first["thread_id"], "把第二页标题改成‘两种方法’，其余事实保持。")
        cases.append(summary("customer_revision", revised))
    incomplete = graph.start("请帮我做一份3页RAG入门PPT，内容等我发给你。", output)
    cases.append(summary("missing_material", incomplete))
    if incomplete["status"] == "needs_clarification":
        supplied = graph.resume(incomplete["thread_id"], complete)
        cases.append(summary("clarification_resumed", supplied))
        if supplied["status"] == "needs_clarification":
            final = graph.resume(incomplete["thread_id"], "明天下午五点前，交付可编辑PPTX。")
            cases.append(summary("clarification_completed", final))
    report = {"mode": "live-model", "model": llm.model, "cases": cases}
    path = output / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
