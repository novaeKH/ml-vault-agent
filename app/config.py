from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(
    os.environ.get("ML_VAULT_AGENT_DATA_DIR", PROJECT_ROOT / "data")
).expanduser()
SETTINGS_PATH = DATA_DIR / "settings.json"


@dataclass(slots=True)
class Settings:
    vault_path: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3:8b"
    code_model: str = "qwen3:8b"
    embedding_model: str = "qwen3-embedding:0.6b"
    top_k: int = 6
    temperature: float = 0.25
    context_chars: int = 24_000
    history_messages: int = 10
    code_max_attempts: int = 2

    def normalized(self) -> "Settings":
        vault = str(Path(self.vault_path).expanduser().resolve()) if self.vault_path else ""
        chat_model = self.chat_model.strip() or "qwen3:8b"
        return Settings(
            vault_path=vault,
            ollama_url=self.ollama_url.rstrip("/"),
            chat_model=chat_model,
            code_model=self.code_model.strip() or chat_model,
            embedding_model=self.embedding_model.strip() or "qwen3-embedding:0.6b",
            top_k=max(2, min(int(self.top_k), 12)),
            temperature=max(0.0, min(float(self.temperature), 1.5)),
            context_chars=max(8_000, min(int(self.context_chars), 48_000)),
            history_messages=max(2, min(int(self.history_messages), 20)),
            code_max_attempts=max(1, min(int(self.code_max_attempts), 3)),
        )

    def public_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


def _is_vault(path: Path) -> bool:
    try:
        return (
            path.is_dir()
            and (path / ".obsidian").is_dir()
            and any(path.rglob("*.md"))
        )
    except OSError:
        return False


def _candidate_score(path: Path) -> tuple[int, int]:
    score = 0
    state = path / "_meta" / "VAULT_REFACTOR_STATE.md"
    if state.is_file():
        score += 20
        try:
            text = state.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if "Stage 3 complete" in text or "ready for use and read-only RAG" in text:
            score += 50
    if (path / "10 Знания").is_dir():
        score += 10
    if (path / "15 Практика").is_dir():
        score += 5
    try:
        markdown_count = sum(1 for _ in path.rglob("*.md"))
    except OSError:
        markdown_count = 0
    return score, markdown_count


def discover_vaults() -> list[str]:
    """Find likely Obsidian vaults without touching their contents."""

    explicit = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    found: set[Path] = set()
    if explicit:
        candidate = Path(explicit).expanduser()
        if _is_vault(candidate):
            found.add(candidate.resolve())

    home = Path.home()
    search_roots = [
        home / "Desktop",
        home / "Documents",
        home / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    ]

    for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(variable, "").strip()
        if value:
            one_drive = Path(value).expanduser()
            search_roots.extend([one_drive, one_drive / "Documents", one_drive / "Desktop"])

    for root in dict.fromkeys(search_roots):
        if not root.is_dir():
            continue
        try:
            children = [root, *[item for item in root.iterdir() if item.is_dir()]]
        except OSError:
            continue
        for child in children:
            if _is_vault(child):
                found.add(child.resolve())
            try:
                grandchildren = [item for item in child.iterdir() if item.is_dir()]
            except OSError:
                continue
            for grandchild in grandchildren:
                if _is_vault(grandchild):
                    found.add(grandchild.resolve())

    return [str(path) for path in sorted(found, key=lambda item: _candidate_score(item), reverse=True)]


def load_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    values: dict[str, Any] = {}
    if SETTINGS_PATH.is_file():
        try:
            values = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            values = {}

    allowed = {field.name for field in fields(Settings)}
    settings = Settings(**{key: value for key, value in values.items() if key in allowed})
    if not settings.vault_path or not _is_vault(Path(settings.vault_path)):
        candidates = discover_vaults()
        unique_best = len(candidates) == 1
        if len(candidates) > 1:
            unique_best = _candidate_score(Path(candidates[0])) > _candidate_score(Path(candidates[1]))
        if candidates and unique_best:
            settings.vault_path = candidates[0]
            save_settings(settings)
    return settings.normalized()


def save_settings(settings: Settings) -> Settings:
    normalized = settings.normalized()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(normalized.public_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(SETTINGS_PATH)
    return normalized


def validate_vault_path(value: str) -> str:
    path = Path(value).expanduser().resolve()
    if not _is_vault(path):
        raise ValueError(
            "Выбранная папка не похожа на Obsidian vault: нужна папка с .obsidian "
            "и Markdown-файлами."
        )
    return str(path)
