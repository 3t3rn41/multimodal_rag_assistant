import unittest

from rag_engine.models import Chunk, RetrievalCandidate
from rag_engine.prompts import build_context, build_messages


class PromptTests(unittest.TestCase):
    def test_context_contains_trusted_chunk_id_and_metadata(self) -> None:
        candidate = RetrievalCandidate(
            Chunk("c1", "manual.pdf", "document", "安装步骤", page=12),
            score=1.0,
            source="bm25",
        )
        context = build_context([candidate])
        self.assertIn("[c1]", context)
        self.assertIn("manual.pdf p.12", context)
        self.assertIn("安装步骤", context)

    def test_messages_include_grounding_rules(self) -> None:
        messages = build_messages("如何安装？", [])
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("只能使用", messages[0]["content"])
        self.assertIn("如何安装", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
