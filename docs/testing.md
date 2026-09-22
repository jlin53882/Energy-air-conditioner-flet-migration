# Testing Strategy

## 1. Test Layers

The repository currently keeps many tests under `tests/characterization/`; the
following are logical layers rather than claims that every directory already
exists:

- domain and equation tests;
- adapter and compatibility tests;
- application/service tests;
- integration and Flet construction tests;
- architecture guardrail tests;
- compile, dependency, and packaging checks.

Tests should be placed in the nearest existing layer without inventing a new
layout solely for naming consistency.

## 2. Characterization Tests

Characterization tests record behavior at a boundary before or during
consolidation. They are useful when Flet and Telegram behavior differs, but a
characterization is not automatically the desired long-term contract. When a
contract is intentionally changed, update the characterization or add a
contract test that makes the new decision explicit.

## 3. Domain Tests

Domain tests cover canonical units, thermodynamic state calculations, HVAC
equations, psychrometric result shapes, reference-state policy, and explicit
error behavior. They should use numeric canonical values and should not require
Flet controls, Telegram transports, or display formatting.

## 4. Adapter Tests

Adapter tests verify parsing, compatibility conversion, display conversion,
error presentation, and channel-specific output. They must prove that unknown
canonical units fail explicitly and that legacy compatibility behavior does not
silently become the domain contract.

## 5. Integration Tests

Integration and smoke tests construct real production entrypoints or UI
components with minimal faithful stubs for non-target runtime dependencies.
They cover Flet tab construction, representative analysis selections,
psychrometric Flet/Telegram paths, and the application service boundary.

## 6. Architecture Guardrails

Guardrails verify dependency direction and ownership invariants:

- domain does not import Flet or Telegram packages;
- application does not import channel rendering/runtime objects;
- only `ReferenceStateService` directly mutates CoolProp reference state;
- reference-state transactions use the shared synchronization mechanism;
- analysis definitions provide unique semantic IDs;
- service boundaries are used by UI lifecycle code.

Guardrails should inspect the relevant production tree and fail on a new
boundary violation rather than checking only one changed file.

## 7. Runtime Smoke Tests

Runtime smoke coverage should exercise the real Flet composition path, property
query path, analysis registration, psychrometric adapters, and chart state
pipeline. A static import check is not a substitute for constructing the
production entrypoint.

## 8. Regression Workflow

For a behavior bug, follow:

```text
reproduce → RED regression → minimal fix → GREEN regression → full suite
```

For process-global dependencies, tests must cover sequential isolation,
concurrency/interleaving, cross-request isolation, and explicit policy
ownership. A lock test alone is insufficient if a request can still inherit an
ambient process state.

For architecture changes, characterize the current behavior, establish the
contract, make the smallest boundary change, verify callers, and remove the
replaced path only when no longer referenced.

## Verification Commands

Run the complete local verification set from the repository root:

```bash
uv run pytest -q
uv lock --check
uv pip check
uv run python -m compileall -q Flet_ui Telegram_bot application domain chart infrastructure run.py telegeram_chatid.py
git diff --check
```

Use focused tests while iterating, then rerun the full suite after the final
edit. Report exact tool output; pending external CI is not equivalent to a
local pass.
