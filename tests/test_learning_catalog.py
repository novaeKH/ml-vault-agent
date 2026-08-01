import json
from pathlib import Path

import pytest

from app.learning_catalog import CatalogError, load_catalog, validate_catalog


def valid_catalog() -> dict:
    return {
        "schema_version": 1,
        "catalog_id": "test-v1",
        "title": "Test catalog",
        "language": "ru",
        "reviewed_at": "2026-08-02",
        "roadmap": {
            "optional": True,
            "description": "Optional expert-backed route.",
            "sources": [
                {
                    "id": "source",
                    "title": "Course",
                    "organization": "University",
                    "url": "https://example.com/course",
                    "audience": "ML learners",
                    "reviewed_at": "2026-08-02",
                }
            ],
            "stages": [
                {
                    "id": "foundation",
                    "title": "Foundation",
                    "description": "Start here.",
                    "skill_ids": ["ml.framing"],
                    "source_ids": ["source"],
                }
            ],
        },
        "error_taxonomy": ["wrong_assumption"],
        "skills": [
            {
                "id": "ml.framing",
                "stage_id": "foundation",
                "title": "Framing",
                "description": "Frame an ML task.",
                "priority": "core",
                "prerequisites": [],
                "note_paths": ["Knowledge/Framing.md"],
                "outcomes": ["Define a prediction contract."],
                "diagnostics": [
                    {
                        "id": "diag.framing.1",
                        "axis": "apply",
                        "prompt": "Frame this task.",
                        "rubric": [
                            {
                                "id": "contract",
                                "description": "Defines the contract.",
                                "weight": 1.0,
                            }
                        ],
                        "error_codes": ["wrong_assumption"],
                    }
                ],
            }
        ],
    }


def make_vault(tmp_path: Path, catalog: dict) -> Path:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Knowledge").mkdir()
    (vault / "Knowledge" / "Framing.md").write_text("# Framing\n", encoding="utf-8")
    (vault / "_meta").mkdir()
    payload = json.dumps(catalog, ensure_ascii=False, indent=2)
    (vault / "_meta" / "LEARNING_CATALOG.md").write_text(
        f"# Catalog\n\n```learning-catalog\n{payload}\n```\n",
        encoding="utf-8",
    )
    return vault


def test_loads_valid_catalog_and_checks_note_paths(tmp_path: Path):
    catalog = valid_catalog()
    vault = make_vault(tmp_path, catalog)

    loaded = load_catalog(vault)

    assert loaded["catalog_id"] == "test-v1"
    assert loaded["skills"][0]["diagnostics"][0]["axis"] == "apply"


def test_missing_linked_note_is_actionable(tmp_path: Path):
    catalog = valid_catalog()
    catalog["skills"][0]["note_paths"] = ["Knowledge/Missing.md"]
    vault = make_vault(tmp_path, catalog)

    with pytest.raises(CatalogError, match="note does not exist"):
        load_catalog(vault)


def test_rejects_unknown_error_code_and_bad_weights():
    catalog = valid_catalog()
    question = catalog["skills"][0]["diagnostics"][0]
    question["error_codes"] = ["invented_error"]
    question["rubric"][0]["weight"] = 0.5

    with pytest.raises(CatalogError) as captured:
        validate_catalog(catalog)

    message = str(captured.value)
    assert "unknown error code" in message
    assert "weights must sum to 1.0" in message


def test_rejects_prerequisite_cycle():
    catalog = valid_catalog()
    original = catalog["skills"][0]
    second = {
        **original,
        "id": "ml.second",
        "title": "Second",
        "prerequisites": ["ml.framing"],
        "diagnostics": [
            {
                **original["diagnostics"][0],
                "id": "diag.second.1",
            }
        ],
    }
    catalog["skills"].append(second)
    catalog["skills"][0]["prerequisites"] = ["ml.second"]
    catalog["roadmap"]["stages"][0]["skill_ids"].append("ml.second")

    with pytest.raises(CatalogError, match="cycle detected"):
        validate_catalog(catalog)
