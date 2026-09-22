# Domain Contracts

This document describes the current domain semantics. Display units and channel
formatting belong to adapters unless explicitly stated otherwise.

## 1. Canonical Quantities

The shared domain uses these canonical quantities:

- pressure `P`: `Pa`
- temperature `T`: `K`
- enthalpy `H`: `J/kg`
- entropy `S`: `J/(kg·K)`
- density `D`: `kg/m³`
- specific volume `V`: `m³/kg`
- internal energy `U`: `J/kg`
- mass: `kg`
- mass flow: `kg/s`
- power: `W`
- energy: `J`

Quality `Q` is dimensionless. `kPa`, `bar`, `psi`, `°C`, `°F`, `kJ/kg`, and
other display units are adapter-facing units, not domain-internal canonical
units.

## 2. Unit Conversion Rules

Adapters may accept display units and construct requests. The canonical unit
converter owns the registered conversion definitions for consolidated core
properties. A conversion definition must identify the property code and the
unit explicitly in both directions.

For canonicalized core quantities, an unknown unit is an error. The system must
raise an explicit failure rather than assume the input is already SI or return
the original value silently.

## 3. Specific Volume / Density Semantics

`V` means specific volume and has canonical unit `m³/kg`.

`D` means density and has canonical unit `kg/m³`.

When CoolProp requires density for a calculation that starts with specific
volume, the thermodynamic boundary performs:

```text
D = 1 / V
```

The property code `V` must not be confused with a CoolProp viscosity code or
with density. Telegram's remaining legacy `V` behavior is documented as an
explicit compatibility boundary, not as the canonical domain contract.

## 4. Thermodynamic Property Contract

`ThermodynamicStateService` accepts at least two known properties, converts
inputs to canonical SI, and returns neutral numeric results for the configured
properties plus `phase`. CoolProp-backed calculations and ideal-gas calculations
are selected by the request. Channel adapters own display conversion and error
presentation.

Reference-state-sensitive calculations must carry an explicit request policy.
Ordinary requests use a concrete policy such as `DEF`, `ASHRAE`, `IIR`, `NBP`, or
`IAPWS`; internal probes may explicitly use `CURRENT`. No ordinary calculation
may depend on whichever state a previous request left in the process.

## 5. Reference-State Contract

CoolProp reference state is process-global. `ReferenceStateService` provides the
single process-level synchronization mechanism and controls mutation. The
mutation and all dependent `PropsSI`/`PhaseSI` calls for one request execute in
the same synchronized transaction.

The mechanism and policy are separate:

- **Mechanism:** shared lock, controlled mutation, and process-global observed
  registry owned by `ReferenceStateService`.
- **Policy:** the caller/application decides which reference state the request
  requires.

Creating another service instance must not create another lock or another
process-local interpretation of `current()`.

## 6. HVAC Calculation Contract

Shared functions under `domain/hvac/` use canonical SI quantities. Typical
contracts include mass flow in `kg/s`, enthalpy in `J/kg`, heat and power in
`W`, and pressure in `Pa`. A Flet or Telegram compatibility facade may accept
`kJ/kg`, `kW`, or other display units only while converting at the adapter
boundary.

Physics formulas are not changed by an adapter conversion or architecture
refactor.

## 7. Psychrometric Contract

The shared psychrometric service accepts numeric SI-oriented inputs and returns
neutral numeric results. In particular, temperatures are represented in `K`,
pressure in `Pa`, enthalpy in `J/kg`, and the result is a structured mapping.

Flet and Telegram remain responsible for labels, display units, strings, and
message/control rendering. Telegram display strings are not the domain output
contract.

The excluded legacy model is accessed through the infrastructure adapter; the
domain service does not import the Flet-owned implementation.

## 8. Error Contract

Invalid request shape, insufficient known properties, invalid fluid/policy, and
unknown canonical units must fail explicitly. Compatibility facades may add
channel-specific error presentation, but they must not swallow canonical
contract errors or silently substitute a different physical meaning.
