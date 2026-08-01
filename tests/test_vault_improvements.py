from pathlib import Path

from app.vault import chunks_for_note, read_note


def make_note(tmp_path: Path, body: str):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = vault / "Note.md"
    path.write_text(
        "---\ntitle: Note\ntype: practice\nrag: include\n---\n# Note\n\n" + body,
        encoding="utf-8",
    )
    note = read_note(vault, path)
    assert note is not None
    return note


def test_heading_inside_code_fence_does_not_split_chunk(tmp_path: Path):
    note = make_note(
        tmp_path,
        "## Real section\n\n```markdown\n## Not a real section\n```\n\nText.",
    )
    chunks = chunks_for_note(note)
    assert len(chunks) == 1
    assert "Not a real section" in chunks[0].content


def test_duplicate_headings_get_unique_chunk_ids(tmp_path: Path):
    note = make_note(
        tmp_path,
        "## Example\n\nFirst.\n\n## Example\n\nSecond.",
    )
    chunks = chunks_for_note(note)
    assert len(chunks) == 2
    assert len({chunk.chunk_id for chunk in chunks}) == 2
