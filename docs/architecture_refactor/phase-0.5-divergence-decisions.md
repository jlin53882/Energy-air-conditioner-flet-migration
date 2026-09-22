# Phase 0.5 — Flet / Telegram Divergence Decision Record

> 專案：`Energy_air-conditioner_flet-migration`
> 基準：Phase 0 characterization tests，commit `4eb49ba`
> 範圍：只分類目前已由原始碼與測試驗證的差異；不在本文件中偷偷修改 domain 行為。
> 排除：`Flet_ui/PsychrometricChart/PsychrometricChart_01_ASHF_model.py` 的內部實作。

## Decision rules

- Presentation difference：保留在 channel adapter，不進 domain contract。
- Adapter difference：Flet／Telegram 可各自輸出，但共用 neutral result。
- Contract difference：在 shared domain 建立前必須明確決定 canonical semantics。
- Domain logic difference：需要 physics／engineering evidence；沒有證據時不得由 agent 任意選一邊。
- Confirmed bug：獨立 bug-fix scope，不能悄悄混入 architecture migration。
- Unknown：阻擋該 contract consolidation，但不阻擋不相關 Phase。

## Records

### D001 — Pressure / temperature / enthalpy conversion

- **Area:** units
- **Evidence:** `tests/characterization/test_phase0_current_behavior.py::test_current_unit_contracts_are_recorded_for_shared_quantities`
- **Flet:** `UnitConverter.convert_to_si()`
- **Telegram:** `ThermoCalculator._convert_to_si()`
- **Observed result:** representative `P`, `T`, `H` cases match numerically.
- **Classification:** No observed numerical divergence for tested cases.
- **Decision:** These quantities may proceed to Phase 1 canonical registry, subject to broader unit inventory and boundary tests.
- **Status:** `decided-for-phase-1`

### D002 — Specific volume `V`

- **Area:** units / thermodynamics
- **Evidence:** `test_specific_volume_contract_differs_between_current_engines`
- **Flet:** `V` remains specific volume in `m³/kg`.
- **Telegram:** `_convert_to_si("V", ...)` currently returns density semantics for the same property code; `calculate_properties()` then treats it as density input.
- **Classification:** Contract divergence, not presentation difference.
- **Decision:** The target contract is explicit specific-volume semantics (`V = m³/kg`) at the domain boundary, while CoolProp calls may normalize to density internally. This follows the Flet `ThermoStateCalculator` contract and the physical property name; the Telegram behavior must be migrated through an explicit compatibility adapter rather than silently copied.
- **Migration rule:** Preserve current Telegram behavior in characterization fixtures until its callers are migrated; do not delete or rewrite it in Phase 0.5.
- **Status:** `canonical-target-recorded; migration-pending`

### D003 — Ideal-gas property result

- **Area:** thermodynamics
- **Evidence:** `test_current_ideal_gas_results_match_between_engines`
- **Observed result:** representative `Air` `P/T` case returns matching `P`, `T`, `D`, `H`, `U`, `V`, and `phase`.
- **Classification:** No observed numerical divergence for tested case.
- **Decision:** Can be used as an initial shared-service parity fixture in Phase 2; expand to `P/D`, `T/D`, invalid fluid and boundary cases before removal of either implementation.
- **Status:** `decided-for-characterization; broader-coverage-pending`

### D004 — Basic HVAC formulas

- **Area:** HVAC
- **Evidence:** `test_current_hvac_formula_contracts_match_for_shared_cases`
- **Observed result:** compressor work, evaporator heat rate, condenser heat rate and compression ratio match for representative inputs.
- **Classification:** No observed numerical divergence for tested cases.
- **Decision:** Existing Flet `hvac_calculations` functions are the initial migration seam because they are already separated as pure calculation modules; Telegram methods must be replaced only after broader characterization and unit-contract tests.
- **Restriction:** This is not approval to rewrite physics formulas. Any formula discrepancy found later requires a separate engineering decision or bug fix.
- **Status:** `decided-for-phase-3-seam; broader-coverage-pending`

### D005 — Psychrometric result shape and display units

- **Area:** psychrometrics / adapter
- **Evidence:** `test_current_psychrometric_adapters_expose_different_output_contracts`
- **Flet:** `PsychrometricCalculator` returns a numeric SI-oriented dictionary (`K`, `Pa`, `J/kg`, etc.).
- **Telegram:** `ThermoCalculator.calculate_psychrometric_properties()` returns display-ready strings in Celsius／kJ/kg／text labels.
- **Classification:** Adapter/output-contract divergence.
- **Decision:** Shared domain service will return a typed neutral SI result; Flet and Telegram retain channel-specific rendering. The excluded model remains unchanged and is hidden behind one adapter.
- **Status:** `decided-for-phase-4-target`

### D006 — Reference-state mutation

- **Area:** thermodynamics / global state
- **Evidence:** `test_reference_state_sequence_returns_to_original_values` and direct sequence probe.
- **Observed result:** changing `R134a` from `ASHRAE` to `IIR` changes enthalpy/entropy; explicitly setting `ASHRAE` again restores the original values for the tested sequence.
- **Classification:** Shared process-global mechanism with policy risk; not yet a formula divergence.
- **Decision:** All mutation and dependent `PropsSI`／`PhaseSI` queries run through one process-wide `ReferenceStateService` synchronization primitive. Synchronization is separate from request policy: every reference-state-sensitive production entrypoint supplies an explicit policy (`DEF`, `ASHRAE`, `IIR`, `NBP`, `IAPWS`, or the explicitly named internal `CURRENT` operation). Ordinary property calculations default to their channel policy and never use `None` to inherit ambient process state. The observed reference-state registry is process-global and protected by the same lock.
- **Status:** `decided-for-reference-state-closure`

### D007 — Formatting and error presentation

- **Area:** adapters
- **Observed result:** Flet uses controls／SnackBar／formatted result components; Telegram uses message strings and Telegram-specific response flow.
- **Classification:** Adapter difference.
- **Decision:** Preserve channel-specific presentation. Shared services return structured result/error objects, not display-ready strings.
- **Status:** `decided-for-application-layer`

### D008 — Telegram calculator construction

- **Area:** dependency ownership
- **Observed result:** Telegram handlers construct module-global calculators at import time; Flet composes several services in `flet_app.py`.
- **Classification:** Composition/lifecycle divergence, not domain behavior.
- **Decision:** Shared services are created by explicit composition roots in Phase 5. Phase 3 may temporarily retain legacy wiring through compatibility facades.
- **Status:** `decided-for-phase-5`

## Blocked decisions that require evidence before consolidation

The following must not be silently decided during implementation:

1. Any formula mismatch not covered by the current parity fixtures.
2. Any difference in pressure／enthalpy／entropy interpretation outside the representative cases.
3. Reference-state concurrency and cache behavior.
4. Psychrometric boundary values, invalid inputs and model error semantics.
5. Existing Telegram behavior that users depend on but is not represented in tests.

## Phase 0.5 exit criteria

- [x] Representative Flet／Telegram differences are recorded.
- [x] Presentation and adapter differences are separated from domain contract differences.
- [x] `V` contract divergence is explicitly recorded rather than hidden.
- [x] Formula consolidation seam is documented without claiming physics correctness beyond tested cases.
- [x] Reference-state policy is explicitly marked pending rather than assumed safe.
- [x] Excluded model remains unmodified.
- [ ] All production callers have parity coverage — deferred to Phase 0.5 expansion / Phase 1–4 focused work.
