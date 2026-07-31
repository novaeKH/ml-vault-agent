from pathlib import Path

import pytest

from app.config import discover_vaults, validate_vault_path


def make_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    return vault


def test_validate_vault_path(tmp_path: Path):
    vault = make_vault(tmp_path)
    assert validate_vault_path(str(vault)) == str(vault.resolve())


def test_invalid_vault_path_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="Obsidian vault"):
        validate_vault_path(str(tmp_path))


def test_explicit_vault_is_discovered(tmp_path: Path, monkeypatch):
    vault = make_vault(tmp_path)
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    assert str(vault.resolve()) in discover_vaults()
