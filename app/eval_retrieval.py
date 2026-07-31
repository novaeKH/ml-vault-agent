from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.index import HybridIndex
from app.ollama_client import OllamaClient


@dataclass(frozen=True, slots=True)
class EvalCase:
    query: str
    expected_files: tuple[str, ...]
    mode: str = "chat"


def load_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Evaluation file must contain a JSON list.")
    cases: list[EvalCase] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each evaluation case must be an object.")
        query = str(item.get("query", "")).strip()
        expected = tuple(str(value) for value in item.get("expected_files", []))
        mode = str(item.get("mode", "chat")).strip() or "chat"
        if not query or not expected:
            raise ValueError("Every case needs query and expected_files.")
        cases.append(EvalCase(query=query, expected_files=expected, mode=mode))
    return cases


def evaluate(cases: list[EvalCase], *, top_k: int) -> dict[str, Any]:
    settings = load_settings()
    index = HybridIndex()
    client = OllamaClient(settings.ollama_url)
    embedder = client if client.available() else None

    hits = 0
    reciprocal_rank = 0.0
    details: list[dict[str, Any]] = []
    for case in cases:
        results = index.search(
            case.query,
            settings,
            embedder,
            mode=case.mode,
            top_k=top_k,
        )
        paths = [result.file_path for result in results]
        rank = 0
        for position, path in enumerate(paths, start=1):
            if path in case.expected_files:
                rank = position
                break
        if rank:
            hits += 1
            reciprocal_rank += 1.0 / rank
        details.append(
            {
                "query": case.query,
                "mode": case.mode,
                "expected_files": list(case.expected_files),
                "retrieved_files": paths,
                "first_relevant_rank": rank or None,
            }
        )

    total = len(cases)
    return {
        "cases": total,
        f"recall_at_{top_k}": hits / total if total else 0.0,
        "mrr": reciprocal_rank / total if total else 0.0,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate ML Vault retrieval quality")
    parser.add_argument("cases", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        cases = load_cases(args.cases)
        report = evaluate(cases, top_k=max(1, args.top_k))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
