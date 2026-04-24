# Testing Rules

## Structure

Tests live in `test/` and mirror the source layout:

```
test/
  backend/      → mirrors backend/
  src/          → mirrors src/
  model/        → mirrors model/
  airflow/      → DAG integrity and task tests
```

## Python Tests

- Framework: `pytest`.
- File naming: `test_{module_name}.py`.
- Test function naming: `test_{function}_{scenario}` (e.g., `test_calculate_sharpe_ratio_empty_series`).
- Use fixtures for shared financial test data (price series, portfolio snapshots).
- Do not use real market API calls in unit tests — fixture data or local stubs only.

## Financial Logic Tests

- Always test with known inputs and hand-verified expected outputs (e.g., compute Sharpe ratio manually for a small series and assert against it).
- Test boundary conditions: zero returns, single-day series, all-loss periods.
- Decimal precision: assert monetary values with an explicit tolerance (`pytest.approx` with `abs=0.01` for KRW, `abs=0.0001` for USD rates).

## ML Model Tests (`model/`, `src/`)

- Smoke test: model instantiates and runs a forward pass on a minimal batch without error.
- Output shape test: assert output tensor/array shape matches expectation.
- Training tests that require large datasets should be marked `@pytest.mark.slow` and excluded from the default run.

## Airflow DAG Tests

- Every DAG must have a test that imports it and calls `dag.test()` or asserts `len(dag.tasks) > 0` — catches import errors and misconfigured dependencies.
- Task dependency order must be explicitly asserted for critical pipelines.

## Coverage

- Target: **80% line coverage** for `src/` and `backend/`.
- ML training code (`model/train*.py`) is exempt from the coverage target but must have smoke tests.
