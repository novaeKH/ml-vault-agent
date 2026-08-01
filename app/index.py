from __future__ import annotations

import json
import math
import sqlite3
import threading
from array import array
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.config import DATA_DIR, Settings
from app.ollama_client import OllamaError
from app.vault import Chunk, chunks_for_note, iter_markdown, read_note, tokenize


INDEX_FORMAT_VERSION = "3"


class Embedder(Protocol):
    def embed_documents(self, model: str, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, model: str, query: str) -> list[float]: ...


@dataclass(slots=True)
class SearchResult:
    chunk_id: str
    file_path: str
    title: str
    heading: str
    breadcrumb: str
    note_type: str
    area: str
    collection: str
    text: str
    excerpt: str
    score: float
    lexical_score: float
    semantic_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HybridIndex:
    def __init__(self, database_path: Path | None = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path or DATA_DIR / "index.sqlite3"
        self._write_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    indexed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS observed_files (
                    path TEXT PRIMARY KEY,
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    included INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    heading TEXT NOT NULL,
                    breadcrumb TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    note_type TEXT NOT NULL,
                    area TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    content TEXT NOT NULL,
                    text TEXT NOT NULL,
                    tokens_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    embedding_model TEXT,
                    embedding_dim INTEGER,
                    embedding BLOB
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_collection
                    ON chunks(collection);
                CREATE INDEX IF NOT EXISTS idx_chunks_file
                    ON chunks(file_path);
                """
            )

    @staticmethod
    def _encode_vector(vector: list[float]) -> bytes:
        return array("f", (float(value) for value in vector)).tobytes()

    @staticmethod
    def _decode_vector(blob: bytes | None) -> list[float] | None:
        if blob is None:
            return None
        values = array("f")
        values.frombytes(blob)
        return list(values)

    @staticmethod
    def _batches(items: list[Any], size: int) -> list[list[Any]]:
        return [items[index : index + size] for index in range(0, len(items), size)]

    @staticmethod
    def _search_tokens(chunk: Chunk) -> list[str]:
        boosted = " ".join(
            [
                chunk.title,
                chunk.title,
                chunk.title,
                chunk.heading,
                chunk.heading,
                " ".join(chunk.aliases),
                " ".join(chunk.aliases),
                chunk.content,
            ]
        )
        return tokenize(boosted)

    def _get_meta(self, connection: sqlite3.Connection, key: str) -> str:
        row = connection.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else ""

    def _set_meta(self, connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO meta(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def clear(self) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM files")
            connection.execute("DELETE FROM observed_files")
            connection.execute("DELETE FROM meta")

    def reindex(
        self,
        settings: Settings,
        embedder: Embedder | None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        vault_root = Path(settings.vault_path)
        if not vault_root.is_dir():
            raise ValueError("Vault не настроен или больше недоступен.")

        started = datetime.now(UTC)
        warnings: list[str] = []
        with self._write_lock, self._connect() as connection:
            existing = {
                row["path"]: row
                for row in connection.execute("SELECT * FROM files").fetchall()
            }
            observed = {
                row["path"]: row
                for row in connection.execute(
                    "SELECT * FROM observed_files"
                ).fetchall()
            }
            previous_vault = self._get_meta(connection, "vault_path")
            previous_model = self._get_meta(connection, "embedding_model")
            previous_format = self._get_meta(connection, "index_format_version")
            if previous_vault and previous_vault != str(vault_root.resolve()):
                force = True
            if previous_model and previous_model != settings.embedding_model:
                force = True
            if previous_format != INDEX_FORMAT_VERSION:
                force = True

            source_files: dict[str, tuple[Path, Any]] = {}
            for path in iter_markdown(vault_root):
                relative_path = path.relative_to(vault_root).as_posix()
                source_files[relative_path] = (path, path.stat())

            current_source_paths = set(source_files)
            removed_sources = sorted(set(observed) - current_source_paths)
            source_changes: list[str] = []
            for relative_path, (_, stat) in source_files.items():
                previous = observed.get(relative_path)
                if (
                    force
                    or previous is None
                    or previous["mtime_ns"] != stat.st_mtime_ns
                    or previous["size"] != stat.st_size
                ):
                    source_changes.append(relative_path)

            # Only new or stat-changed Markdown is opened. Unchanged files are
            # represented by their existing chunks and never re-embedded.
            parsed_changes: dict[str, tuple[Any | None, Any]] = {}
            for relative_path in source_changes:
                path, stat = source_files[relative_path]
                parsed_changes[relative_path] = (
                    read_note(vault_root, path),
                    stat,
                )

            changed = sorted(
                relative_path
                for relative_path, (note, _) in parsed_changes.items()
                if note is not None
            )
            current_indexed_paths = set(existing)
            current_indexed_paths.difference_update(removed_sources)
            for relative_path, (note, _) in parsed_changes.items():
                if note is None:
                    current_indexed_paths.discard(relative_path)
                else:
                    current_indexed_paths.add(relative_path)
            removed = sorted(set(existing) - current_indexed_paths)
            unchanged = sorted(current_indexed_paths - set(changed))

            prepared: dict[str, list[tuple[Chunk, list[float] | None]]] = {}
            all_chunks: list[tuple[str, Chunk]] = []
            for relative_path in changed:
                note, _ = parsed_changes[relative_path]
                assert note is not None
                note_chunks = chunks_for_note(note)
                prepared[relative_path] = []
                all_chunks.extend((relative_path, chunk) for chunk in note_chunks)

            embeddings: list[list[float] | None] = [None] * len(all_chunks)
            embeddings_ready = False
            if all_chunks and embedder is not None:
                try:
                    offset = 0
                    for batch in self._batches(all_chunks, 16):
                        vectors = embedder.embed_documents(
                            settings.embedding_model,
                            [chunk.text for _, chunk in batch],
                        )
                        if len(vectors) != len(batch):
                            raise OllamaError("Неполный пакет embeddings.")
                        embeddings[offset : offset + len(batch)] = vectors
                        offset += len(batch)
                    embeddings_ready = True
                except (OllamaError, ValueError, OSError) as error:
                    warnings.append(
                        "Semantic-индекс временно недоступен; lexical BM25 продолжает "
                        f"работать. Причина: {error}"
                    )

            for (relative_path, chunk), vector in zip(all_chunks, embeddings):
                prepared[relative_path].append((chunk, vector))

            now = datetime.now(UTC).isoformat()
            for relative_path in removed_sources:
                connection.execute(
                    "DELETE FROM observed_files WHERE path = ?", (relative_path,)
                )
            for relative_path in removed:
                connection.execute("DELETE FROM files WHERE path = ?", (relative_path,))

            for relative_path, (note, stat) in parsed_changes.items():
                connection.execute(
                    """
                    INSERT INTO observed_files(path, mtime_ns, size, included)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        mtime_ns = excluded.mtime_ns,
                        size = excluded.size,
                        included = excluded.included
                    """,
                    (
                        relative_path,
                        stat.st_mtime_ns,
                        stat.st_size,
                        int(note is not None),
                    ),
                )

            for relative_path in changed:
                note, stat = parsed_changes[relative_path]
                assert note is not None
                connection.execute("DELETE FROM files WHERE path = ?", (relative_path,))
                connection.execute(
                    """
                    INSERT INTO files(
                        path, mtime_ns, size, content_hash, collection, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        relative_path,
                        stat.st_mtime_ns,
                        stat.st_size,
                        note.content_hash,
                        note.collection,
                        now,
                    ),
                )
                for chunk, vector in prepared[relative_path]:
                    tokens = self._search_tokens(chunk)
                    connection.execute(
                        """
                        INSERT INTO chunks(
                            id, file_path, title, heading, breadcrumb, aliases_json,
                            note_type, area, collection, content, text, tokens_json,
                            content_hash, word_count, embedding_model, embedding_dim,
                            embedding
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk.chunk_id,
                            chunk.file_path,
                            chunk.title,
                            chunk.heading,
                            chunk.breadcrumb,
                            json.dumps(chunk.aliases, ensure_ascii=False),
                            chunk.note_type,
                            chunk.area,
                            chunk.collection,
                            chunk.content,
                            chunk.text,
                            json.dumps(tokens, ensure_ascii=False),
                            chunk.content_hash,
                            chunk.word_count,
                            settings.embedding_model if vector is not None else None,
                            len(vector) if vector is not None else None,
                            self._encode_vector(vector) if vector is not None else None,
                        ),
                    )

            # A lexical-only first pass is useful when Ollama was not started yet.
            # When it becomes available, fill only the missing vectors.
            missing_rows = connection.execute(
                """
                SELECT id, text FROM chunks
                WHERE embedding IS NULL OR embedding_model != ?
                ORDER BY id
                """,
                (settings.embedding_model,),
            ).fetchall()
            embedded_missing = 0
            if missing_rows and embedder is not None and (not all_chunks or embeddings_ready):
                try:
                    for batch in self._batches(list(missing_rows), 16):
                        vectors = embedder.embed_documents(
                            settings.embedding_model,
                            [row["text"] for row in batch],
                        )
                        for row, vector in zip(batch, vectors):
                            connection.execute(
                                """
                                UPDATE chunks
                                SET embedding_model = ?, embedding_dim = ?, embedding = ?
                                WHERE id = ?
                                """,
                                (
                                    settings.embedding_model,
                                    len(vector),
                                    self._encode_vector(vector),
                                    row["id"],
                                ),
                            )
                            embedded_missing += 1
                except (OllamaError, ValueError, OSError) as error:
                    if not warnings:
                        warnings.append(
                            "Индекс обновлён lexical-only; нажмите Reindex после запуска "
                            f"Ollama. Причина: {error}"
                        )

            self._set_meta(connection, "vault_path", str(vault_root.resolve()))
            self._set_meta(connection, "embedding_model", settings.embedding_model)
            self._set_meta(connection, "index_format_version", INDEX_FORMAT_VERSION)
            self._set_meta(connection, "updated_at", now)

            total_files = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            total_chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            vector_chunks = connection.execute(
                "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
            ).fetchone()[0]

        elapsed = (datetime.now(UTC) - started).total_seconds()
        return {
            "changed_files": len(changed),
            "unchanged_files": len(unchanged),
            "removed_files": len(removed),
            "scanned_files": len(source_files),
            "opened_files": len(source_changes),
            "total_files": total_files,
            "total_chunks": total_chunks,
            "vector_chunks": vector_chunks,
            "embedded_missing": embedded_missing,
            "elapsed_seconds": round(elapsed, 2),
            "warnings": warnings,
        }

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            files = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            vectors = connection.execute(
                "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
            ).fetchone()[0]
            collections = {
                row["collection"]: row["count"]
                for row in connection.execute(
                    """
                    SELECT collection, COUNT(*) AS count
                    FROM chunks GROUP BY collection
                    """
                )
            }
            return {
                "files": files,
                "chunks": chunks,
                "vector_chunks": vectors,
                "collections": collections,
                "vault_path": self._get_meta(connection, "vault_path"),
                "embedding_model": self._get_meta(connection, "embedding_model"),
                "updated_at": self._get_meta(connection, "updated_at"),
            }

    @staticmethod
    def _bm25(rows: list[sqlite3.Row], query_tokens: list[str]) -> dict[str, float]:
        if not rows or not query_tokens:
            return {}
        documents = [json.loads(row["tokens_json"]) for row in rows]
        lengths = [len(document) for document in documents]
        average_length = sum(lengths) / max(len(lengths), 1)
        document_frequency: Counter[str] = Counter()
        for document in documents:
            document_frequency.update(set(document))

        scores: dict[str, float] = {}
        k1 = 1.5
        b = 0.75
        query_counts = Counter(query_tokens)
        total = len(documents)
        for row, document, length in zip(rows, documents, lengths):
            frequencies = Counter(document)
            score = 0.0
            for token, query_weight in query_counts.items():
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                df = document_frequency[token]
                inverse_document_frequency = math.log(
                    1 + (total - df + 0.5) / (df + 0.5)
                )
                denominator = frequency + k1 * (
                    1 - b + b * length / max(average_length, 1)
                )
                score += (
                    inverse_document_frequency
                    * (frequency * (k1 + 1) / denominator)
                    * min(query_weight, 2)
                )
            if score > 0:
                scores[row["id"]] = score
        return scores

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return -1.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return -1.0
        return dot / (left_norm * right_norm)

    def search(
        self,
        query: str,
        settings: Settings,
        embedder: Embedder | None,
        *,
        mode: str = "chat",
        top_k: int | None = None,
    ) -> list[SearchResult]:
        collections_by_mode = {
            "interviewer": ["knowledge", "interview"],
            "practice": ["knowledge", "practice"],
            "code": ["knowledge", "practice", "solution"],
        }
        collections = collections_by_mode.get(mode, ["knowledge"])
        placeholders = ",".join("?" for _ in collections)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chunks WHERE collection IN ({placeholders})",
                collections,
            ).fetchall()
        if not rows:
            return []

        lexical_scores = self._bm25(rows, tokenize(query))
        lexical_rank = sorted(
            lexical_scores, key=lexical_scores.get, reverse=True
        )

        semantic_scores: dict[str, float] = {}
        if embedder is not None and any(row["embedding"] is not None for row in rows):
            try:
                query_vector = embedder.embed_query(settings.embedding_model, query)
                for row in rows:
                    vector = self._decode_vector(row["embedding"])
                    if vector is not None:
                        score = self._cosine(query_vector, vector)
                        if score > -1:
                            semantic_scores[row["id"]] = score
            except (OllamaError, ValueError, OSError):
                semantic_scores = {}
        semantic_rank = sorted(
            semantic_scores, key=semantic_scores.get, reverse=True
        )

        fused: defaultdict[str, float] = defaultdict(float)
        for rank, chunk_id in enumerate(lexical_rank[:80], start=1):
            fused[chunk_id] += 0.48 / (60 + rank)
        for rank, chunk_id in enumerate(semantic_rank[:80], start=1):
            fused[chunk_id] += 0.52 / (60 + rank)
        if not semantic_rank:
            for rank, chunk_id in enumerate(lexical_rank[:80], start=1):
                fused[chunk_id] += 0.52 / (60 + rank)
        if not lexical_rank:
            for rank, chunk_id in enumerate(semantic_rank[:80], start=1):
                fused[chunk_id] += 0.48 / (60 + rank)

        by_id = {row["id"]: row for row in rows}
        if mode == "interviewer":
            for chunk_id in fused:
                if by_id[chunk_id]["collection"] == "interview":
                    fused[chunk_id] *= 1.08
        if mode == "practice":
            for chunk_id in fused:
                if by_id[chunk_id]["collection"] == "practice":
                    fused[chunk_id] *= 1.12
        if mode == "code":
            for chunk_id in fused:
                if by_id[chunk_id]["collection"] in {"practice", "solution"}:
                    fused[chunk_id] *= 1.08

        ordered = sorted(fused, key=fused.get, reverse=True)
        limit = top_k or settings.top_k
        per_file: defaultdict[str, int] = defaultdict(int)
        selected: list[str] = []
        for chunk_id in ordered:
            file_path = by_id[chunk_id]["file_path"]
            if per_file[file_path] >= 2:
                continue
            selected.append(chunk_id)
            per_file[file_path] += 1
            if len(selected) >= limit:
                break

        maximum = max((fused[item] for item in selected), default=1.0)
        results: list[SearchResult] = []
        for chunk_id in selected:
            row = by_id[chunk_id]
            content = row["content"].strip()
            excerpt = " ".join(content.replace("\n", " ").split())
            if len(excerpt) > 240:
                excerpt = excerpt[:237].rstrip() + "…"
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    file_path=row["file_path"],
                    title=row["title"],
                    heading=row["heading"],
                    breadcrumb=row["breadcrumb"],
                    note_type=row["note_type"],
                    area=row["area"],
                    collection=row["collection"],
                    text=row["text"],
                    excerpt=excerpt,
                    score=round(fused[chunk_id] / maximum, 4),
                    lexical_score=round(lexical_scores.get(chunk_id, 0.0), 4),
                    semantic_score=(
                        round(semantic_scores[chunk_id], 4)
                        if chunk_id in semantic_scores
                        else None
                    ),
                )
            )
        return results
