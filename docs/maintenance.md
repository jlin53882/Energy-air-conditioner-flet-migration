# Maintenance Guide

## 1. Before Modifying Production Code

1. Search all callers and consumers of the symbol or contract.
2. Identify the current executable behavior and domain meaning.
3. Check [`compatibility-boundaries.md`](compatibility-boundaries.md) and the
   dependency direction in [`architecture.md`](architecture.md).
4. Check repository and GitNexus index freshness; do not treat a stale graph as
   the only source of caller evidence.
5. Add or update a regression test that expresses the intended behavior.
6. Make the smallest change that closes the contract.
7. Run focused tests, then the full verification set in [`testing.md`](testing.md).

## 2. Domain Change Rules

- Keep one domain implementation for each rule.
- Keep canonical quantities and unit semantics in domain/application
  boundaries, not in UI or handlers.
- Do not change physics formulas during an architecture-only refactor.
- Unknown canonical units must fail explicitly; never silently assume SI.
- Process-global dependencies require explicit request policy and tests for
  sequential, concurrent, and cross-request isolation.
- Use PEP 257 docstrings for new or changed Python functions and classes.

## 3. Architecture Change Rules

- Preserve the direction `channel adapter → application → domain`.
- Domain must not import Flet, Telegram, or infrastructure implementations.
- Application must remain independent of channel controls, updates, contexts,
  and rendering.
- New routes, modules, scripts, and entrypoints require both their import and
  registration/wiring to be checked.
- New production code must not leave zero-reference helpers, duplicate replaced
  implementations, or calculated-but-unused values.

## 4. Compatibility Boundary Rules

A compatibility facade may remain only when:

- a legacy caller still exists;
- the target contract is documented;
- the boundary has regression coverage;
- the allowed scope is narrow; and
- removal criteria are explicit.

A compatibility facade is not permission to create a permanent second core
implementation. Current accepted boundaries are listed in
[`compatibility-boundaries.md`](compatibility-boundaries.md).

## 5. Documentation Update Rules

Long-term documents describe current architecture, current domain contracts,
accepted compatibility boundaries, testing strategy, and maintenance rules.
They should use present-tense, contract-oriented language.

Do not add PR numbers, commit SHAs, phase labels, one-time audit counts, or
review snapshots to current documentation. Preserve historical evidence in Git
history and PR history. When executable behavior or an invariant changes,
update the relevant current-state document in the same change.

Documentation authority is explicit:

- production code and executable tests are the executable truth;
- `docs/architecture.md` is the intended architecture;
- `docs/domain-contracts.md` is the intended domain contract;
- `docs/compatibility-boundaries.md` records accepted temporary exceptions;
- `docs/testing.md` records the testing strategy.

A disagreement is architecture or contract drift. Determine whether code or
documentation must change; do not leave a silent divergence.

## 6. Verification Checklist

Before handoff or commit:

- focused regression tests pass;
- `uv run pytest -q` passes;
- compileall passes for the production entrypoints and packages;
- `uv lock --check` passes;
- `uv pip check` passes;
- `git diff --check` passes with the repository's line-ending policy;
- the worktree and intended branch are verified;
- external PR/branch state is read back after a push.

## 7. Current Maintenance Constraints

These are current technical constraints, not phase or PR history:

- Telegram specific-volume behavior remains an active compatibility boundary.
- Remaining compressor analyses still use legacy paths and require separate
  characterization before migration.
- Telegram constructor dependency injection is not fully consolidated.
- Chart renderer and sampling responsibilities are not fully separated.
- Packaging targets and build-script cleanup remain future maintenance work.
- Packaging metadata belongs in `pyproject.toml` and `uv.lock`; build scripts
  must target an explicit artifact and must not mutate dependency metadata as a
  build side effect.

These constraints must not be silently promoted into domain contracts. Any
future removal or migration should update the compatibility/maintenance
classification and add the corresponding tests.
