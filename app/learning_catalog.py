from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CATALOG_RELATIVE_PATH = Path("_meta") / "LEARNING_CATALOG.md"
CATALOG_BLOCK = re.compile(
    r"```learning-catalog[ \t]*\r?\n(?P<payload>.*?)\r?\n```",
    re.DOTALL,
)
SKILL_AXES = frozenset({"recall", "explain", "apply", "diagnose"})
EVIDENCE_KINDS = frozenset({"deterministic", "rubric", "agent", "self_report"})


class CatalogError(ValueError):
    """Raised when a vault learning catalog violates the public contract."""


def _required_string(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: expected a non-empty string")
        return ""
    return value.strip()


def _unique_ids(
    items: Any,
    path: str,
    errors: list[str],
) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(items, list):
        errors.append(f"{path}: expected a list")
        return [], set()
    valid_items: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_path}: expected an object")
            continue
        identifier = _required_string(item.get("id"), f"{item_path}.id", errors)
        if identifier in identifiers:
            errors.append(f"{item_path}.id: duplicate id {identifier!r}")
        elif identifier:
            identifiers.add(identifier)
        valid_items.append(item)
    return valid_items, identifiers


def _validate_source(source: dict[str, Any], path: str, errors: list[str]) -> None:
    for field in ("title", "organization", "audience", "reviewed_at"):
        _required_string(source.get(field), f"{path}.{field}", errors)
    url = _required_string(source.get("url"), f"{path}.url", errors)
    parsed = urlparse(url)
    if url and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
        errors.append(f"{path}.url: expected an absolute http(s) URL")


def _validate_note_path(
    raw_path: Any,
    path: str,
    vault_root: Path | None,
    errors: list[str],
) -> None:
    note_path = _required_string(raw_path, path, errors)
    if not note_path:
        return
    relative = Path(note_path)
    if relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{path}: note path must stay inside the vault")
        return
    if relative.suffix.lower() != ".md":
        errors.append(f"{path}: linked learning content must be Markdown")
    if vault_root is not None and not (vault_root / relative).is_file():
        errors.append(f"{path}: note does not exist: {note_path}")


def _validate_diagnostic(
    diagnostic: dict[str, Any],
    path: str,
    taxonomy: set[str],
    errors: list[str],
) -> None:
    axis = _required_string(diagnostic.get("axis"), f"{path}.axis", errors)
    if axis and axis not in SKILL_AXES:
        errors.append(
            f"{path}.axis: expected one of {', '.join(sorted(SKILL_AXES))}"
        )
    _required_string(diagnostic.get("prompt"), f"{path}.prompt", errors)

    rubric, rubric_ids = _unique_ids(diagnostic.get("rubric"), f"{path}.rubric", errors)
    if not rubric:
        errors.append(f"{path}.rubric: at least one criterion is required")
    total_weight = 0.0
    for index, criterion in enumerate(rubric):
        criterion_path = f"{path}.rubric[{index}]"
        _required_string(
            criterion.get("description"),
            f"{criterion_path}.description",
            errors,
        )
        weight = criterion.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            errors.append(f"{criterion_path}.weight: expected a number")
            continue
        if not 0 < float(weight) <= 1:
            errors.append(f"{criterion_path}.weight: expected 0 < weight <= 1")
        total_weight += float(weight)
    if rubric_ids and abs(total_weight - 1.0) > 0.001:
        errors.append(f"{path}.rubric: weights must sum to 1.0, got {total_weight:g}")

    error_codes = diagnostic.get("error_codes")
    if not isinstance(error_codes, list) or not error_codes:
        errors.append(f"{path}.error_codes: expected a non-empty list")
    else:
        for index, code in enumerate(error_codes):
            code_path = f"{path}.error_codes[{index}]"
            value = _required_string(code, code_path, errors)
            if value and value not in taxonomy:
                errors.append(f"{code_path}: unknown error code {value!r}")


