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
| Container | Docker on Ubuntu 22.04 — all shell scripts and system commands target this environment |
| DB (primary) | MySQL via MySQL server |
| DB (archive) | AWS S3 — large CSV/Parquet datasets live here, not in `data/`; use boto3 or s3fs for access |
| In-memory | Pandas DataFrame — keep inference results as DataFrames to support downstream XAI computation |
| Pipeline | Apache Airflow |
| Deploy | AWS EC2 |

## Environment

Copy `.env` and fill in required values before running anything:
```
cp .env .env.local
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
