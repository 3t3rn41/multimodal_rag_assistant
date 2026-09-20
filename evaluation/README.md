# RAG 评估集与指标

`dataset.jsonl` 是成员 C 的最小回归集，覆盖文档、图片、音频、视频和混合检索问题。每行包含：

- `case_id`：稳定的用例标识；
- `question`：用户问题；
- `source_type`：问题涉及的模态；
- `expected_chunk_ids`：相关 Chunk 的金标准集合；
- `reference_answer`：人工参考答案；
- `expected_citations`：期望引用。

在线检索服务只需要输出同名 `case_id` 的预测 JSONL：

```json
{"case_id":"doc_001","retrieved_chunk_ids":["spec_task_state"],"cited_chunk_ids":["spec_task_state"]}
```

运行评估：

```bash
python scripts/evaluate_rag.py --predictions evaluation/predictions.jsonl --k 5
```

脚本输出每个用例和汇总指标：

- `precision_at_k`：top-k 中相关 Chunk 的比例；
- `recall_at_k`：金标准 Chunk 在 top-k 中的覆盖率；
- `hit_rate`：top-k 是否至少命中一个相关 Chunk；
- `mrr`：第一个相关 Chunk 的倒数排名；
- `citation_accuracy`：模型引用中真实相关 Chunk 的比例。

## 当前指标报告

当前仓库只有方案级样例集，没有接入真实文件、Embedding 服务或向量库，因此不伪造线上基线数字。接入 M2 文本闭环后，应保存一份预测 JSONL，并将脚本输出作为版本化回归报告。后续可增加 Faithfulness 评估器，由人工标注或独立评审模型判断回答是否被引用证据支持。
