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

CoolProp reference state is process-global. Mutation and every dependent
`PropsSI`/`PhaseSI` transaction use the shared synchronization boundary in
`domain/thermodynamics/reference_state.py`. Synchronization is separate from
request policy: ordinary property entrypoints explicitly use a concrete policy
(`DEF`, `ASHRAE`, `IIR`, `NBP`, or `IAPWS`), while only internal probes may use
the explicitly named `CURRENT` policy. No ordinary request inherits the state
left by a previous request, and the observed state registry is process-global.

## Run tests

```bash
uv run pytest -q
```

## Scope notes

This branch does not claim to complete every deferred migration. Telegram
specific-volume (`V`) semantics, remaining compressor analyses, full Telegram
constructor dependency injection, complete chart renderer decomposition, and
packaging-target redesign remain explicit follow-up work.
