from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


WORD_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿА-Яа-яЁё]+(?:[-_][\wА-Яа-яЁё]+)*", re.UNICODE)
FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?")


@dataclass(slots=True)
class Note:
    relative_path: str
    title: str
    note_type: str
    area: str
    aliases: list[str]
    collection: str
    body: str
    content_hash: str


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    file_path: str
    title: str
    heading: str
    breadcrumb: str
    aliases: list[str]
    note_type: str
    area: str
    collection: str
    content: str
    text: str
    content_hash: str
    word_count: int


def tokenize(text: str) -> list[str]:
    return [match.group(0).casefold() for match in WORD_RE.finditer(text)]


def split_frontmatter(text: str) -> tuple[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return match.group(1), text[match.end() :]


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def frontmatter_scalar(frontmatter: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", frontmatter, re.MULTILINE)
    return _strip_quotes(match.group(1)) if match else ""


def frontmatter_list(frontmatter: str, key: str) -> list[str]:
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        inline = re.match(rf"^{re.escape(key)}:\s*\[(.*)]\s*$", line)
        if inline:
            return [
                _strip_quotes(item)
                for item in inline.group(1).split(",")
                if _strip_quotes(item)
            ]
        if re.match(rf"^{re.escape(key)}:\s*$", line):
            result: list[str] = []
            for child in lines[index + 1 :]:
                item = re.match(r"^\s*-\s+(.+?)\s*$", child)
                if not item:
                    break
                result.append(_strip_quotes(item.group(1)))
            return result
    return []


def _title_from_body(body: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return match.group(1) if match else fallback


def _collection(note_type: str, rag: str, status: str) -> str:
    if rag.casefold() == "exclude" or status.casefold() == "archived":
        return ""
    if note_type == "practice" and rag.casefold() == "include":
        return "practice"
    if note_type == "solution" and rag.casefold() == "include":
        return "solution"
    if note_type in {"concept", "deep-dive"}:
        return "knowledge"
    if note_type == "interview":
        return "interview"
    if rag.casefold() == "include":
        return "knowledge"
    return ""


def read_note(vault_root: Path, path: Path) -> Note | None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = split_frontmatter(raw)
    note_type = frontmatter_scalar(frontmatter, "type").casefold()
    rag = frontmatter_scalar(frontmatter, "rag")
    status = frontmatter_scalar(frontmatter, "status")
    collection = _collection(note_type, rag, status)
    if not collection:
        return None

    relative = path.relative_to(vault_root).as_posix()
    return Note(
        relative_path=relative,
        title=frontmatter_scalar(frontmatter, "title")
        or _title_from_body(body, path.stem),
        note_type=note_type,
        area=frontmatter_scalar(frontmatter, "area"),
        aliases=frontmatter_list(frontmatter, "aliases"),
        collection=collection,
        body=body,
        content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def iter_markdown(vault_root: Path) -> Iterator[Path]:
    for path in sorted(vault_root.rglob("*.md")):
        relative_parts = path.relative_to(vault_root).parts
        if any(part in {".obsidian", ".trash"} for part in relative_parts):
            continue
        if any(part.startswith(".") for part in relative_parts):
            continue
        yield path


def _word_count(text: str) -> int:
    return len(tokenize(text))


def _heading_indices(lines: list[str], level: int) -> list[int]:
    marker = "#" * level + " "
    indices: list[int] = []
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            current = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = current[0]
            elif current[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if not in_fence and line.startswith(marker):
            indices.append(index)
    return indices


def _make_chunk(
    note: Note,
    heading: str,
    content: str,
    level: int,
    ordinal: int,
) -> Chunk:
    clean = content.strip()
    breadcrumb = note.title if heading == "Overview" else f"{note.title} > {heading}"
    alias_context = f"\nAliases: {'; '.join(note.aliases)}" if note.aliases else ""
    text = f"# {note.title}\n\nBreadcrumb: {breadcrumb}{alias_context}\n\n{clean}"
    normalized = re.sub(r"\s+", " ", clean).strip().casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    identity = f"{note.relative_path}|{level}|{ordinal}|{heading}|{digest}"
    chunk_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return Chunk(
        chunk_id=f"{note.relative_path}#{ordinal}-{chunk_key}",
        file_path=note.relative_path,
        title=note.title,
        heading=heading,
        breadcrumb=breadcrumb,
        aliases=note.aliases,
        note_type=note.note_type,
        area=note.area,
        collection=note.collection,
        content=clean,
        text=text,
        content_hash=digest,
        word_count=_word_count(clean),
    )


def _raw_chunks(note: Note) -> list[Chunk]:
    lines = note.body.splitlines()
    h2_indices = _heading_indices(lines, 2)
    chunk_specs: list[tuple[str, str, int]] = []

    first_h2 = h2_indices[0] if h2_indices else len(lines)
    preamble = "\n".join(
        line for line in lines[:first_h2] if not re.match(r"^#\s+", line)
    ).strip()
    if _word_count(preamble) >= 30:
        chunk_specs.append(("Overview", preamble, 1))

    for position, start in enumerate(h2_indices):
        end = h2_indices[position + 1] if position + 1 < len(h2_indices) else len(lines)
        heading = re.sub(r"^##\s+", "", lines[start]).strip()
        section_lines = lines[start + 1 : end]
        section_text = "\n".join(section_lines).strip()
        h3_offsets = _heading_indices(section_lines, 3)

        if len(section_text) <= 4_500 or not h3_offsets:
            if section_text:
                chunk_specs.append((heading, section_text, 2))
            continue

        intro = "\n".join(section_lines[: h3_offsets[0]]).strip()
        if len(intro) >= 80:
            chunk_specs.append((heading, intro, 2))

        for h3_position, h3_start in enumerate(h3_offsets):
            h3_end = (
                h3_offsets[h3_position + 1]
                if h3_position + 1 < len(h3_offsets)
                else len(section_lines)
            )
            h3_heading = re.sub(r"^###\s+", "", section_lines[h3_start]).strip()
            h3_text = "\n".join(section_lines[h3_start + 1 : h3_end]).strip()
            if h3_text:
                chunk_specs.append((f"{heading} > {h3_heading}", h3_text, 3))

    if not chunk_specs:
        fallback = "\n".join(
            line for line in lines if not re.match(r"^#\s+", line)
        ).strip()
        if fallback:
            chunk_specs.append(("Overview", fallback, 1))

    return [
        _make_chunk(note, heading, content, level, ordinal)
        for ordinal, (heading, content, level) in enumerate(chunk_specs, start=1)
    ]


def _merge_short_knowledge_chunks(note: Note, chunks: list[Chunk]) -> list[Chunk]:
    groups: list[list[Chunk]] = []
    current: list[Chunk] = []
    current_words = 0

    for chunk in chunks:
        if current and current_words >= 150 and current_words + chunk.word_count > 700:
            groups.append(current)
            current = []
            current_words = 0
        current.append(chunk)
        current_words += chunk.word_count
        if current_words >= 150:
            groups.append(current)
            current = []
            current_words = 0

    if current:
        previous_words = sum(item.word_count for item in groups[-1]) if groups else 0
        if groups and previous_words + current_words <= 700:
            groups[-1].extend(current)
        else:
            groups.append(current)

    merged: list[Chunk] = []
    for ordinal, group in enumerate(groups, start=1):
        if len(group) == 1:
            merged.append(group[0])
            continue
        content_parts: list[str] = []
        for chunk in group:
            if chunk.heading == "Overview":
                content_parts.append(chunk.content)
            else:
                content_parts.append(f"## {chunk.heading}\n\n{chunk.content}")
        merged.append(
            _make_chunk(
                note,
                f"{group[0].heading} — {group[-1].heading}",
                "\n\n".join(content_parts),
                2,
                ordinal,
            )
        )
    return merged


def chunks_for_note(note: Note) -> list[Chunk]:
    chunks = _raw_chunks(note)
    if note.collection == "knowledge":
        return _merge_short_knowledge_chunks(note, chunks)
    return chunks
