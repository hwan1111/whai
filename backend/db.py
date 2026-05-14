import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local", override=True)

_raw_url = os.getenv("SERVICE_DATABASE_URL", "")
CA_PATH = str(ROOT / "config" / "certs" / "ca.pem")

# ssl_ca=${CA_PATH} 리터럴 치환
if "ssl_ca=" in _raw_url:
    _base_url = _raw_url.split("?")[0]
    _url = f"{_base_url}?charset=utf8mb4"
    _connect_args = {"ssl": {"ca": CA_PATH}}
else:
    _url = _raw_url
    _connect_args = {}

engine = create_engine(_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
