# Energy Air Conditioner — Tkinter-free Flet migration

This repository is the Flet migration of the Energy Air Conditioner application.
It removes the Tkinter desktop entry point while preserving the existing
thermodynamic, HVAC, psychrometric, and chart behavior.

## Architecture

The migration uses the following dependency direction:

```text
Flet / Telegram adapters -> application -> domain
                                  ^
                         infrastructure adapters
```

- `domain/` contains canonical units, thermodynamics, HVAC equations, and
  psychrometric contracts.
- `application/` coordinates neutral property and analysis requests.
- `Flet_ui/` and `Telegram_bot/` remain channel adapters.
- `infrastructure/` contains concrete adapters for legacy integrations,
  including the excluded legacy psychrometric model.
- `chart/` contains headless chart state parsing; existing rendering and
  sampling behavior remains unchanged in this migration.

CoolProp reference-state mutation is process-global. All mutation and
reference-state-dependent `PropsSI`/`PhaseSI` transactions use the shared
synchronization boundary in `domain/thermodynamics/reference_state.py`.

## Run tests

```bash
uv run pytest -q
```

## Scope notes

This branch does not claim to complete every deferred migration. Telegram
specific-volume (`V`) semantics, remaining compressor analyses, full Telegram
constructor dependency injection, complete chart renderer decomposition, and
packaging-target redesign remain explicit follow-up work.
