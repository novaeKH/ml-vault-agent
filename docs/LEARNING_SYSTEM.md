# Learning System v1

This document is the implementation contract for the first learning-oriented
version of ML Vault Agent. It deliberately keeps the Obsidian vault read-only
and stores personal learning data in the application's local data directory.

## Product boundary

- The agent remains a theory-first ML assistant.
- The learning system starts with ten core ML skills. SQL remains outside this
  milestone and can be added later through the same catalog contract.
- The roadmap is optional. It is a curated mapping of named expert-created
  curricula, not an AI-generated claim about the only correct order.
- Memory contains inspectable evidence about skills, attempts and recurring
  errors. It does not retain arbitrary chat transcripts.
- A single mistake is evidence, not a permanent label. Users can dismiss any
  evidence item.

## Source of truth

The configured vault contains `_meta/LEARNING_CATALOG.md`. A fenced JSON block
named `learning-catalog` defines:

- catalog schema and review date;
- external roadmap sources and their URLs;
- stages and prerequisite order;
- skills, outcomes, linked notes and diagnostic questions;
- explicit rubrics and allowed error codes.

The app parses and validates that file without modifying it. A vault without a
valid catalog continues to work as before; the learning screen explains what is
missing instead of breaking chat.

## Skill model

Each skill is evaluated on four independent axes:

1. `recall` — recalls terms and definitions;
2. `explain` — explains mechanism and causal links;
3. `apply` — chooses and applies the idea in a task;
4. `diagnose` — detects broken assumptions and mistakes.

The UI exposes the axes and the evidence used for them. Deterministic tests have
the highest weight, rubric-based model review has medium weight, model inference
from ordinary dialogue has low weight, and self-report has the lowest weight.
Version 1 records rubric review and self-report; it never silently turns normal
chat into a high-confidence assessment.

## Local memory

`data/learning.sqlite3` contains append-only evidence plus review scheduling.
The vault itself remains read-only and may safely be synchronized through Git.

Evidence fields:

- skill and axis;
- activity/question identifier;
- evidence kind and confidence;
- numeric score and result;
- optional error code and concise note;
- creation and dismissal timestamps.

Displayed mastery is a deterministic weighted summary of active evidence. It is
not a hidden model score. Review intervals follow a small documented ladder:
`1 -> 3 -> 7 -> 14 -> 30` days after successful attempts; partial or failed
attempts shorten the interval.

The exact v1 calculation uses at most the eight newest events per axis. Event
weight is `source_weight * confidence * 0.88^position`, where source weights are
`1.0` deterministic, `0.75` rubric review, `0.35` agent observation and `0.25`
self-report. Level thresholds are `<0.45 needs_work`, `<0.70 developing`,
`<0.85 reliable`; `strong` additionally needs at least two events. An error code
appears as recurring only after two active observations, and two later successful
attempts resolve it. Dismissing/restoring evidence also rebuilds review state.

## Learning loop

1. Select a skill from the optional roadmap or the weak/due list.
2. Read the linked vault note or ask the tutor for an explanation.
3. Answer one catalog diagnostic question.
4. Receive rubric-based feedback labelled as model-reviewed evidence.
5. Inspect or dismiss the saved evidence.
6. Revisit the skill when it becomes due.

## API contract

- `GET /api/learning/overview` — catalog state, stages, mastery and due items.
- `GET /api/learning/skills/{skill_id}` — skill, question and evidence details.
- `POST /api/learning/diagnose` — rubric review and evidence creation.
- `POST /api/learning/evidence` — explicit self-report/manual evidence.
- `POST /api/learning/evidence/{event_id}/dismiss` — reversible dismissal.
- `POST /api/chat` accepts an optional `skill_id` and adds only the relevant,
  transparent learning context to the system prompt.

## Definition of done

- malformed catalogs fail validation with actionable messages;
- the ten core skills and their linked notes exist in the vault;
- memory calculations, scheduling and dismissals are covered by tests;
- learning endpoints do not affect existing chat when no catalog is present;
- the dashboard works on desktop and a narrow mobile viewport;
- backend, frontend and vault validation commands are recorded in
  `docs/IMPLEMENTATION_STATE.md`.
