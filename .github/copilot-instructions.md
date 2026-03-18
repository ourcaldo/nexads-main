# Copilot Instructions for nexAds

## Git Commit Scope Rules

- When the user asks to commit and push, include all non-cache changes by default.
- Exclude all Python cache artifacts under `__pycache__/` and `*.pyc` unless the user explicitly asks to include them.
- Stage files explicitly; do not use broad staging that can include secrets or generated files by accident.

## Project-Specific Note

- `config.json` is a user-managed runtime file and should be included in commits when the user asks to push all non-cache changes.
