# Current Architecture

## Executable boundaries

- `run.py` is the Flet launcher and owns only Flet startup plus neutral logging.
- `Telegram_bot/` remains an independent bot executable boundary.
- Shared domain code lives in `domain/`; application orchestration lives in `application/`.
- Channel-specific UI and handlers remain adapters.

## Migration status

Completed slices are recorded by commit and verified by the focused/full test suite:

- canonical core unit conversion
- shared thermodynamic state service and reference-state mechanism
- shared SI HVAC equations
- single psychrometric boundary around the excluded model
- property query application service
- first thin PropertyTab boundary
- first compressor analysis migration
- explicit analysis dispatch metadata
- headless chart state-point parser
- neutral Flet logging ownership

The remaining legacy compatibility surfaces are intentional and tracked in
`docs/architecture_refactor/phase-0.5-divergence-decisions.md`, especially the
Telegram specific-volume contract and the un-migrated compressor analyses.
