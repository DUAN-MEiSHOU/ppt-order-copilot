import tempfile
import unittest
import zipfile
from pathlib import Path

from projects.p5_ppt_order_copilot.team import OrderTeam


class FakeModel:
    model = "fake-for-test"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        from agentkit.llm import LLMResponse
        self.calls += 1
        outputs = [
            '{"requirements":{"topic":"RAG","audience":"students","style":"clean","pages":2},"reply":"已收到需求"}',
            '{"action":"design","reason":"requirements complete"}',
            '{"slides":[{"title":"RAG","bullets":["检索","生成"]},{"title":"切块","bullets":["按标题分段"]}]}',
            '{"approved":true,"issues":[]}',
            '{"reply":"初稿已完成，请查看。"}',
        ]
        return LLMResponse(content=outputs[self.calls - 1], model=self.model,
                           usage={"prompt_tokens": 10, "completion_tokens": 5})


class TeamTests(unittest.TestCase):
    def test_roles_create_editable_ppt_and_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            result = OrderTeam(FakeModel()).run("做两页 RAG 入门 PPT", Path(folder))
            self.assertEqual(result["status"], "draft_ready")
            self.assertEqual([x["role"] for x in result["trace"]],
                             ["customer_service", "supervisor", "designer", "supervisor", "customer_service"])
            with zipfile.ZipFile(result["pptx"]) as archive:
                self.assertIn("ppt/slides/slide1.xml", archive.namelist())
                self.assertIn("RAG", archive.read("ppt/slides/slide1.xml").decode())
            from pptx import Presentation
            self.assertEqual(len(Presentation(result["pptx"]).slides), 2)


if __name__ == "__main__":
    unittest.main()
