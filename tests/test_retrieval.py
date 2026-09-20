import unittest

from rag_engine.models import Chunk, RetrievalCandidate
from rag_engine.retrieval import BM25Retriever, HybridRetriever, reciprocal_rank_fusion


def chunk(chunk_id: str, content: str) -> Chunk:
    return Chunk(chunk_id, "file-1", "document", content)


class RetrievalTests(unittest.TestCase):
    def test_bm25_prefers_exact_terms(self) -> None:
        retriever = BM25Retriever(
            [
                chunk("c1", "配置 Redis 环境变量和队列"),
                chunk("c2", "介绍图片抽帧和视频时间轴"),
            ]
        )
        results = retriever.search("Redis 环境变量", top_k=2)
        self.assertEqual(results[0].chunk_id, "c1")

    def test_rrf_merges_two_rankings(self) -> None:
        c1 = RetrievalCandidate(chunk("c1", "alpha"), 0.9, "dense")
        c2 = RetrievalCandidate(chunk("c2", "beta"), 0.8, "dense")
        c3 = RetrievalCandidate(chunk("c3", "gamma"), 0.9, "bm25")
        fused = reciprocal_rank_fusion(
            {"dense": [c1, c2], "bm25": [c3, c1]}, top_k=3, rank_constant=1
        )
        self.assertEqual(fused[0].chunk_id, "c1")
        self.assertIn("dense", fused[0].source)
        self.assertIn("bm25", fused[0].source)

    def test_hybrid_can_run_without_vector_service(self) -> None:
        retriever = HybridRetriever(
            BM25Retriever([chunk("c1", "混合检索和重排"), chunk("c2", "音频转写")])
        )
        self.assertEqual(retriever.search("混合检索", top_k=1)[0].chunk_id, "c1")


if __name__ == "__main__":
    unittest.main()
