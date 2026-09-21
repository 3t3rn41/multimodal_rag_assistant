import unittest
from pathlib import Path

from scripts.index_chunks import build_parser


class IndexCommandTests(unittest.TestCase):
    def test_defaults_to_a_jina_specific_collection_and_supports_rebuild(self) -> None:
        args = build_parser().parse_args(["--chunks", str(Path("chunks.jsonl")), "--rebuild"])

        self.assertTrue(args.rebuild)
        self.assertEqual(args.collection, "jina_v5_omni_small_1024")
        self.assertEqual(args.embedding_dimensions, 1024)


if __name__ == "__main__":
    unittest.main()
