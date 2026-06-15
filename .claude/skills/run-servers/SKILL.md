---
description: Launch backend (Uvicorn) and frontend (Next.js) dev servers for this project
---

# Run Servers

## Environment

- OS: Windows 11, shell tool uses bash (forward slashes required)
- Python venv: `.venv/Scripts/activate` (sourced via bash)
- Frontend: Node.js v24, npm v11

## Backend

Working directory: repo root (`c:/Users/minha/whai`)

```bash
cd "c:/Users/minha/whai" && source .venv/Scripts/activate && PYTHONUTF8=1 uvicorn backend.main:app --port 8000 --reload
```

Run in background. Healthy when output contains:
```
INFO:     Application startup complete.
```

Smoke test:
```bash
curl -s http://127.0.0.1:8000/docs
```

## Frontend

Working directory: `frontend/`

```bash
cd "c:/Users/minha/whai/frontend" && npm run dev
```

Run in background. Healthy when output contains:
```
✓ Ready in
```

- Runs on http://localhost:3000
- Uses webpack mode (`--webpack`) — do NOT switch to Turbopack (causes DWM/GPU crash on this machine)
- `NODE_OPTIONS=--max-old-space-size=4096` applied via cross-env in package.json

## Notes

- Start backend first, then frontend
- Bash tool path issue: use forward slashes (`/`), not backslashes (`\`)
- `.venv\Scripts\activate` (PowerShell) → `.venv/Scripts/activate` (bash)
- `PYTHONUTF8=1` 필수 — `.env`에 한글 주석이 있어서 Windows 기본 인코딩(cp949)으로 읽으면 `slowapi`/Starlette에서 UnicodeDecodeError 발생
