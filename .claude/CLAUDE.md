# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a greenfield ML/data engineering project with a monorepo layout. The directory structure reflects an integrated system combining a web frontend, backend API, ML model pipeline, workflow orchestration (Airflow), and experiment tracking (MLflow).

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `frontend/` | Web UI (model interaction, monitoring dashboards) |
| `backend/` | API service (REST endpoints serving the frontend and external consumers) |
| `src/` | Shared core logic used across backend and model components |
| `model/` | ML model definitions, training scripts, inference code |
| `airflow/` | Airflow DAG definitions for orchestrating data/training pipelines |
| `mlflow/` | MLflow configuration and experiment tracking setup |
| `data/` | Raw and processed datasets (not committed to git beyond samples) |
| `script/` | One-off utility scripts (data prep, deployment helpers, migrations) |
| `config/` | Environment-specific configuration files |
| `test/` | Test suites (mirrors `src/`, `backend/`, `model/` structure) |
| `docs/` | Architecture docs, API specs, and design decisions |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12.10 — use 3.12 features freely, no backward compatibility needed |
| Frontend | Next.js 16.2.6 (App Router) + React 19.2.4 — Node.js v24, npm v11; Tailwind CSS v4; Webpack |
| Container | Docker on Ubuntu 22.04 — all shell scripts and system commands target this environment |
| DB (primary) | MySQL via Aiven — SQLAlchemy 2.0 + PyMySQL |
| DB (metadata) | PostgreSQL 15 — Airflow 및 MLflow 메타데이터 저장소 |
| DB (archive) | AWS S3 — large CSV/Parquet datasets live here, not in `data/`; use boto3 for access |
| DB (search) | OpenSearch via Aiven — 패키지 설치됨(opensearch-py), 현재 코드에서 미사용 |
| In-memory | Pandas DataFrame — keep inference results as DataFrames to support downstream XAI computation |
| Pipeline | Apache Airflow 3.0.6 — CeleryExecutor; Redis 7 브로커; 7개 DAG 운영 |
| Experiment tracking | MLflow 3.12 (full) — OpenRouter 게이트웨이 통합; 기본 인증 활성화 |
| Backend API | FastAPI 0.109 + Uvicorn — JWT 인증(python-jose + bcrypt), slowapi Rate Limiting |
| Async HTTP | aiohttp 3.9 / httpx — LLM 게이트웨이 및 외부 API 호출 |
| LLM | OpenRouter API (Claude 모델 라우팅) — `OPENROUTER_API_KEY`; OpenAI SDK는 일부 평가 스크립트에서만 사용 |
| Financial data | pykrx (KRX 주가), yfinance (글로벌 지수), finance-datareader (환율·거시지표) |
| ML models | Prophet (D+5 예측, 일부 종목), statsmodels (ARIMA/VECM/Markov), PyTorch ≥ 2.0 (PatchTST), arch (GARCH) |
| ML extras | scikit-learn, XGBoost, LightGBM, SciPy — 모델 파이프라인 보조 |
| Embeddings / NLP | sentence-transformers (ko-sroberta-multitask) — 국면 요약 품질 평가 |
| Evaluation metrics | rouge-score, bert-score — 뉴스 요약 평가 |
| Web scraping | Playwright + BeautifulSoup4 — 동적 뉴스 크롤링 (네이버 뉴스 등) |
| Deploy | AWS EC2 |

## Environment

Copy `.env` and fill in required values before running anything:
```
cp .env .env
```

## Commands

> Commands will be added here as the project is scaffolded (build, lint, test, run).

## Architecture Notes

- ML experiments are tracked via MLflow; training pipelines are orchestrated by Airflow DAGs.
- The `backend/` service acts as the gateway between `frontend/` and the `model/` inference layer.
- `src/` holds shared utilities (data transforms, schema definitions, etc.) imported by both `backend/` and `model/`.

## Domain

Financial

## Project Rules

Detailed guidelines live in `.claude/rules/`:

| File | Scope |
|------|-------|
| [`rules/code-style.md`](rules/code-style.md) | Naming conventions, formatting, language-specific style |
| [`rules/testing.md`](rules/testing.md) | Test structure, coverage expectations, ML-specific testing |
| [`rules/security.md`](rules/security.md) | Secrets handling, PII, API auth, financial data compliance |