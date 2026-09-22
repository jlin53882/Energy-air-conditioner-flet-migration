# Packaging Contract

- Flet is launched through `run.py`.
- Telegram is launched through its own bot entrypoint; Flet must not import
  Telegram configuration for logging side effects.
- Dependency metadata is maintained in `pyproject.toml` and `uv.lock`.
- Build scripts must package an explicit target and must never run `uv add` or
  mutate dependency metadata as a build side effect.

Packaging script consolidation remains a follow-up after the executable smoke
coverage is added.