def _find_cycle(prerequisites: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(skill_id: str, trail: list[str]) -> list[str] | None:
        if skill_id in visiting:
            start = trail.index(skill_id)
            return [*trail[start:], skill_id]
        if skill_id in visited:
            return None
        visiting.add(skill_id)
        trail.append(skill_id)
        for prerequisite in prerequisites.get(skill_id, []):
            cycle = visit(prerequisite, trail)
            if cycle:
                return cycle
        trail.pop()
        visiting.remove(skill_id)
        visited.add(skill_id)
        return None

    for identifier in prerequisites:
        cycle = visit(identifier, [])
        if cycle:
            return cycle
    return None


def validate_catalog(
    catalog: Any,
    *,
    vault_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate and return a learning catalog, or raise one actionable error."""

    errors: list[str] = []
    if not isinstance(catalog, dict):
        raise CatalogError("catalog: expected a JSON object")

    root = Path(vault_root).expanduser().resolve() if vault_root else None
    if catalog.get("schema_version") != 1:
        errors.append("schema_version: only version 1 is supported")
    for field in ("catalog_id", "title", "language", "reviewed_at"):
        _required_string(catalog.get(field), field, errors)

    taxonomy_value = catalog.get("error_taxonomy")
    taxonomy: set[str] = set()
    if not isinstance(taxonomy_value, list) or not taxonomy_value:
        errors.append("error_taxonomy: expected a non-empty list")
    else:
        for index, raw_code in enumerate(taxonomy_value):
            code = _required_string(raw_code, f"error_taxonomy[{index}]", errors)
            if code in taxonomy:
                errors.append(f"error_taxonomy[{index}]: duplicate code {code!r}")
            taxonomy.add(code)

    roadmap = catalog.get("roadmap")
    if not isinstance(roadmap, dict):
        errors.append("roadmap: expected an object")
        roadmap = {}
    if roadmap.get("optional") is not True:
        errors.append("roadmap.optional: version 1 roadmaps must be optional")
    _required_string(roadmap.get("description"), "roadmap.description", errors)
    sources, source_ids = _unique_ids(roadmap.get("sources"), "roadmap.sources", errors)
    for index, source in enumerate(sources):
        _validate_source(source, f"roadmap.sources[{index}]", errors)
    stages, stage_ids = _unique_ids(roadmap.get("stages"), "roadmap.stages", errors)

    skills, skill_ids = _unique_ids(catalog.get("skills"), "skills", errors)
    if not skills:
        errors.append("skills: at least one skill is required")

    diagnostic_ids: set[str] = set()
    prerequisites: dict[str, list[str]] = {}
    stage_memberships: dict[str, int] = {identifier: 0 for identifier in skill_ids}
    for index, skill in enumerate(skills):
        skill_path = f"skills[{index}]"
        skill_id = str(skill.get("id", "")).strip()
        for field in ("title", "description", "priority"):
            _required_string(skill.get(field), f"{skill_path}.{field}", errors)

        stage_id = _required_string(skill.get("stage_id"), f"{skill_path}.stage_id", errors)
        if stage_id and stage_id not in stage_ids:
            errors.append(f"{skill_path}.stage_id: unknown stage {stage_id!r}")

        raw_prerequisites = skill.get("prerequisites")
        if not isinstance(raw_prerequisites, list):
            errors.append(f"{skill_path}.prerequisites: expected a list")
            raw_prerequisites = []
        cleaned_prerequisites: list[str] = []
        for item_index, prerequisite in enumerate(raw_prerequisites):
            item_path = f"{skill_path}.prerequisites[{item_index}]"
            value = _required_string(prerequisite, item_path, errors)
            if value and value not in skill_ids:
                errors.append(f"{item_path}: unknown skill {value!r}")
            if value == skill_id:
                errors.append(f"{item_path}: a skill cannot require itself")
            if value:
                cleaned_prerequisites.append(value)
        prerequisites[skill_id] = cleaned_prerequisites

        note_paths = skill.get("note_paths")
        if not isinstance(note_paths, list) or not note_paths:
            errors.append(f"{skill_path}.note_paths: expected a non-empty list")
        else:
            for item_index, note_path in enumerate(note_paths):
                _validate_note_path(
                    note_path,
                    f"{skill_path}.note_paths[{item_index}]",
                    root,
                    errors,
                )

        outcomes = skill.get("outcomes")
        if not isinstance(outcomes, list) or not outcomes:
            errors.append(f"{skill_path}.outcomes: expected a non-empty list")
        else:
            for item_index, outcome in enumerate(outcomes):
                _required_string(outcome, f"{skill_path}.outcomes[{item_index}]", errors)

        diagnostics, current_ids = _unique_ids(
            skill.get("diagnostics"),
            f"{skill_path}.diagnostics",
            errors,
        )
        if not diagnostics:
            errors.append(f"{skill_path}.diagnostics: at least one question is required")
        for identifier in current_ids:
            if identifier in diagnostic_ids:
                errors.append(f"{skill_path}.diagnostics: duplicate global id {identifier!r}")
            diagnostic_ids.add(identifier)
        for diagnostic_index, diagnostic in enumerate(diagnostics):
            _validate_diagnostic(
                diagnostic,
                f"{skill_path}.diagnostics[{diagnostic_index}]",
                taxonomy,
                errors,
            )

    for index, stage in enumerate(stages):
        stage_path = f"roadmap.stages[{index}]"
        for field in ("title", "description"):
            _required_string(stage.get(field), f"{stage_path}.{field}", errors)
        raw_skill_ids = stage.get("skill_ids")
        if not isinstance(raw_skill_ids, list) or not raw_skill_ids:
            errors.append(f"{stage_path}.skill_ids: expected a non-empty list")
        else:
            for item_index, raw_skill_id in enumerate(raw_skill_ids):
                item_path = f"{stage_path}.skill_ids[{item_index}]"
                skill_id = _required_string(raw_skill_id, item_path, errors)
                if skill_id not in skill_ids:
                    errors.append(f"{item_path}: unknown skill {skill_id!r}")
                else:
                    stage_memberships[skill_id] += 1
        raw_source_ids = stage.get("source_ids")
        if not isinstance(raw_source_ids, list) or not raw_source_ids:
            errors.append(f"{stage_path}.source_ids: expected a non-empty list")
        else:
            for item_index, raw_source_id in enumerate(raw_source_ids):
                item_path = f"{stage_path}.source_ids[{item_index}]"
                source_id = _required_string(raw_source_id, item_path, errors)
                if source_id not in source_ids:
                    errors.append(f"{item_path}: unknown source {source_id!r}")

    for skill_id, count in stage_memberships.items():
        if count != 1:
            errors.append(
                f"skills[{skill_id!r}]: expected exactly one roadmap stage membership, got {count}"
            )
    cycle = _find_cycle(prerequisites)
    if cycle:
        errors.append(f"skills.prerequisites: cycle detected: {' -> '.join(cycle)}")

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise CatalogError(f"Learning catalog is invalid:\n{details}")
    return catalog


def load_catalog(vault_root: str | Path) -> dict[str, Any]:
    root = Path(vault_root).expanduser().resolve()
    path = root / CATALOG_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise CatalogError(
            f"Learning catalog not found: {CATALOG_RELATIVE_PATH.as_posix()}"
        ) from error
    except OSError as error:
        raise CatalogError(f"Could not read learning catalog: {error}") from error

    match = CATALOG_BLOCK.search(text)
    if not match:
        raise CatalogError(
            "Learning catalog must contain one fenced `learning-catalog` JSON block."
        )
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError as error:
        raise CatalogError(
            f"Learning catalog JSON is invalid at line {error.lineno}, "
            f"column {error.colno}: {error.msg}"
        ) from error
    return validate_catalog(payload, vault_root=root)


def skill_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {skill["id"]: skill for skill in catalog["skills"]}


def diagnostic_map(catalog: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        diagnostic["id"]: (skill["id"], diagnostic)
        for skill in catalog["skills"]
        for diagnostic in skill["diagnostics"]
    }


def _summary(catalog: dict[str, Any]) -> str:
    diagnostics = sum(len(skill["diagnostics"]) for skill in catalog["skills"])
    return (
        f"OK: {catalog['catalog_id']} — {len(catalog['skills'])} skills, "
        f"{len(catalog['roadmap']['stages'])} stages, {diagnostics} diagnostics"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an ML Vault learning catalog")
    parser.add_argument("--vault", required=True, help="Path to the Obsidian vault")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        catalog = load_catalog(arguments.vault)
    except CatalogError as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(_summary(catalog))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
