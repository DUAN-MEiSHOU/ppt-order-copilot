"""Run sample orders through the real three-role model team."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentkit import load_api_llm, load_dotenv  # noqa: E402
from projects.p5_ppt_order_copilot.team import OrderTeam  # noqa: E402
from projects.p5_ppt_order_copilot.workflow import chat_by_id, chat_text  # noqa: E402


def main() -> int:
    load_dotenv()
    model = load_api_llm()
    if model is None:
        raise SystemExit("Live evaluation requires LLM_API_KEY and LLM_BASE_URL")
    out = ROOT / "runs" / "live"
    cases = []
    examples = [(chat_id, chat_text(chat_by_id(chat_id)))
                for chat_id in ("c01_speech_to_ppt", "c08_revision_round3")]
    examples.append(("complete_rag_brief",
                     "请制作3页中文PPT，主题是RAG切块入门，面向刚入门的大学生，清爽蓝白风格，明天下午交付。"
                     "全部内容素材已在本消息给出：第1页标题‘什么是切块’，要点‘将长文档拆成可检索的小段’；"
                     "第2页标题‘常见方法’，要点‘固定长度’、‘按标题分段’；"
                     "第3页标题‘检查点’，要点‘保留来源’、‘检查上下文是否完整’。"
                     "仅依据这些文字制作，不需要图表或外部文件。"))
    complete_result = None
    for chat_id, chat in examples:
        result = OrderTeam(model).run(chat, out)
        models = [step["model"] for step in result["trace"]]
        if not models or any(not name or name.startswith("scripted") for name in models):
            raise RuntimeError("Evaluation contained a missing or scripted model response")
        cases.append({"chat_id": chat_id, "status": result["status"],
                      "models": sorted(set(models)), "roles": [s["role"] for s in result["trace"]],
                      "pptx": result["pptx"], "trace": result["state_file"]})
        if chat_id == "complete_rag_brief":
            complete_result = result
    if complete_result and complete_result["status"] == "draft_ready":
        revised = OrderTeam(model).run(examples[-1][1], out,
            feedback="请把第2页标题改成‘两种切块方法’，配色改为深蓝色；其余事实内容保持。",
            previous_state=Path(complete_result["state_file"]))
        cases.append({"chat_id": "complete_rag_revision", "status": revised["status"],
                      "models": sorted({s["model"] for s in revised["trace"]}),
                      "roles": [s["role"] for s in revised["trace"]],
                      "pptx": revised["pptx"], "trace": revised["state_file"]})
    report = {"mode": "live-model", "model_requested": model.model, "cases": cases,
              "draft_rate": sum(c["status"] == "draft_ready" for c in cases) / len(cases)}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
