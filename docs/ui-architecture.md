# HVAC workspace UI architecture

## Purpose and truth boundary

This document is the intended UI architecture contract for the Flet engineering workspace. Executable code is the implementation truth; this document is the intended contract. Any difference between the two is architecture drift that should be identified and corrected, not resolved by silently treating either one as authoritative.

The current migration keeps thermodynamic and HVAC calculation services in their existing application/domain boundaries. A view may collect and validate presentation input, call an existing service through its adapter, and render the returned values. It must not implement thermodynamic equations.

## Application shell

`Flet_ui/flet_app.py` is the composition root. It constructs existing services once and mounts `Flet_ui/ui/app_shell.py`.

`AppShell` owns four regions:

- **Top bar** — application identity and global output unit preference.
- **Sidebar** — grouped route links addressed by stable route keys, never by translated labels.
- **Workspace** — the selected view and its route heading.
- **Context panel** — optional desktop context region. It must not invent calculation history; until a history repository is connected, it displays an explicit empty state and refrigerant shortcuts only.

The shell keeps each unique view mounted in one stable `Stack` and changes visibility when routes change. This prevents expensive child controls (especially chart adapters) from being destroyed/recreated during navigation and avoids control lifecycle churn in Flet. Multiple route keys may deliberately map to the same legacy analysis adapter; the adapter changes its selected category without being reparented.

## Navigation contract

`Flet_ui/ui/navigation.py` defines semantic route identifiers and their display labels. Currently registered routes are home, thermodynamic state query, compressor, evaporator, condenser, psychrometrics, P-h chart, and T-s chart. Each analysis route maps to the existing analysis registry category. New routes must represent an implemented tool or be visibly marked unavailable; roadmap entries must not look executable.

Route identity is data (`route.key`), independent of presentation text. Navigation state belongs to `WorkspaceState`, not to labels or Flet selection indices.

## Design tokens and shared components

`Flet_ui/ui/theme.py` centralizes spacing, radii, control sizes, width guidance, colors, and typography. New workspace views should use these tokens rather than defining local palettes and spacing values.

`Flet_ui/ui/components/` currently provides:

- `EngineeringCard` — shared surface and titled grouping.
- `QuantityInput` — semantic value/unit grouping that can adopt existing controls while migrating a legacy form.
- `ResultPanel` — explicit empty, loading, success, warning, and error states; metric cards only render values actually supplied by a calculator adapter.
- `Sidebar` — sectioned, tooltip-bearing route controls.

A control wrapper owns presentation and field-local validation. Conversion remains the responsibility of the existing `UnitConverter` or a domain/application adapter, not a duplicated per-view formula.

The shared analysis input-row builder renders the value label and unit label as separate text controls above their respective `TextField` and `Dropdown`. Do not put these labels inside the outlined controls: keeping labels outside the border prevents text and outline collisions across compressor, evaporator, condenser, and other analysis forms. Generic analysis labels describe the quantity and stay unchanged when units change; thermo-diagram labels intentionally include the unit and update with it. In all cases, the dropdown's selected value is the source of truth for the unit.

## View responsibilities and migration boundaries

- The property workspace composes existing mode, fluid, reference-state, and property controls into configuration, known-condition, optional extensive-property, result, and action regions.
- The generic state-query solver accepts two independent properties. Until third-condition constraints are implemented by the solver, hide the third input row and its add action; render each supported property selector and value/unit control on aligned responsive columns.
- HVAC analysis calculations remain registered in the existing `analysis_modules` and are dispatched by `AnalysisTab`; the shell selects a route category and exposes only that category's real registered operations. The selected mode must be visually distinct, and psychrometric mode must also be stated in text.
- Psychrometric calculation and chart generation stay in their existing adapters/modules.
- Future `ThermoPropertiesView`, compressor/evaporator/condenser views, chart adapters, and state-point adapters may be extracted from legacy containers incrementally. Do not duplicate calculation behavior while doing so.

The active code still uses legacy `PropertyTab` and a shared `AnalysisTab` adapter for several routes. That is a migration boundary, not a target for putting new domain calculations into the views.

## State ownership

`WorkspaceState` holds the active semantic route, global output-unit preference, and a lightweight per-input-unit map. It must never serialize Flet controls.

The current legacy property and analysis adapters still read/write some state through Flet controls. During further migration, move durable query inputs and result metadata into typed application state models, then bind controls to that state. Keep these concerns separate:

- presentation state: selected/visible controls and local validation;
- navigation state: stable route key;
- unit state: each input's selected unit and the global output preference;
- thermodynamic state: canonical calculator result;
- analysis state: inputs/results owned by an individual analysis.

Changing the global output preference re-renders result values but does not overwrite each input's chosen unit.

## Responsive behavior

The shell has three width modes:

- wide (about 1200 px and above): full sidebar, workspace, context panel;
- medium (about 800–1200 px): compact icon rail and hidden context panel;
- narrow (below about 800 px): full-width workspace with a toggleable overlay navigation drawer and no context panel.

Scroll ownership should be clear: the workspace does not scroll the whole shell; each calculation view owns its scrolling region. The property query keeps its bottom action bar outside its scrollable inputs/results so Reset/Calculate remain available while scrolling.

## Validation and result contracts

Validation belongs beside its field where possible; a global snackbar is supplementary, not the only signal. Calculation state uses explicit empty/loading/success/warning/error labels, icons, and text—not color alone. Developer exception details stay out of user-facing result text; domain validation errors may be shown when they are safe and actionable.

Results are structured metrics plus metadata (fluid, engine, reference convention, input units, output system). Raw text is a secondary, opt-in detail view. Never synthesize values that the calculation did not return.

## Testing and maintenance

Use behavioral tests for unit refresh, value reset/conversion, presets, route selection, result states, and unit-system rendering. Structural tests may verify the shell and reusable control contracts but do not replace runtime/interaction checks. New or changed functions need PEP 257 docstrings; changes to this contract or cross-file behavior update this document in the same change.

## Current extension points and roadmap

The route registry supports additional thermodynamic, refrigeration, air-treatment, charts, tools, data, and settings sections. A future history implementation should depend on a `HistoryRepository` interface and store application data, not controls; persistent JSON/SQLite decisions are deferred. State-point/cycle workspace and superheat/subcooling/saturation tools are separate feature work unless the existing domain service already implements them.
