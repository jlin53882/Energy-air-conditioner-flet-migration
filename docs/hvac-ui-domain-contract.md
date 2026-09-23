# HVAC UI domain contracts

## Purpose and truth boundary

This document records the intended domain-to-UI boundary for thermodynamic and HVAC inputs. Executable code is the implementation truth; this document is the intended contract. Any mismatch is architecture drift that must be investigated and repaired.

The Flet presentation layer is not an alternate thermodynamic calculation engine. It adapts user-facing quantities to existing application/domain services and renders values those services actually return.

## Canonical and display units

The thermodynamic domain uses canonical SI values: pressure in Pa, temperature in K, enthalpy in J/kg, entropy in J/(kg·K), density in kg/m³, specific volume in m³/kg, and mass in kg. `UnitConverter` owns conversion between user-selected units and those canonical quantities.

Input and output preferences are independent. A global SI/Imperial preference selects result display units; it must not silently replace a field's selected input unit. When a user changes a quantity's unit, convert its numeric value through canonical SI. When a user changes the property type (for example P to T), clear the old numeric value because it is not semantically convertible; refresh the unit options/default and label immediately.

## Pressure basis

Pressure is ambiguous unless its basis is explicit. A pressure input must identify `Gauge` or `Absolute` whenever the operation accepts gauge pressure. Thermodynamic property queries and CoolProp state solving require absolute pressure. A gauge-to-absolute adapter must use the configured atmospheric pressure and the selected pressure unit consistently; it must not reinterpret a gauge reading as absolute. Existing HVAC analyzer/module calculations remain the executable contract until a dedicated shared `PressureInput` is migrated across them.

## Relative humidity and quality

Relative humidity (`RH`) and vapor quality (`Q`) are different properties with different UI contracts:

- RH displays a percentage from 0 through 100. The canonical psychrometric boundary normalizes percent to a fraction: `88 %` maps to `0.88`, and a normalized `0.88` is rendered as `88 %`.
- Quality is dimensionless in the range 0 through 1. `Q = 0.88` displays as `0.88`, never as `88 %` and never as `0.88 %`.

The two properties must not share a percent formatter. RH validation rejects values outside 0–100%; quality validation rejects values outside 0–1.

## Property query and reference state

A property query supplies a fluid, calculation mode, reference-state policy, and the independent input property/value/unit pairs. The UI currently accepts exactly two independent properties for the existing state solver. A visible optional third row is not silently ignored: until additional-constraint validation exists, entering a third value must produce an explicit warning/error and stop the calculation.

Reference-state choices (`ASHRAE`, `IIR`, `NBP`, `Default`) are passed through the existing `resolve_reference_state_policy`/query service. Results identify the fluid, engine, reference convention, actual input units, and output unit system.

## Result values and metadata

Metrics are generated only from keys present in the calculator result. Quality stays unitless. Extensive outputs require a mass value converted to canonical kg; the mass input is hidden until extensive-property calculation is explicitly enabled. Invalid or absent properties are omitted, not replaced with sample numbers.

A result record should carry enough context to reproduce or interpret it: selected fluid, query inputs with their units, engine/model, reference state, output preference, and result values. Flet controls are never serialized as domain state.

## State-point and cycle extension

A future `ThermoStatePoint` adapter may identify a fluid/reference state and carry canonical pressure, temperature, enthalpy, entropy, density, specific volume, quality/phase, original inputs, source, and timestamp. Existing calculators should not be rewritten to depend on that model until adapter contracts and regression coverage are established.

Cycle calculations (states 1–4, heat/work/COP/flow) belong in application/domain services, not in UI callbacks. P-h/T-s views consume calculator/chart adapter data and may later reference state-point IDs; they must not duplicate thermodynamic equations.

## Current implementation boundary

The psychrometric fraction/percent conversion and unit conversion already exist. The property-query adapter now validates finite values, absolute pressure/temperature, quality and RH limits before dispatch, and shows field-local messages; however, a unified reusable pressure-basis control and equivalent validation coverage across every analysis module remain future migration work. Any change to these behaviors requires corresponding boundary/regression tests and an update to this contract.
