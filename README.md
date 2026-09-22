# Energy Air Conditioner

## Project Overview

Energy Air Conditioner is a Flet-based HVAC and thermodynamic application. It
provides property calculations, HVAC analyses, psychrometric calculations, and
thermodynamic diagrams without a Tkinter UI entry point.

## Supported Interfaces

- **Flet:** interactive desktop application launched through `run.py`.
- **Telegram:** bot interface under `Telegram_bot/`.

Both interfaces use shared application and domain services where the contract
has been consolidated. Channel-specific formatting remains in the adapters.

## High-level Architecture

```text
Flet / Telegram adapters
            ↓
       application
            ↓
          domain

infrastructure adapters ──┐
                           ↑
                    composition roots
```

The detailed dependency rules and ownership boundaries are documented in
[`docs/architecture.md`](docs/architecture.md).

## Run / Development

Install the locked environment with `uv`, then launch the Flet application:

```bash
uv sync
uv run python run.py
```

The Telegram bot has its own entrypoint and configuration requirements. Do not
make the Flet launcher depend on Telegram configuration for logging or startup.

## Testing

Run the complete test suite with:

```bash
uv run pytest -q
```

The full verification checklist is in [`docs/testing.md`](docs/testing.md).

## Documentation Index

- [Architecture](docs/architecture.md)
- [Domain contracts](docs/domain-contracts.md)
- [Compatibility boundaries](docs/compatibility-boundaries.md)
- [Testing strategy](docs/testing.md)
- [Maintenance guide](docs/maintenance.md)

## Known Compatibility Boundaries

The intentionally retained Telegram specific-volume (`V`) behavior is an
adapter boundary, not the canonical domain contract. Other current constraints
and their removal criteria are listed in
[`docs/compatibility-boundaries.md`](docs/compatibility-boundaries.md) and
[`docs/maintenance.md`](docs/maintenance.md).

## Documentation Authority

Production code and executable tests are the executable truth. The documents
under `docs/` describe intended architecture, domain contracts, accepted
compatibility boundaries, and maintenance rules. If code and documentation
diverge, treat the difference as architecture or contract drift and decide
whether the code or the documentation must be updated; do not leave the
disagreement silent.
