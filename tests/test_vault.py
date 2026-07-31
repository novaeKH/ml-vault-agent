from pathlib import Path

from app.vault import chunks_for_note, read_note, tokenize


NOTE = """---
title: Linear Regression
type: concept
area: ml
status: active
aliases:
  - Линейная регрессия
  - OLS
---

# Linear Regression

## Идея

Линейная регрессия моделирует условное среднее target.

## Почему MSE

При Gaussian noise maximum likelihood приводит к squared error.

$$
\\varepsilon_i \\sim \\mathcal{N}(0, \\sigma^2)
$$

Это отдельная причинная связь.
"""


def test_frontmatter_and_chunks(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note_path = vault / "Linear Regression.md"
    note_path.write_text(NOTE, encoding="utf-8")

    note = read_note(vault, note_path)

    assert note is not None
    assert note.title == "Linear Regression"
    assert note.aliases == ["Линейная регрессия", "OLS"]
    assert note.collection == "knowledge"
    chunks = chunks_for_note(note)
    assert chunks
    assert all(chunk.file_path == "Linear Regression.md" for chunk in chunks)
    assert any("Gaussian noise" in chunk.text for chunk in chunks)


def test_rag_exclude_is_not_indexed(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = vault / "Router.md"
    path.write_text(
        "---\ntitle: Router\ntype: concept\nrag: exclude\n---\n# Router\n",
        encoding="utf-8",
    )
    assert read_note(vault, path) is None


def test_tokenizer_supports_russian_and_code():
    assert tokenize("Линейная regression train_test") == [
        "линейная",
        "regression",
        "train_test",
    ]
