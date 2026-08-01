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
- [x] 4. Build the learning dashboard and diagnostic interaction.
- [x] 5. Complete automated, integration and visual verification.
- [x] 6. Move verified branches to the laptop's primary folders and publish.

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

Checkpoint 4 adds the responsive Learning dashboard, roadmap/source provenance,
skill detail, visible rubrics, self-report, evidence dismissal/restoration and
the explicit handoff to Tutor. Desktop and a 390×844 viewport were checked in a
real browser; the console had no errors. The suite now reports 45 passing tests,
and lexical smoke cases return a source for all five existing modes.

## Verification commands

```bash
cd /Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/ml-vault-agent
PYTHONPATH=. /Users/kheichiev/projects/ml-vault-agent/.venv/bin/python -m pytest
PYTHONPATH=. /Users/kheichiev/projects/ml-vault-agent/.venv/bin/python \
  -m app.learning_catalog \
  --vault /Users/kheichiev/Documents/Codex/2026-07-31/cvj/outputs/My_brain_v2
```

## Final verification and handoff

Completed on 2026-08-02:

- 47 automated tests passed from the primary app folder;
- catalog validation reported 10 skills, 4 stages and 10 diagnostics;
- JavaScript syntax validation passed;
- all five lexical smoke cases returned a relevant source;
- desktop Learning, skill detail, self-report, evidence dismissal and Tutor
  handoff were tested in a real browser;
- the 390×844 mobile layout collapsed to one column with a static skill panel;
- browser console contained no errors;
- GitHub Actions passed on `macos-latest` and `windows-latest`, including the
  Windows PowerShell launcher parse and setup smoke test;
- both remote repositories contained only `main`, so no remote branch deletion
  was necessary.

Primary folders now use the verified commits through a fast-forward merge:

```bash
cd /Users/kheichiev/projects/ml-vault-agent
git status --short --branch

cd /Users/kheichiev/Desktop/My_brain_v2
git status --short --branch
```

Both should report `main...origin/main` with no changed files after the final
status commit is pushed. The isolated `learning-system-v1` local branches are
kept as recovery pointers; they are not GitHub branches and can be deleted later
without affecting `main`.
