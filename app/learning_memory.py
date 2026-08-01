from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from app.config import DATA_DIR
from app.learning_catalog import EVIDENCE_KINDS, SKILL_AXES


DATABASE_VERSION = 1
DEFAULT_MEMORY_PATH = DATA_DIR / "learning.sqlite3"
RESULTS = frozenset({"success", "partial", "failure"})
EVIDENCE_WEIGHTS = {
    "deterministic": 1.0,
    "rubric": 0.75,
    "agent": 0.35,
    "self_report": 0.25,
}
MAX_EVENTS_PER_AXIS = 8
RECENCY_FACTOR = 0.88
REVIEW_INTERVALS = (1, 3, 7, 14, 30)

Result = Literal["success", "partial", "failure"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def result_for_score(score: float) -> Result:
    if score >= 0.8:
        return "success"
    if score >= 0.5:
        return "partial"
    return "failure"


def _next_success_interval(previous: int) -> int:
    for interval in REVIEW_INTERVALS:
        if interval > previous:
            return interval
    return REVIEW_INTERVALS[-1]


class LearningMemory:
    """Local, inspectable evidence memory kept separately from the vault."""

    def __init__(self, path: str | Path = DEFAULT_MEMORY_PATH) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self) -> None:
        with self._lock, self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > DATABASE_VERSION:
                raise RuntimeError(
                    f"Learning memory schema {version} is newer than supported "
                    f"version {DATABASE_VERSION}."
                )
            if version == 0:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS learning_evidence (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_uuid TEXT NOT NULL UNIQUE,
                        skill_id TEXT NOT NULL,
                        axis TEXT NOT NULL CHECK (
                            axis IN ('recall', 'explain', 'apply', 'diagnose')
                        ),
                        activity_id TEXT NOT NULL DEFAULT '',
                        evidence_kind TEXT NOT NULL CHECK (
                            evidence_kind IN (
                                'deterministic', 'rubric', 'agent', 'self_report'
                            )
                        ),
                        score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
                        confidence REAL NOT NULL CHECK (
                            confidence >= 0 AND confidence <= 1
                        ),
                        result TEXT NOT NULL CHECK (
                            result IN ('success', 'partial', 'failure')
                        ),
                        error_code TEXT,
                        note TEXT NOT NULL DEFAULT '',
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        dismissed_at TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_learning_evidence_skill
                    ON learning_evidence(skill_id, created_at DESC, id DESC);

                    CREATE INDEX IF NOT EXISTS idx_learning_evidence_active
                    ON learning_evidence(skill_id, axis, dismissed_at, created_at DESC);

                    CREATE TABLE IF NOT EXISTS learning_review_state (
                        skill_id TEXT PRIMARY KEY,
                        interval_days INTEGER NOT NULL DEFAULT 0,
                        success_streak INTEGER NOT NULL DEFAULT 0,
                        lapse_count INTEGER NOT NULL DEFAULT 0,
                        last_reviewed_at TEXT NOT NULL,
                        next_review_at TEXT NOT NULL
                    );

                    PRAGMA user_version = 1;
                    """
                )

    def record_evidence(
        self,
        *,
        skill_id: str,
        axis: str,
        evidence_kind: str,
        score: float,
        confidence: float,
        activity_id: str = "",
        error_code: str | None = None,
        note: str = "",
        details: dict[str, Any] | None = None,
        created_at: datetime | None = None,
        event_uuid: str | None = None,
        schedule_review: bool = True,
    ) -> dict[str, Any]:
        skill_id = skill_id.strip()
        if not skill_id:
            raise ValueError("skill_id must not be empty")
        if axis not in SKILL_AXES:
            raise ValueError(f"Unknown skill axis: {axis}")
        if evidence_kind not in EVIDENCE_KINDS:
            raise ValueError(f"Unknown evidence kind: {evidence_kind}")
        if isinstance(score, bool) or not 0 <= float(score) <= 1:
            raise ValueError("score must be between 0 and 1")
        if isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")

        moment = _as_utc(created_at)
        result = result_for_score(float(score))
        identifier = event_uuid or uuid.uuid4().hex
        serialized_details = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)

        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO learning_evidence (
                    event_uuid, skill_id, axis, activity_id, evidence_kind,
                    score, confidence, result, error_code, note, details_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    skill_id,
                    axis,
                    activity_id.strip(),
                    evidence_kind,
                    float(score),
                    float(confidence),
                    result,
                    error_code.strip() if error_code else None,
                    note.strip(),
                    serialized_details,
                    _timestamp(moment),
                ),
            )
            event_id = int(cursor.lastrowid)
            if schedule_review:
                self._update_review_state(connection, skill_id, result, moment)
            row = connection.execute(
                "SELECT * FROM learning_evidence WHERE id = ?", (event_id,)
            ).fetchone()
        return self._row_to_event(row)

    def _update_review_state(
        self,
        connection: sqlite3.Connection,
        skill_id: str,
        result: Result,
        moment: datetime,
    ) -> None:
        previous = connection.execute(
            "SELECT * FROM learning_review_state WHERE skill_id = ?", (skill_id,)
        ).fetchone()
        previous_interval = int(previous["interval_days"]) if previous else 0
        previous_streak = int(previous["success_streak"]) if previous else 0
        previous_lapses = int(previous["lapse_count"]) if previous else 0

        if result == "success":
            interval = _next_success_interval(previous_interval)
            streak = previous_streak + 1
            lapses = previous_lapses
        elif result == "partial":
            interval = 1
            streak = 0
            lapses = previous_lapses
        else:
            interval = 1
            streak = 0
            lapses = previous_lapses + 1

        connection.execute(
            """
            INSERT INTO learning_review_state (
                skill_id, interval_days, success_streak, lapse_count,
                last_reviewed_at, next_review_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                interval_days = excluded.interval_days,
                success_streak = excluded.success_streak,
                lapse_count = excluded.lapse_count,
                last_reviewed_at = excluded.last_reviewed_at,
                next_review_at = excluded.next_review_at
            """,
            (
                skill_id,
                interval,
                streak,
                lapses,
                _timestamp(moment),
                _timestamp(moment + timedelta(days=interval)),
            ),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "event_uuid": row["event_uuid"],
            "skill_id": row["skill_id"],
            "axis": row["axis"],
            "activity_id": row["activity_id"],
            "evidence_kind": row["evidence_kind"],
            "score": float(row["score"]),
            "confidence": float(row["confidence"]),
            "result": row["result"],
            "error_code": row["error_code"],
            "note": row["note"],
            "details": json.loads(row["details_json"] or "{}"),
            "created_at": row["created_at"],
            "dismissed_at": row["dismissed_at"],
        }

    def evidence(
        self,
        *,
        skill_id: str | None = None,
        include_dismissed: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if skill_id:
            clauses.append("skill_id = ?")
            parameters.append(skill_id)
        if not include_dismissed:
            clauses.append("dismissed_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(int(limit), 500)))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM learning_evidence
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def set_dismissed(
        self,
        event_id: int,
        *,
        dismissed: bool = True,
        changed_at: datetime | None = None,
    ) -> dict[str, Any]:
        value = _timestamp(_as_utc(changed_at)) if dismissed else None
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE learning_evidence SET dismissed_at = ? WHERE id = ?",
                (value, int(event_id)),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Evidence {event_id} does not exist")
            row = connection.execute(
                "SELECT * FROM learning_evidence WHERE id = ?", (int(event_id),)
            ).fetchone()
            self._rebuild_review_state(connection, row["skill_id"])
        return self._row_to_event(row)

    def _rebuild_review_state(
        self,
        connection: sqlite3.Connection,
        skill_id: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT result, created_at
            FROM learning_evidence
            WHERE skill_id = ? AND dismissed_at IS NULL
            ORDER BY created_at, id
            """,
            (skill_id,),
        ).fetchall()
        connection.execute(
            "DELETE FROM learning_review_state WHERE skill_id = ?", (skill_id,)
        )
        for evidence in rows:
            moment = datetime.fromisoformat(evidence["created_at"])
            self._update_review_state(
                connection,
                skill_id,
                evidence["result"],
                moment,
            )

    @staticmethod
    def _axis_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            return {
                "level": "unseen",
                "score": None,
                "evidence_count": 0,
                "reliability": "none",
            }

        selected = events[:MAX_EVENTS_PER_AXIS]
        weighted_score = 0.0
        total_weight = 0.0
        for position, event in enumerate(selected):
            weight = (
                EVIDENCE_WEIGHTS[event["evidence_kind"]]
                * event["confidence"]
                * (RECENCY_FACTOR**position)
            )
            weighted_score += event["score"] * weight
            total_weight += weight
        score = weighted_score / total_weight if total_weight else 0.0
        if score < 0.45:
            level = "needs_work"
        elif score < 0.7:
            level = "developing"
        elif score < 0.85 or len(selected) < 2:
            level = "reliable"
        else:
            level = "strong"
        if total_weight >= 2:
            reliability = "high"
        elif total_weight >= 0.8:
            reliability = "medium"
        else:
            reliability = "low"
        return {
            "level": level,
            "score": round(score, 3),
            "evidence_count": len(selected),
            "reliability": reliability,
        }

    @staticmethod
    def _active_errors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        negatives: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            if event["error_code"] and event["result"] != "success":
                negatives[event["error_code"]].append(event)

        active: list[dict[str, Any]] = []
        for code, failures in negatives.items():
            if len(failures) < 2:
                continue
            latest_failure = failures[0]
            successes_after = sum(
                event["result"] == "success"
                and event["created_at"] > latest_failure["created_at"]
                for event in events
            )
            if successes_after >= 2:
                continue
            active.append(
                {
                    "code": code,
                    "observations": len(failures),
                    "latest_at": latest_failure["created_at"],
                }
            )
        return sorted(active, key=lambda item: item["latest_at"], reverse=True)

    def review_state(self, skill_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE skill_id = ?" if skill_id else ""
        parameters = (skill_id,) if skill_id else ()
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM learning_review_state
                {where}
                ORDER BY next_review_at, skill_id
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def skill_profile(self, skill_id: str) -> dict[str, Any]:
        events = self.evidence(skill_id=skill_id, limit=500)
        by_axis: dict[str, list[dict[str, Any]]] = {
            axis: [] for axis in sorted(SKILL_AXES)
        }
        for event in events:
            by_axis[event["axis"]].append(event)
        reviews = self.review_state(skill_id)
        review = reviews[0] if reviews else None
        return {
            "skill_id": skill_id,
            "axes": {
                axis: self._axis_summary(axis_events)
                for axis, axis_events in by_axis.items()
            },
            "active_errors": self._active_errors(events),
            "evidence_count": len(events),
            "review": review,
        }

    def overview(self, catalog: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        moment = _as_utc(now)
        skills: list[dict[str, Any]] = []
        skill_states: dict[str, dict[str, Any]] = {}
        for skill in catalog["skills"]:
            profile = self.skill_profile(skill["id"])
            review = profile["review"]
            profile["due"] = bool(
                review and review["next_review_at"] <= _timestamp(moment)
            )
            combined = {
                "id": skill["id"],
                "title": skill["title"],
                "description": skill["description"],
                "priority": skill["priority"],
                "stage_id": skill["stage_id"],
                "prerequisites": skill["prerequisites"],
                **profile,
            }
            skills.append(combined)
            skill_states[skill["id"]] = combined

        due = [skill["id"] for skill in skills if skill["due"]]
        weak = [
            skill["id"]
            for skill in skills
            if skill["active_errors"]
            or any(
                axis["level"] == "needs_work" for axis in skill["axes"].values()
            )
        ]
        started = [skill["id"] for skill in skills if skill["evidence_count"] > 0]
        return {
            "catalog": {
                "id": catalog["catalog_id"],
                "title": catalog["title"],
                "reviewed_at": catalog["reviewed_at"],
                "roadmap_optional": catalog["roadmap"]["optional"],
            },
            "summary": {
                "skills_total": len(skills),
                "skills_started": len(started),
                "due_count": len(due),
                "weak_count": len(weak),
            },
            "due_skill_ids": due,
            "weak_skill_ids": weak,
            "skills": skills,
            "stages": catalog["roadmap"]["stages"],
            "sources": catalog["roadmap"]["sources"],
        }
