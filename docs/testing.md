# Verification Contract

Every architecture-refactor commit must run:

```bash
uv run pytest -q
uv run python -m compileall -q application chart domain Flet_ui Telegram_bot run.py telegeram_chatid.py tests
uv lock --check
uv pip check
git diff --check
```

Focused characterization tests live under `tests/characterization/`. They record
legacy behavior before consolidation and protect each migrated boundary.

Physics behavior changes require a separate regression test and a divergence
decision record; architecture movement alone must not rewrite formulas.
