# Code Style Guide

## Financial Domain Conventions

- Ticker symbols are always **UPPERCASE** (`AAPL`, `005930.KS`).
- All timestamps must be **UTC**; use ISO 8601 strings or Unix epoch integers — never naive datetimes.
- OHLCV column names: `open`, `high`, `low`, `close`, `volume` (snake_case, no prefixes).
- Use `Decimal` (not `float`) for monetary amounts where precision matters; include the currency unit in the variable name or docstring when ambiguous (e.g., `price_krw`, `nav_usd`).
- Standard metric names: `sharpe_ratio`, `max_drawdown`, `var_95`, `cvar_95`, `annualized_return`, `pnl`.
- Accepted abbreviations (no spelling out required): PnL, OHLCV, VaR, NAV, ETF, ROI.

## Python (`backend/`, `src/`, `model/`, `airflow/`, `script/`)

| Construct | Style | Example |
|-----------|-------|---------|
| Variables / functions | `snake_case` | `calculate_sharpe_ratio` |
| Classes | `PascalCase` | `PortfolioOptimizer` |
| Constants / env keys | `UPPER_SNAKE_CASE` | `MAX_DRAWDOWN_THRESHOLD` |
| Private methods | `_snake_case` | `_normalize_prices` |
| Type aliases | `PascalCase` | `OHLCVRow = dict[str, float]` |
| Modules / files | `snake_case` | `feature_engineering.py` |

- All public function signatures require **type hints**.
- Follow **PEP 8**; max line length **100**.
- Use `ruff` for linting.

## Airflow DAGs

Pattern: `{domain}_{pipeline}_{frequency}`

```
finance_stock_price_daily
finance_model_train_weekly
```

## MLflow Experiments

Pattern: `{model_type}/{target_variable}`

```
lstm/return_5d
xgboost/default_probability
```

## API Endpoints (`backend/`)

- Paths: **kebab-case** → `/api/v1/portfolio-metrics`
- JSON fields: **snake_case** → `{ "sharpe_ratio": 1.23 }`
- All routes versioned under `/api/v1/`.

## Frontend (`frontend/`)

| Construct | Style | Example |
|-----------|-------|---------|
| Components | `PascalCase` | `PortfolioChart.tsx` |
| Hooks / utilities | `camelCase` | `useMarketData.ts` |
| CSS modules / classes | `kebab-case` | `portfolio-card` |

- Formatter: Prettier (project defaults).
- Linter: ESLint with project config.

## SQL / Data Schemas

- Column names: `snake_case`.
- Table names: singular (`transaction`, not `transactions`).
