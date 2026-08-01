from pathlib import Path

from app.config import Settings
from app.learning_memory import LearningMemory
from app.main import (
    DiagnoseRequest,
    DismissEvidenceRequest,
    LearningEvidenceRequest,
    add_learning_evidence,
    diagnose_learning_answer,
    dismiss_learning_evidence,
    learning_overview,
    state,
)


CATALOG = {
    "catalog_id": "test-v1",
    "title": "Test learning",
    "reviewed_at": "2026-08-02",
    "error_taxonomy": ["wrong_validation"],
    "roadmap": {
        "optional": True,
        "sources": [],
        "stages": [
            {
                "id": "evaluation",
                "title": "Evaluation",
                "description": "Validate honestly.",
                "skill_ids": ["ml.validation"],
                "source_ids": [],
            }
        ],
    },
    "skills": [
        {
            "id": "ml.validation",
            "stage_id": "evaluation",
            "title": "Validation",
            "description": "Honest split.",
            "priority": "core",
            "prerequisites": [],
            "note_paths": ["Validation.md"],
            "outcomes": ["Choose a split."],
            "diagnostics": [
                {
                    "id": "diag.validation.1",
                    "axis": "apply",
                    "prompt": "Choose a split.",
                    "rubric": [
                        {
                            "id": "time",
                            "description": "Keeps time order.",
                            "weight": 1.0,
                        }
                    ],
                    "error_codes": ["wrong_validation"],
                }
            ],
        }
    ],
}


def configure_test_state(tmp_path: Path, monkeypatch) -> LearningMemory:
    memory = LearningMemory(tmp_path / "learning.sqlite3")
    monkeypatch.setattr(state, "learning", memory)
    monkeypatch.setattr(
        state,
        "settings",
        Settings(vault_path="/configured", chat_model="fake-model"),
    )
    monkeypatch.setattr("app.main.load_catalog", lambda _: CATALOG)
    return memory


def test_overview_is_available_with_a_catalog(tmp_path: Path, monkeypatch):
    configure_test_state(tmp_path, monkeypatch)

    payload = learning_overview()

    assert payload["available"] is True
    assert payload["summary"]["skills_total"] == 1
    assert payload["skills"][0]["axes"]["apply"]["level"] == "unseen"


def test_diagnosis_records_medium_confidence_rubric_evidence(
    tmp_path: Path,
    monkeypatch,
):
    memory = configure_test_state(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.main.review_answer",
        lambda *args, **kwargs: {
            "score": 0.5,
            "feedback": "Временной порядок указан не полностью.",
            "error_code": "wrong_validation",
            "criteria": [{"id": "time", "credit": 0.5, "comment": "неполно"}],
        },
    )

    payload = diagnose_learning_answer(
        DiagnoseRequest(
            skill_id="ml.validation",
            diagnostic_id="diag.validation.1",
            answer="Разделю данные по времени.",
        )
    )

    assert payload["evidence"]["evidence_kind"] == "rubric"
    assert payload["evidence"]["confidence"] == 0.7
    assert memory.skill_profile("ml.validation")["evidence_count"] == 1


def test_self_report_can_be_dismissed_and_restored(tmp_path: Path, monkeypatch):
    configure_test_state(tmp_path, monkeypatch)
    created = add_learning_evidence(
        LearningEvidenceRequest(
            skill_id="ml.validation",
            axis="recall",
            score=0.3,
            note="Путаю роли validation и test.",
            error_code="wrong_validation",
        )
    )["evidence"]

    dismissed = dismiss_learning_evidence(
        created["id"], DismissEvidenceRequest(dismissed=True)
    )
    restored = dismiss_learning_evidence(
        created["id"], DismissEvidenceRequest(dismissed=False)
    )

    assert dismissed["profile"]["evidence_count"] == 0
    assert restored["profile"]["evidence_count"] == 1
