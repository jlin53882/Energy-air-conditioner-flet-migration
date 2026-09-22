# Architecture

## 1. System Overview

The application has two channel interfaces, a neutral application layer, shared
domain services, and infrastructure adapters for legacy integrations.

```text
Flet adapter -----------┐
                         ├──> application/ ───> domain/
Telegram adapter -------┘

Composition roots construct channel/application/domain services and inject
infrastructure implementations; infrastructure is not discovered by
application or domain code.
chart/ provides headless chart state models and parsing for chart adapters.
```

## 2. Dependency Direction

The legal direction is:

```text
channel adapters / entrypoints
              ↓
       application services
              ↓
        domain services
```

Infrastructure adapters are concrete implementations injected at composition
roots. `domain/` and `application/` must not import channel packages or channel
rendering types.

## 3. Layer Responsibilities

### `domain/`

Owns canonical quantities, unit definitions, thermodynamic calculations, HVAC
equations, psychrometric neutral result models, and process-global
reference-state policy. It does not know Flet controls, Telegram updates, or
display formatting.

### `application/`

Owns request models and orchestration such as `PropertyQueryService`. It
validates request shape and coordinates domain services. It does not render
controls or messages.

### `infrastructure/`

Owns concrete integrations that are not domain contracts. The excluded legacy
psychrometric implementation is accessed through
`LegacyPsychrometricModelAdapter` here.

### `Flet_ui/`

Owns controls, parsing of Flet input, adapter formatting, and UI lifecycle.
`PropertyTab` crosses the property-query application boundary rather than
implementing thermodynamic policy itself.

### `Telegram_bot/`

Owns Telegram handlers, response formatting, and compatibility facades for
legacy Telegram behavior. It uses explicit reference-state policy when calling
shared thermodynamic services.

### `chart/`

Owns headless chart state models and parsing. Existing chart rendering and
sampling remain channel/infrastructure concerns.

### Entrypoints

`run.py` composes and launches the Flet application with neutral logging.
Telegram has its own bot entrypoint and configuration boundary. No separate
`bootstrap/` package is currently part of the repository.

## 4. Composition Roots

Composition roots create channel adapters and inject shared services. A
composition root may select a channel policy, adapter implementation, or
formatter, but domain code must not discover those implementations by importing
upward.

## 5. Thermodynamic Boundary

`ThermodynamicStateService` accepts known properties in display units at the
adapter boundary, converts them to canonical SI, performs the CoolProp or
ideal-gas calculation, and returns neutral numeric results. Compatibility
facades may preserve channel-specific behavior, but they must delegate canonical
quantities to the shared service where the contract is consolidated.

## 6. HVAC Boundary

Shared HVAC equations live under `domain/hvac/` and use canonical SI inputs and
outputs. Flet and Telegram modules adapt channel values and presentation around
that boundary; they must not introduce a second implementation of the shared
formula.

## 7. Psychrometric Boundary

`domain.psychrometrics.service.PsychrometricService` consumes an injected
neutral protocol and returns numeric results. The excluded legacy model
`Flet_ui/PsychrometricChart/PsychrometricChart_01_ASHF_model.py` is imported only
by the infrastructure adapter. Its internal implementation is outside the
ordinary domain refactor boundary and is not a domain dependency.

## 8. Chart Boundary

`chart/` provides headless state-point models and parsing. Chart adapters may
render using Flet or Matplotlib, but chart rendering details must not leak into
domain calculations. Reference-state-sensitive chart queries use the shared
CoolProp synchronization mechanism.

## 9. Reference-State Ownership

CoolProp reference state is process-global. `ReferenceStateService` owns:

- the process-wide synchronization primitive;
- controlled reference-state mutation;
- the shared observed-state registry;
- the `ReferenceStatePolicy` vocabulary.

Mutation and the complete dependent `PropsSI`/`PhaseSI` transaction run inside
one shared `calculation_scope`. Synchronization is distinct from request
policy: ordinary entrypoints choose a concrete policy (`DEF`, `ASHRAE`, `IIR`,
`NBP`), while only explicitly internal operations may use `CURRENT`.
No ordinary request inherits the state left by a previous request.

## 10. Analysis Registration

Each analysis definition owns a stable semantic `analysis_id`. `AnalysisTab`
validates and registers definitions, rejects missing or duplicate IDs, and uses
those IDs for control flow. Display labels, localized names, list position, and
class-name-plus-position are not identities.

## 11. Architecture Invariants

- `domain/` does not import `Flet_ui`, `Telegram_bot`, `flet`, or `telegram`.
- `application/` does not depend on Flet controls, Telegram update/context
  objects, or channel rendering.
- UI and handlers do not own canonical unit rules, HVAC equations, thermodynamic
  formulas, or reference-state mutation.
- Direct `CP.set_reference_state(...)` exists only in
  `domain/thermodynamics/reference_state.py`.
- Reference-state-sensitive CoolProp queries use the shared synchronization
  boundary.
- The excluded psychrometric model is reached only through infrastructure.
- Analysis control flow uses semantic `analysis_id` values.
- Compatibility behavior is isolated, documented, and tested at an adapter
  boundary.

## 12. Guardrails

Architecture guardrail tests scan production imports and direct CoolProp
mutation. Regression tests cover stable analysis registration, explicit unit
errors, reference-state transaction isolation, cross-instance state ownership,
and the application/UI service boundary.

The domain contracts are specified in
[`domain-contracts.md`](domain-contracts.md). Accepted temporary behavior
boundaries are specified in
[`compatibility-boundaries.md`](compatibility-boundaries.md). Maintenance and
verification rules are specified in
[`maintenance.md`](maintenance.md) and [`testing.md`](testing.md).
