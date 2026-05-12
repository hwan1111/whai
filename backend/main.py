from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import engine, Base
from backend.routers import auth
import backend.models.user  # noqa: F401 — Base에 모델 등록

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[WARNING] DB 테이블 자동 생성 실패: {e}")

app = FastAPI(title="WHAi API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
