# Current Architecture

## Executable boundaries

- `run.py` is the Flet launcher and owns only Flet startup plus neutral logging.
- `Telegram_bot/` remains an independent bot executable boundary.
- Shared domain code lives in `domain/`; application orchestration lives in `application/`.
- Channel-specific UI and handlers remain adapters.

## Current synchronization and adapter contracts

- CoolProp reference state is process-global. `ReferenceStateService` exposes one
  process-wide `RLock`; mutation plus dependent `PropsSI`/`PhaseSI` queries must
  run inside its `calculation_scope`. This synchronization mechanism is separate
  from request policy: ordinary property entrypoints pass an explicit `DEF`,
  `ASHRAE`, `IIR`, `NBP`, or `IAPWS` policy; only internal probes may use the
  explicitly named `CURRENT` policy. The observed state registry is shared too.
- The excluded legacy psychrometric model is imported only by
  `infrastructure.psychrometrics.LegacyPsychrometricModelAdapter`. Domain code
  consumes its neutral protocol and does not import Flet or Telegram modules.
- Analysis definitions own stable semantic `analysis_id` values. `AnalysisTab`
  validates and registers them but does not derive IDs from class names or order.
- `PropertyTab` receives `PropertyQueryService`; fluid validation, reference-state
  setup, and property queries cross the application boundary through that service.


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
