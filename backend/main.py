from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.db import engine, Base
from backend.limiter import limiter
from backend.routers import auth, news, prices, report, favorites
import backend.models.user         # noqa: F401 — Base에 모델 등록
import backend.models.news         # noqa: F401
import backend.models.user_portfolio  # noqa: F401
import backend.models.favorite     # noqa: F401

UPLOAD_DIR = Path("uploads/profile_images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[WARNING] DB 테이블 자동 생성 실패: {e}")

app = FastAPI(title="WHAi API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(prices.router, prefix="/api/v1")
app.include_router(report.router, prefix="/api/v1")
app.include_router(favorites.router, prefix="/api/v1")

app.mount("/uploads", StaticFiles(directory="uploads", check_dir=False), name="uploads")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
