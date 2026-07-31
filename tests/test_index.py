import hashlib
import math
from pathlib import Path

from app.config import Settings
from app.index import HybridIndex


class FakeEmbedder:
    @staticmethod
    def _vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.casefold().encode("utf-8")).digest()
        values = [float(value) - 127.5 for value in digest[:8]]
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values]

    def embed_documents(self, model: str, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, model: str, query: str) -> list[float]:
        return self._vector(query)


def make_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    note = vault / "Linear Regression.md"
    note.write_text(
        """---
title: Linear Regression
type: concept
area: ml
aliases: [OLS, Линейная регрессия]
---
# Linear Regression

## Почему MSE

Gaussian noise через maximum likelihood приводит к MSE и squared error.

## Gauss-Markov

Gauss-Markov отдельно описывает BLUE, а не происхождение MSE.
""",
        encoding="utf-8",
    )
    return vault


def test_incremental_index_and_hybrid_search(tmp_path: Path):
    vault = make_vault(tmp_path)
    database = tmp_path / "index.sqlite3"
    index = HybridIndex(database)
    settings = Settings(vault_path=str(vault), embedding_model="fake")
    embedder = FakeEmbedder()

    first = index.reindex(settings, embedder)
    original = (vault / "Linear Regression.md").read_bytes()
    second = index.reindex(settings, embedder)

    assert first["changed_files"] == 1
    assert first["vector_chunks"] > 0
    assert second["changed_files"] == 0
    assert second["unchanged_files"] == 1
    assert second["opened_files"] == 0
    assert (vault / "Linear Regression.md").read_bytes() == original

    results = index.search(
        "Почему в линейной регрессии MSE Gaussian likelihood?",
        settings,
        embedder,
        mode="tutor",
    )
    assert results
    assert results[0].title == "Linear Regression"
    assert "MSE" in results[0].text


def test_removed_file_is_removed_from_index(tmp_path: Path):
    vault = make_vault(tmp_path)
    index = HybridIndex(tmp_path / "index.sqlite3")
    settings = Settings(vault_path=str(vault), embedding_model="fake")
    embedder = FakeEmbedder()
    index.reindex(settings, embedder)

    (vault / "Linear Regression.md").unlink()
    result = index.reindex(settings, embedder)

    assert result["removed_files"] == 1
    assert index.stats()["chunks"] == 0


def test_practice_mode_retrieves_tasks_but_not_solutions(tmp_path: Path):
    vault = make_vault(tmp_path)
    (vault / "Two Pointers Practice.md").write_text(
        """---
title: Two Pointers Practice
type: practice
area: algorithms
rag: include
---
# Two Pointers Practice

## Palindrome task

Проверьте палиндром двумя указателями. Сначала сформулируйте инвариант.
""",
        encoding="utf-8",
    )
    (vault / "Two Pointers Solution.md").write_text(
        """---
title: Two Pointers Solution
type: solution
area: algorithms
rag: include
---
# Two Pointers Solution

## Palindrome reference solution

Эталонное решение palindrome использует left и right с движением навстречу.
""",
        encoding="utf-8",
    )
    index = HybridIndex(tmp_path / "practice.sqlite3")
    settings = Settings(vault_path=str(vault), top_k=10)
    index.reindex(settings, embedder=None)

    practice_results = index.search(
        "Дай задачу palindrome на two pointers",
        settings,
        embedder=None,
        mode="practice",
    )
    code_results = index.search(
        "Покажи эталонное решение palindrome left right",
        settings,
        embedder=None,
        mode="code",
    )

    assert any(result.collection == "practice" for result in practice_results)
    assert all(result.collection != "solution" for result in practice_results)
    assert any(result.collection == "solution" for result in code_results)
    assert index.stats()["collections"]["practice"] > 0
    assert index.stats()["collections"]["solution"] > 0
