# Security Requirements

## Secrets & Credentials

- All secrets (API keys, DB passwords, broker tokens) go in `.env.local` — never hardcoded, never committed.
- `.env` in the repo is the template with empty values only.
- Use `python-dotenv` or the framework's env loader; do not `os.environ` raw strings in application logic.
- Rotate any secret that appears in a commit immediately.

## Financial Data & PII

- User account numbers, portfolio holdings, and trade history are PII — do not log them at INFO level or above.
- Mask or truncate sensitive identifiers in log output (e.g., last 4 digits of account number).
- Do not store raw PII in MLflow experiment params or tags.

## API Authentication (`backend/`)

- All endpoints require authentication except explicitly documented public health-check routes.
- Use short-lived JWT tokens; include expiry (`exp`) and issuer (`iss`) claims.
- Rate-limit financial transaction endpoints to prevent abuse.
- Validate and sanitize all query parameters — especially ticker symbols and date ranges used in DB queries.

## Input Validation

- Reject ticker symbols that do not match the allowed pattern (alphanumeric + `.` `-`).
- Clamp date range inputs to prevent unreasonably large data fetches.
- Validate numeric inputs (quantities, prices) are positive and within sane bounds before processing.

## Dependency & Supply Chain

- Pin all Python dependencies with exact versions in `requirements.txt` or `pyproject.toml`.
- Review third-party packages before adding; prefer well-maintained libraries with financial/numerical credibility (pandas, numpy, scipy, scikit-learn).

## Data at Rest

- Financial data stored in the database must be encrypted at rest (handled at the infrastructure level — document the requirement in `config/`).
- `data/` directory must not contain real customer data; use synthetic or anonymized datasets for development.
