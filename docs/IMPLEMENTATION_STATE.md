# Learning System v1 — implementation state

Last updated: 2026-08-02

## Repositories and branches

- App worktree: `/Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/ml-vault-agent`
- App branch: `learning-system-v1`
- Vault worktree: `/Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/My_brain_v2`
- Vault branch: `learning-system-v1`
- Starting app commit: `f0cdb7c`
- Starting vault commit: `53d2766`

## Checkpoints

- [x] 0. Create isolated reproducible branches and freeze the contract.
- [x] 1. Add and validate the ten-skill catalog and roadmap in the vault.
- [x] 2. Implement deterministic SQLite evidence memory and review schedule.
- [x] 3. Add learning API and optional skill context to chat.
- [ ] 4. Build the learning dashboard and diagnostic interaction.
- [ ] 5. Complete automated, integration and visual verification.
- [ ] 6. Move verified branches to the laptop's primary folders and publish.

Each checked step must end in a Git commit in the affected repository. Do not
publish an incomplete checkpoint to GitHub.

## Resume procedure

```bash
cd /Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/ml-vault-agent
git status --short --branch
git log --oneline --decorate -8

cd /Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/My_brain_v2
git status --short --branch
git log --oneline --decorate -8
```

Read this file and continue from the first unchecked checkpoint. Before copying
anything into the primary app or vault, rerun all verification commands below.

Checkpoint 1 commits contain the vault catalog/roadmap and the standalone
`app.learning_catalog` validator. The catalog currently reports 10 skills,
4 stages and 10 diagnostics with no missing note paths.

Checkpoint 2–3 add the versioned `learning.sqlite3` schema, transparent mastery,
review scheduling, reversible evidence, rubric parsing, five learning endpoints
and opt-in `skill_id` context for chat. At this checkpoint the full suite reports
42 passing tests.

## Verification commands

```bash
cd /Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/ml-vault-agent
python3 -m pytest
python3 -m app.learning_catalog \
  --vault /Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/My_brain_v2
```

Frontend visual checks and the exact production handoff commands will be added
at checkpoint 5 after their final form is known.
