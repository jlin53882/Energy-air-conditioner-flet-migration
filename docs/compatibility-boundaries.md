# Compatibility Boundaries

This document lists temporary production behavior or integration boundaries that
are intentionally accepted today. It is not a migration history or a change
log. Resolved architecture work belongs in the current architecture and domain
contract documents.

## Telegram Specific Volume Compatibility

**Status:** Active

### Telegram canonical contract

`V` is specific volume in `m³/kg`. The canonical thermodynamic boundary uses
`D = 1 / V` when CoolProp requires density.

### Telegram legacy behavior

The Telegram compatibility path retains its existing specific-volume conversion
and legacy calculation semantics. Its `V` path is deliberately not treated as
the canonical domain conversion.

### Telegram rationale

Telegram callers still depend on the established behavior, and changing its
physical interpretation would be a behavior migration rather than a safe
adapter-only change.

### Telegram allowed scope

Only reference-state ownership, synchronization, explicit error handling, and
adapter wiring may be improved without changing the `V` meaning. Do not copy
this behavior into domain services or silently reinterpret existing Telegram
requests.

### Telegram removal criteria

Remove this boundary only after Telegram callers have a separately reviewed
specific-volume contract, characterization coverage, and an explicit migration
of all affected handlers.

## Excluded Legacy Psychrometric Implementation

**Status:** Active adapter boundary

### Psychrometric canonical contract

The domain psychrometric service returns neutral numeric SI-oriented results.

### Psychrometric legacy behavior

The implementation in
`Flet_ui/PsychrometricChart/PsychrometricChart_01_ASHF_model.py` remains the
concrete calculation provider behind
`infrastructure.psychrometrics.LegacyPsychrometricModelAdapter`.

### Psychrometric rationale

Existing Flet and Telegram behavior depends on the model, while its internal
formula and tuple implementation are not part of the neutral domain contract.

### Psychrometric allowed scope

Adapters may translate inputs, result shapes, and display formatting. Domain
code must not import the excluded model, and ordinary architecture work must
not modify its internal formulas.

### Psychrometric removal criteria

Replace the adapter only when an independently characterized neutral
psychrometric implementation has parity evidence for required inputs, outputs,
invalid inputs, and channel behavior.
