import tempfile
import unittest
from pathlib import Path

from agentkit.llm import LLMResponse
from projects.p5_ppt_order_copilot.graph_team import OrderGraph


class QueueModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def chat(self, messages, **kwargs):
        return LLMResponse(content=next(self.outputs), model="fake-for-test",
                           usage={"prompt_tokens": 10, "completion_tokens": 5})


class OrderGraphTests(unittest.TestCase):
    def test_clarification_resumes_from_sqlite_checkpoint(self):
        outputs = [
            '{"requirements":{"topic":"RAG","audience":null,"pages":2},"reply":"请补充受众"}',
            '{"action":"clarify","blocker":"audience","reason":"audience missing"}',
            '{"requirements":{"topic":"RAG","audience":"students","pages":2},"reply":"需求已齐"}',
            '{"action":"design","reason":"complete"}',
            '{"theme":{"accent":"112233"},"slides":[{"title":"RAG","bullets":["检索"]}]}',
            '{"approved":true,"issues":[]}',
            '{"reply":"初稿已完成"}',
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = QueueModel(outputs)
            first = OrderGraph(model, root / "orders.sqlite").start("请做RAG PPT", root, "order-1")
            self.assertEqual(first["status"], "needs_clarification")
            resumed = OrderGraph(model, root / "orders.sqlite").resume("order-1", "给大学生讲")
            self.assertEqual(resumed["status"], "draft_ready")
            self.assertTrue(Path(resumed["pptx"]).is_file())
            self.assertEqual(len(resumed["trace"]), 7)

    def test_revision_uses_same_order_and_prior_slides(self):
        outputs = [
            '{"requirements":{"topic":"RAG","audience":"students","pages":1},"reply":"收到"}',
            '{"action":"design","reason":"complete"}',
            '{"slides":[{"title":"初版","bullets":["切块"]}]}',
            '{"approved":true,"issues":[]}',
            '{"content":{"summary":"初稿完成","next_step":"请提出修改意见"}}',
            '{"requirements":{"topic":"RAG","audience":"students","pages":1},"reply":"收到修改"}',
            '{"action":"design","reason":"complete"}',
            '{"slides":[{"title":"修改版","bullets":["按标题切块"]}]}',
            '{"approved":true,"issues":[]}',
            '{"reply":"修改完成"}',
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            graph = OrderGraph(QueueModel(outputs), root / "orders.sqlite")
            first = graph.start("给大学生做一页RAG PPT", root, "order-2")
            self.assertEqual(first["customer_reply"], "初稿完成\n请提出修改意见")
            revised = graph.revise("order-2", "标题改为修改版")
            self.assertEqual(revised["status"], "draft_ready")
            self.assertEqual(revised["slides"][0]["title"], "修改版")
            self.assertEqual(revised["revision_round"], 1)

    def test_optional_deadline_does_not_block_design(self):
        outputs = [
            '{"requirements":{"topic":"RAG","audience":"students","pages":1},"reply":"收到"}',
            '{"action":"clarify","blocker":"deadline","reason":"deadline missing"}',
            '{"slides":[{"title":"RAG","bullets":["切块"]}]}',
            '{"approved":true,"issues":[]}',
            '{"reply":"初稿完成"}',
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = OrderGraph(QueueModel(outputs), root / "orders.sqlite").start(
                "给学生做RAG PPT", root)
            self.assertEqual(result["status"], "draft_ready")

    def test_missing_audience_blocks_even_without_action_field(self):
        outputs = [
            '{"requirements":{"topic":"RAG","audience":null,"pages":3},"reply":"请补充受众"}',
            '{"blocker":"audience","reason":"audience missing"}',
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = OrderGraph(QueueModel(outputs), root / "orders.sqlite").start(
                "做三页RAG PPT", root)
            self.assertEqual(result["status"], "needs_clarification")


if __name__ == "__main__":
    unittest.main()
