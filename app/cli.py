from __future__ import annotations

import argparse
import sys

from app.config import load_settings
from app.index import HybridIndex
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import build_context, system_prompt


SMOKE_CASES = [
    ("tutor", "Почему в линейной регрессии MSE?"),
    ("tutor", "Объясни PCA и связь с eigenvectors"),
    ("interviewer", "Проведи собеседование по CatBoost"),
    (
        "code",
        "Как в SQL посчитать средний чек по клиенту, сохранив клиентов без заказов?",
    ),
]


def _client_if_available(settings):
    client = OllamaClient(settings.ollama_url)
    return client, client if client.available() else None


def command_reindex(force: bool) -> int:
    settings = load_settings()
    if not settings.vault_path:
        print("Vault не найден. Запустите web UI и выберите папку в настройках.")
        return 1
    client, embedder = _client_if_available(settings)
    result = HybridIndex().reindex(settings, embedder, force=force)
    print(
        f"Готово: {result['total_files']} notes, {result['total_chunks']} chunks, "
        f"{result['vector_chunks']} embeddings."
    )
    for warning in result["warnings"]:
        print(f"Предупреждение: {warning}")
    return 0


def command_smoke(live: bool) -> int:
    settings = load_settings()
    index = HybridIndex()
    client, embedder = _client_if_available(settings)
    stats = index.stats()
    if not stats["chunks"]:
        print("Индекс пуст; сначала выполните reindex.")
        return 1

    failures = 0
    for mode, query in SMOKE_CASES:
        results = index.search(query, settings, embedder, mode=mode)
        top = results[0].breadcrumb if results else "нет результатов"
        print(f"[{mode}] {query}\n  top source: {top}", flush=True)
        if not results:
            failures += 1
            continue
        if live:
            context = build_context(
                [result.to_dict() for result in results],
                settings.context_chars,
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        system_prompt(mode, context)
                        + "\n\nЭто smoke test: уложись примерно в 180 слов."
                    ),
                },
                {"role": "user", "content": query},
            ]
            try:
                answer = "".join(
                    client.chat_stream(
                        model=settings.chat_model,
                        messages=messages,
                        temperature=settings.temperature,
                        num_predict=220,
                    )
                ).strip()
            except OllamaError as error:
                print(f"  generation failed: {error}")
                failures += 1
                continue
            print(
                f"  answer: {answer[:260].replace(chr(10), ' ')}…",
                flush=True,
            )
            if not answer:
                failures += 1
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ML Vault Agent utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    reindex_parser = subparsers.add_parser("reindex")
    reindex_parser.add_argument("--force", action="store_true")
    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.command == "reindex":
        return command_reindex(args.force)
    if args.command == "smoke":
        return command_smoke(args.live)
    return 2


if __name__ == "__main__":
    sys.exit(main())
