import unittest

from rag_engine.citations import CitationParser, StreamingCitationSplitter, citation_label
from rag_engine.models import Chunk


class CitationTests(unittest.TestCase):
    def test_parser_drops_fabricated_chunk_ids(self) -> None:
        evidence = Chunk("video_1", "demo.mp4", "video", "环境变量", time_start=80, time_end=110)
        raw = (
            "回答内容 [video_1]"
            "<<CITATIONS>>{\"citations\":[{\"chunk_id\":\"video_1\"},"
            "{\"chunk_id\":\"made_up\"}]}<<END_CITATIONS>>"
        )
        answer, citations = CitationParser().parse(raw, [evidence])
        self.assertEqual(answer, "回答内容 [video_1]")
        self.assertEqual([item.chunk_id for item in citations], ["video_1"])
        self.assertEqual(citation_label(evidence), "demo.mp4 01:20-01:50")

    def test_streaming_splitter_hides_citation_block(self) -> None:
        splitter = StreamingCitationSplitter()
        visible = splitter.feed("答案<<CIT")
        visible += splitter.feed("ATIONS>>{\"citations\":[]}")
        visible += splitter.feed("<<END_CITATIONS>>")
        visible += splitter.finish()
        self.assertEqual(visible, "答案")


if __name__ == "__main__":
    unittest.main()
