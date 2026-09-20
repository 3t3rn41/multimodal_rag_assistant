#!/usr/bin/env python3
"""Evaluate retrieval predictions against evaluation/dataset.jsonl.

Prediction JSONL schema:
{"case_id":"doc_001", "retrieved_chunk_ids":["..."],
 "cited_chunk_ids":["..."]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.metrics import aggregate, evaluate_case  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"expected object at {path}:{line_number}")
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation" / "dataset.jsonl")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dataset = {str(row["case_id"]): row for row in read_jsonl(args.dataset)}
    predictions = read_jsonl(args.predictions)
    metrics = []
    for prediction in predictions:
        case_id = str(prediction.get("case_id", ""))
        if case_id not in dataset:
            raise ValueError(f"prediction references unknown case_id: {case_id}")
        row = {**dataset[case_id], **prediction}
        metrics.append(evaluate_case(row, k=args.k))
    report = {
        "k": args.k,
        "summary": aggregate(metrics),
        "cases": [item.to_dict() for item in metrics],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
