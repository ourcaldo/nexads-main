---
description: MANDATORY rules for every git commit and push. These rules MUST be followed for EVERY code change without exception.
globs: **/*
---

# Git Commit & Push Rules (MANDATORY)

## 1. One commit per change
- NEVER bundle multiple unrelated fixes into one commit.
- Each logical change gets its own commit and push.
- Example: fixing a bug in worker.py and fixing a bug in telemetry.py = 2 separate commits.

## 2. Update log BEFORE committing
- EVERY commit MUST have a corresponding entry in `docs/log/log-changes.md` BEFORE the commit is created.
- Add the log entry first, then stage both the changed files AND the log file, then commit.
- Log entry format (ALL fields required):
  - `Date time` (ISO 8601)
  - `Short description`
  - `What you do`
  - `File path that changes`

## 3. Commit and push after every change
- Do NOT accumulate changes. Commit and push immediately after each change is complete.
- The workflow for every change is:
  1. Make the code change
  2. Add log entry to `docs/log/log-changes.md`
  3. `git add` the changed files + log file (explicit filenames, not `git add .`)
  4. `git commit` with clear message
  5. `git push origin main`
  6. Then move to the next change

## 4. Never include cache or generated files
- Exclude `__pycache__/`, `*.pyc`, `data/*.jsonl` unless explicitly asked.
- Stage files by explicit name, not broad patterns.

## 5. Do NOT skip these rules
- These rules apply to ALL commits — bug fixes, features, docs, config, scripts, everything.
- There are ZERO exceptions. If you are about to commit, check this file first.
