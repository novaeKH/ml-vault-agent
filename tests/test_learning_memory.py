import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.learning_memory import LearningMemory


NOW = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)


def make_memory(tmp_path: Path) -> LearningMemory:
    return LearningMemory(tmp_path / "learning.sqlite3")


def test_empty_profile_has_four_visible_unseen_axes(tmp_path: Path):
    profile = make_memory(tmp_path).skill_profile("ml.validation")

    assert set(profile["axes"]) == {"recall", "explain", "apply", "diagnose"}
    assert {item["level"] for item in profile["axes"].values()} == {"unseen"}
    assert profile["evidence_count"] == 0


def test_mastery_is_weighted_and_dismissal_is_reversible(tmp_path: Path):
    memory = make_memory(tmp_path)
    strong = memory.record_evidence(
        skill_id="ml.validation",
        axis="apply",
        evidence_kind="rubric",
        score=1.0,
        confidence=0.8,
        created_at=NOW,
    )
    memory.record_evidence(
        skill_id="ml.validation",
        axis="apply",
        evidence_kind="self_report",
        score=0.0,
        confidence=0.4,
        created_at=NOW - timedelta(minutes=1),
    )

    with_both = memory.skill_profile("ml.validation")["axes"]["apply"]
    memory.set_dismissed(strong["id"], changed_at=NOW)
    without_strong = memory.skill_profile("ml.validation")["axes"]["apply"]
    dismissed_review = memory.review_state("ml.validation")[0]
    memory.set_dismissed(strong["id"], dismissed=False)
    restored = memory.skill_profile("ml.validation")["axes"]["apply"]
    restored_review = memory.review_state("ml.validation")[0]

    assert with_both["score"] > without_strong["score"]
    assert without_strong["level"] == "needs_work"
    assert dismissed_review["success_streak"] == 0
    assert restored == with_both
    assert restored_review["success_streak"] == 1


def test_one_mistake_is_not_a_persistent_weakness(tmp_path: Path):
    memory = make_memory(tmp_path)
    memory.record_evidence(
        skill_id="ml.leakage",
        axis="diagnose",
        evidence_kind="rubric",
        score=0.2,
        confidence=0.7,
        error_code="data_leakage",
        created_at=NOW,
    )

    assert memory.skill_profile("ml.leakage")["active_errors"] == []

    memory.record_evidence(
        skill_id="ml.leakage",
        axis="diagnose",
        evidence_kind="rubric",
        score=0.4,
        confidence=0.7,
        error_code="data_leakage",
        created_at=NOW + timedelta(minutes=1),
    )

    errors = memory.skill_profile("ml.leakage")["active_errors"]
    assert errors[0]["code"] == "data_leakage"
    assert errors[0]["observations"] == 2


def test_review_schedule_advances_and_resets(tmp_path: Path):
    memory = make_memory(tmp_path)

    for day in (0, 1, 4):
        memory.record_evidence(
            skill_id="ml.metrics",
            axis="apply",
            evidence_kind="deterministic",
            score=0.9,
            confidence=1.0,
            created_at=NOW + timedelta(days=day),
        )

    review = memory.review_state("ml.metrics")[0]
    assert review["interval_days"] == 7
    assert review["success_streak"] == 3

    memory.record_evidence(
        skill_id="ml.metrics",
        axis="apply",
        evidence_kind="deterministic",
        score=0.1,
        confidence=1.0,
        created_at=NOW + timedelta(days=11),
    )
    reset = memory.review_state("ml.metrics")[0]
    assert reset["interval_days"] == 1
    assert reset["success_streak"] == 0
    assert reset["lapse_count"] == 1


def test_rejects_invalid_evidence(tmp_path: Path):
    memory = make_memory(tmp_path)

    with pytest.raises(ValueError, match="Unknown skill axis"):
        memory.record_evidence(
            skill_id="ml.metrics",
            axis="intuition",
            evidence_kind="rubric",
            score=0.5,
            confidence=0.5,
        )


def test_memory_persists_between_instances(tmp_path: Path):
    path = tmp_path / "learning.sqlite3"
    first = LearningMemory(path)
    first.record_evidence(
        skill_id="ml.framing",
        axis="explain",
        evidence_kind="self_report",
        score=0.7,
        confidence=0.4,
        created_at=NOW,
    )

    second = LearningMemory(path)
    assert second.skill_profile("ml.framing")["evidence_count"] == 1


def test_newer_unknown_database_schema_is_rejected(tmp_path: Path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(RuntimeError, match="newer than supported"):
        LearningMemory(path)


def test_overview_needs_repeated_evidence_before_calling_skill_weak(tmp_path: Path):
    memory = make_memory(tmp_path)
    catalog = {
        "catalog_id": "test",
        "title": "Test",
        "reviewed_at": "2026-08-02",
        "roadmap": {"optional": True, "stages": [], "sources": []},
        "skills": [
            {
                "id": "ml.validation",
                "title": "Validation",
                "description": "Honest evaluation.",
                "priority": "core",
                "stage_id": "evaluation",
                "prerequisites": [],
            }
        ],
    }
    memory.record_evidence(
        skill_id="ml.validation",
        axis="apply",
        evidence_kind="rubric",
        score=0.2,
        confidence=0.7,
        created_at=NOW,
    )

    assert memory.overview(catalog, now=NOW)["summary"]["weak_count"] == 0

    memory.record_evidence(
        skill_id="ml.validation",
        axis="apply",
        evidence_kind="rubric",
        score=0.2,
        confidence=0.7,
        created_at=NOW + timedelta(minutes=1),
    )
    assert memory.overview(catalog, now=NOW)["summary"]["weak_count"] == 1
