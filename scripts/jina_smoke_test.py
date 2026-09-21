"""Send one passage and one query to the configured Jina API."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable

from ingestion import ApiMultimodalEmbedder, MultimodalEmbeddingAPIConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--text",
        default="Jina v5 omni smoke test: multimodal retrieval uses one shared vector space.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = MultimodalEmbeddingAPIConfig.from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    provider = ApiMultimodalEmbedder(config)
    passage = provider.embed([args.text])[0]
    query = provider.embed_query(args.text)
    if len(passage) != len(query):
        raise SystemExit("Jina passage/query dimensions do not match")
    print(
        json.dumps(
            {
                "model": config.model,
                "dimensions": len(passage),
                "passage_task": config.passage_task,
                "query_task": config.query_task,
                "status": "ok",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
