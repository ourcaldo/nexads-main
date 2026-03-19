# Copilot Instructions for nexAds

## Git Commit Scope Rules

- Always commit and push after every change, including very small changes.
- For each commit/push, include all non-cache changes in the working tree by default.
- Exclude all Python cache artifacts under `__pycache__/` and `*.pyc` unless the user explicitly asks to include them.
- Stage files explicitly; do not use broad staging that can include secrets or generated files by accident.

## Change Log Rules

- For every implementation/change, update `docs/plans/log-changes.md` before commit/push.
- Each log entry must include exactly these fields:
	- `Date time`
	- `Short description`
	- `What you do`
	- `File path that changes`
- Log entries should be appended in reverse-chronological order (newest first).

## Project-Specific Note

- `config.json` is a user-managed runtime file and should be included in commits when the user asks to push all non-cache changes.
