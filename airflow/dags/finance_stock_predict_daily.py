"""
매일 장 마감 후 종목·KOSPI·USD/KRW D+5 예측 DAG.

흐름:
  predict_and_save(×12 동적 매핑)

predict_and_save 태스크:
  1. 1순위 모델로 D+5 예측 (Choi: ARIMA/Prophet/VECM | SU: sklearn/PatchTST)
  2. MySQL JOIN으로 rolling 20거래일 MAPE 계산 → 드리프트 감지
  3. 드리프트 시 2순위 모델로 재예측
  4. CI 계산 (80%, z=1.28, rolling 20일 변동성 기반)
  5. forecast_json 구성 (Choi: D+1~D+20, SU: D+1~D+5 롤링)
  6. prediction 테이블 UPSERT

drift_detected / retrain_needed 는 DB에만 기록.
알림 없음 — 로그를 하루 한 번 확인.

의존:
  finance_market_data_daily.py → price 테이블 (드리프트 MAPE JOIN)

pretrained pkl: S3 버킷 whai-stock-models 에서 런타임 다운로드 → /tmp/su_models/ 캐시
  pretrained/saved_models/{ticker}.pkl   ← sklearn 7종목
  pretrained/patchtst_v18_model.pkl      ← PatchTST 3종목 공용
  Choi: 매일 yfinance 재학습 (pkl 없음)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
S3_BUCKET    = "whai-stock-models"
S3_PKL_DIR   = "/tmp/su_models"   # Airflow worker 임시 캐시

# ── 상수 ──────────────────────────────────────────────────────────────────
CI_Z              = 1.28   # 80% 신뢰구간 (norm.ppf(0.9))
CI_PCT            = 0.80
HORIZON           = 5      # D+5 예측
DRIFT_MULTIPLIER  = 1.5    # baseline_mape × 1.5 임계값
VOL_DAYS          = 20     # rolling 변동성 계산 윈도우
MIN_DRIFT_SAMPLES = 5      # 드리프트 감지 최소 이력 수
CHOI_FORECAST_STEPS = 25   # Choi 예측 단계 수 (D+20 BDay 커버)
SU_SEQ_LEN        = 512    # PatchTST 입력 시퀀스 길이

BASE_FEAT = ['ret_1d', 'ret_5d', 'ret_20d', 'vol_norm',
             'kospi_ret', 'sp500_ret', 'ndx_ret', 'usdkrw_ret', 'vix_chg']
ALL_FEAT  = BASE_FEAT + ['regime_prob', 'regime_duration', 'regime_change']

# ── 종목별 우선순위 모델 설정 ─────────────────────────────────────────────
#   mape: 노트북 백테스트 기준 baseline MAPE (%)
#   features: SU 모델 입력 피처 수 (9=BASE_FEAT, 12=ALL_FEAT)
#   pkl: 프로젝트 루트 기준 상대경로
MODEL_PRIORITY: dict[str, dict] = {
    '105560': {
        'name': 'KB금융',
        'priority_1': {
            'model': 'ARIMA', 'source': 'Choi', 'mape': 1.56,
            'config': {
                'order': (3, 0, 0), 'preprocess': 'log',
                'train_window': 'Super_Short',
            },
        },
        'priority_2': {
            'model': 'LGBMRegressor', 'source': 'SU', 'mape': 7.07,
            'config': {
                'features': 9,
                's3_key': 'pretrained/saved_models/105560.pkl',
            },
        },
    },
    '055550': {
        'name': '신한지주',
        'priority_1': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 1.72,
            'config': {
                'preprocess': 'diff1', 'train_window': 'Short',
            },
        },
        'priority_2': {
            'model': 'XGBRegressor', 'source': 'SU', 'mape': 2.08,
            'config': {
                'features': 12,
                's3_key': 'pretrained/saved_models/055550.pkl',
            },
        },
    },
    '012450': {
        'name': '한화에어로스페이스',
        'priority_1': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 3.43,
            'config': {
                'preprocess': 'ret', 'train_window': 'Mid_Short',
            },
        },
        'priority_2': {
            'model': 'LGBMRegressor', 'source': 'SU', 'mape': 11.94,
            'config': {
                'features': 12,
                's3_key': 'pretrained/saved_models/012450.pkl',
            },
        },
    },
    '000270': {
        'name': '기아',
        'priority_1': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 3.52,
            'config': {
                'preprocess': 'raw', 'train_window': 'Recent',
            },
        },
        'priority_2': {
            'model': 'ElasticNet', 'source': 'SU', 'mape': 7.44,
            'config': {
                'features': 12,
                's3_key': 'pretrained/saved_models/000270.pkl',
            },
        },
    },
    '051910': {
        'name': 'LG화학',
        'priority_1': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 4.78,
            'config': {
                'preprocess': 'diff1', 'train_window': 'Full',
            },
        },
        'priority_2': {
            'model': 'PatchTST', 'source': 'SU', 'mape': 8.08,
            'config': {
                'features': 9,
                's3_key': 'pretrained/patchtst_v18_model.pkl',
                'state_dict_key': 'LG Chem',
            },
        },
    },
    '096770': {
        'name': 'SK이노베이션',
        'priority_1': {
            'model': 'LGBMRegressor', 'source': 'SU', 'mape': 5.21,
            'config': {
                'features': 11,
                's3_key': 'pretrained/saved_models/096770.pkl',
            },
        },
        'priority_2': {
            'model': 'ARIMA', 'source': 'Choi', 'mape': 5.36,
            'config': {
                'order': (0, 0, 3), 'preprocess': 'raw',
                'train_window': 'Super_Short',
            },
        },
    },
    '079550': {
        'name': 'LIG넥스원',
        'priority_1': {
            'model': 'HuberRegressor', 'source': 'SU', 'mape': 5.68,
            'config': {
                'features': 12,
                's3_key': 'pretrained/saved_models/079550.pkl',
            },
        },
        'priority_2': {
            'model': 'VECM', 'source': 'Choi', 'mape': 5.70,
            'config': {
                'preprocess': 'level',
                'train_window': 'Mid',
                'exog_cols': ['KOSPI200', 'WTI', 'VIX'],
                'fixed_cols': ['close', 'volume'],
                'deterministic': 'co',
            },
        },
    },
    '005380': {
        'name': '현대차',
        'priority_1': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 7.82,
            'config': {
                'preprocess': 'log', 'train_window': 'Short',
            },
        },
        'priority_2': {
            'model': 'PatchTST', 'source': 'SU', 'mape': 9.87,
            'config': {
                'features': 9,
                's3_key': 'pretrained/patchtst_v18_model.pkl',
                'state_dict_key': 'Hyundai Motor',
            },
        },
    },
    '005930': {
        'name': '삼성전자',
        'priority_1': {
            'model': 'ExtraTreesRegressor', 'source': 'SU', 'mape': 5.09,
            'config': {
                'features': 12,
                's3_key': 'pretrained/saved_models/005930.pkl',
            },
        },
        'priority_2': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 10.22,
            'config': {
                'preprocess': 'diff1', 'train_window': 'Super_Short',
            },
        },
    },
    '000660': {
        'name': 'SK하이닉스',
        'priority_1': {
            'model': 'PatchTST', 'source': 'SU', 'mape': 10.84,
            'config': {
                'features': 9,
                's3_key': 'pretrained/patchtst_v18_model.pkl',
                'state_dict_key': 'SK Hynix',
            },
        },
        'priority_2': {
            'model': 'Prophet', 'source': 'Choi', 'mape': 13.13,
            'config': {
                'preprocess': 'log_diff2', 'train_window': 'Recent',
            },
        },
    },
    '000000': {
        'name': 'KOSPI',
        'asset_type': 'index',
        'yf_symbol': '^KS11',
        'drift_enabled': False,
        'priority_1': {
            'model': 'Prophet', 'source': 'Choi', 'mape': None,
            'config': {
                'preprocess': 'log', 'train_window': 'Long',
            },
        },
        'priority_2': {
            'model': 'ARIMA', 'source': 'Choi', 'mape': None,
            'config': {
                'order': (2, 0, 1), 'preprocess': 'log',
                'train_window': 'Long',
            },
        },
    },
    'USD': {
        'name': 'USD/KRW',
        'asset_type': 'fx',
        'yf_symbol': 'KRW=X',
        'drift_enabled': False,
        'priority_1': {
            'model': 'VECM', 'source': 'Choi', 'mape': None,
            'config': {
                'preprocess': 'level',
                'train_window': 'Long',
                'exog_cols': ['KOSPI200', 'WTI', 'VIX'],
                'fixed_cols': ['close'],
                'deterministic': 'co',
            },
        },
        'priority_2': {
            'model': 'Prophet', 'source': 'Choi', 'mape': None,
            'config': {
                'preprocess': 'log', 'train_window': 'Long',
            },
        },
    },
}


# ── DAG ───────────────────────────────────────────────────────────────────

default_args = {
    "owner": "ml-eng",
    "depends_on_past": False,
    "start_date": datetime(2026, 6, 9),
    "email_on_failure": True,
    "retries": 1,
    "retry_delay": timedelta(minutes=15),
}


@dag(
    dag_id="finance_stock_predict_daily",
    default_args=default_args,
    schedule="10 16 * * 1-5",    # 01:10 KST (16:10 UTC) — finance_market_data_daily(15:00) 이후
    catchup=False,
    max_active_tasks=4,         # 동시 종목 처리 수 제한 (API rate limit)
    tags=["finance", "prediction", "drift"],
    doc_md=__doc__,
)
def finance_stock_predict_daily():

    @task(task_id="predict_and_save")
    def predict_and_save(ticker: str) -> dict:
        """종목별 예측 + 드리프트 감지 + MySQL UPSERT. 결과 summary dict 반환."""

        # ── 무거운 import는 태스크 내부에서 (Airflow 직렬화 방지) ──────────
        import os
        import pickle
        import warnings

        import mlflow
        import numpy as np
        import pandas as pd
        import torch
        import torch.nn as nn
        from dotenv import load_dotenv
        from pandas.tseries.offsets import BDay
        from sqlalchemy import create_engine, text

        warnings.filterwarnings("ignore")
        load_dotenv(PROJECT_ROOT / ".env", override=True)

        # MLflow 설정 (auth env 변수를 먼저 세팅해야 load_dotenv 덮어쓰기 방지)
        os.environ.setdefault("MLFLOW_TRACKING_USERNAME", "admin")
        os.environ.setdefault("MLFLOW_TRACKING_PASSWORD", "Woorifisateam4")
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://52.78.237.104:5001"))

        today    = pd.Timestamp.today().normalize()
        info     = MODEL_PRIORITY[ticker]
        name     = info["name"]

        # ── DB 연결 ────────────────────────────────────────────────────────
        def _get_engine():
            raw = os.environ["SERVICE_DATABASE_URL"]
            ca  = str(PROJECT_ROOT / "config" / "certs" / "ca.pem")
            if "ssl_ca=" in raw:
                url  = raw.split("?")[0] + "?charset=utf8mb4"
                args = {"ssl": {"ca": ca}}
            else:
                url, args = raw, {}
            return create_engine(url, connect_args=args, pool_pre_ping=True)

        engine = _get_engine()

        # ── 학습 구간 시작일 ───────────────────────────────────────────────
        def _window_start(name: str) -> pd.Timestamp:
            months = {
                "Super_Short": 6, "Short": 18, "Mid_Short": 24,
                "Recent": 30,    "Mid": 36,    "Mid_Long": 42,  "Long": 48,
            }
            if name in months:
                return today - pd.DateOffset(months=months[name])
            return pd.Timestamp("2020-01-01")   # 'Full'

        # ── CI 계산 ────────────────────────────────────────────────────────
        def _ci(base: float, log_ret: float, vol: float, h: int) -> tuple[float, float]:
            half = CI_Z * vol * np.sqrt(h)
            return round(base * np.exp(log_ret + half), 2), \
                   round(base * np.exp(log_ret - half), 2)

        # ── Rolling MAPE (MySQL JOIN) ──────────────────────────────────────
        def _rolling_mape() -> tuple[float | None, int]:
            sql = text("""
                SELECT p.pred_price_d5, pr.close
                  FROM prediction p
                  JOIN price pr
                    ON pr.ticker = :t AND pr.date = p.target_date
                 WHERE p.ticker = :t
                   AND p.target_date <= :today
                   AND pr.close IS NOT NULL
                 ORDER BY p.date DESC
                 LIMIT :lim
            """)
            with engine.connect() as conn:
                rows = conn.execute(
                    sql, {"t": ticker, "today": today.date(), "lim": VOL_DAYS}
                ).fetchall()
            if len(rows) < MIN_DRIFT_SAMPLES:
                return None, len(rows)
            mapes = [
                abs(float(pred) - float(actual)) / float(actual) * 100
                for pred, actual in rows if actual
            ]
            return (float(np.mean(mapes)) if mapes else None), len(mapes)

        # ──────────────────────────────────────────────────────────────────
        # CHOI 모델 (ARIMA / Prophet / VECM)
        # ──────────────────────────────────────────────────────────────────

        def _choi_preprocess(series: pd.Series, name: str) -> pd.Series:
            ops = {
                "raw":      lambda s: s,
                "log":      lambda s: np.log(s),
                "diff1":    lambda s: s.diff().dropna(),
                "ret":      lambda s: np.log(s).diff().dropna(),
                "diff2":    lambda s: s.diff().diff().dropna(),
                "log_diff2":lambda s: np.log(s).diff().diff().dropna(),
                "seas5":    lambda s: s.diff(5).dropna(),
                "log_seas5":lambda s: np.log(s).diff(5).dropna(),
                "level":    lambda s: s,
            }
            return ops.get(name, lambda s: s)(series)

        def _choi_inverse(pred: np.ndarray, pp: str, lv: dict) -> np.ndarray:
            pred = np.asarray(pred, dtype=float)
            lp   = lv["last_price"]
            if pp == "raw":       return pred
            if pp == "log":       return np.exp(pred)
            if pp == "diff1":     return lp + np.cumsum(pred)
            if pp == "ret":       return lp * np.exp(np.cumsum(pred))
            if pp == "diff2":
                d1 = lv["last_d1"] + np.cumsum(pred)
                return lp + np.cumsum(d1)
            if pp == "log_diff2":
                ld1 = lv["last_ld1"] + np.cumsum(pred)
                return np.exp(lv["last_log"] + np.cumsum(ld1))
            if pp == "seas5":
                buf, out = list(lv["tail5"]), []
                for v in pred:
                    out.append(buf[-5] + v); buf.append(out[-1])
                return np.array(out)
            if pp == "log_seas5":
                buf, out = list(lv["tail5_log"]), []
                for v in pred:
                    out.append(buf[-5] + v); buf.append(out[-1])
                return np.exp(np.array(out))
            return pred

        def _choi_last_vals(raw: pd.Series) -> dict:
            log_s = np.log(raw)
            return {
                "last_price": float(raw.iloc[-1]),
                "last_d1":    float(raw.diff().dropna().iloc[-1]),
                "last_log":   float(log_s.iloc[-1]),
                "last_ld1":   float(log_s.diff().dropna().iloc[-1]),
                "tail5":      raw.values[-5:],
                "tail5_log":  log_s.values[-5:],
            }

        def _fetch_choi() -> dict:
            """yfinance에서 대상 자산·외생변수 데이터 수집."""
            import yfinance as yf
            start  = "2020-01-01"
            yfcode = info.get("yf_symbol", f"{ticker}.KS")

            def _col(raw_df, name: str):
                """MultiIndex/단일 컬럼 모두에서 name을 1차원 Series로 추출.
                (신버전 yfinance는 컬럼이 MultiIndex라 raw[name]이 DataFrame이 됨)"""
                if isinstance(raw_df.columns, pd.MultiIndex):
                    raw_df = raw_df.copy()
                    raw_df.columns = raw_df.columns.get_level_values(0)
                s = raw_df[name]
                if isinstance(s, pd.DataFrame):
                    s = s.iloc[:, 0]
                s.index = pd.to_datetime(s.index).tz_localize(None)
                return s

            raw = yf.download(
                yfcode, start=start, auto_adjust=True, progress=False, timeout=60
            )
            close  = _col(raw, "Close").dropna().rename("close")
            try:
                volume = _col(raw, "Volume").reindex(close.index).rename("volume")
                if volume.dropna().empty:
                    raise ValueError("volume data is empty")
                volume = volume.ffill().fillna(0.0)
            except (KeyError, ValueError):
                # 환율처럼 거래량이 없는 자산도 동일 파이프라인에서 처리한다.
                volume = pd.Series(1.0, index=close.index, name="volume")

            exog = {}
            for col, sym in [("KOSPI200","^KS200"), ("USDKRW","KRW=X"),
                              ("WTI","CL=F"),       ("VIX","^VIX")]:
                d = yf.download(sym, start=start, auto_adjust=True,
                                progress=False, timeout=60)
                exog[col] = _col(d, "Close").rename(col)

            return {"close": close, "volume": volume, "exog": exog}

        def _predict_arima(close: pd.Series, cfg: dict) -> tuple[np.ndarray, float]:
            from statsmodels.tsa.arima.model import ARIMA as StatsARIMA
            pp   = cfg["preprocess"]
            raw  = close[close.index >= _window_start(cfg["train_window"])]
            if len(raw) < 30:
                raw = close
            lv   = _choi_last_vals(raw)
            trpp = _choi_preprocess(raw, pp)
            # statsmodels 신버전 ARIMA.fit()은 disp 인자를 받지 않음 → 생략
            mdl  = StatsARIMA(trpp, order=cfg["order"]).fit()
            pred = _choi_inverse(mdl.forecast(CHOI_FORECAST_STEPS).values, pp, lv)
            vol  = float(np.log(raw / raw.shift(1)).dropna().tail(VOL_DAYS).std())
            return pred, vol

        def _predict_prophet(close: pd.Series, cfg: dict) -> tuple[np.ndarray, float]:
            from prophet import Prophet
            logging.getLogger("prophet").setLevel(logging.ERROR)
            logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
            pp   = cfg["preprocess"]
            raw  = close[close.index >= _window_start(cfg["train_window"])]
            if len(raw) < 30:
                raw = close
            lv   = _choi_last_vals(raw)
            trpp = _choi_preprocess(raw, pp)
            dfp  = trpp.reset_index()
            dfp.columns = ["ds", "y"]
            dfp["ds"] = pd.to_datetime(dfp["ds"]).dt.tz_localize(None)
            m = Prophet(daily_seasonality=False, yearly_seasonality=True,
                        weekly_seasonality=True, uncertainty_samples=False)
            m.fit(dfp)
            future = m.make_future_dataframe(periods=CHOI_FORECAST_STEPS, freq="B")
            fc     = m.predict(future)
            pred   = _choi_inverse(fc.tail(CHOI_FORECAST_STEPS)["yhat"].values, pp, lv)
            vol    = float(np.log(raw / raw.shift(1)).dropna().tail(VOL_DAYS).std())
            return pred, vol

        def _predict_vecm(choi: dict, cfg: dict) -> tuple[np.ndarray, float]:
            from statsmodels.tsa.vector_ar.vecm import VECM, select_coint_rank
            close  = choi["close"]
            volume = choi["volume"]
            panel  = pd.DataFrame({"close": close, "volume": volume})
            for col in cfg.get("exog_cols", []):
                panel[col] = choi["exog"].get(col, pd.Series(dtype=float))
            panel = panel.ffill().bfill().dropna()
            panel = panel[panel.index >= _window_start(cfg["train_window"])]
            cols  = cfg.get("fixed_cols", ["close", "volume"]) + cfg.get("exog_cols", [])
            panel = panel[[c for c in cols if c in panel.columns]]
            det   = cfg.get("deterministic", "co")
            try:
                rank = max(select_coint_rank(panel, det=det, k_ar_diff=1).rank, 1)
            except Exception:
                rank = 1  # statsmodels 버전차로 select_coint_rank 실패 시 rank=1 기본
            mdl   = VECM(panel, deterministic=det, k_ar_diff=1, coint_rank=rank).fit()
            pred  = mdl.predict(steps=CHOI_FORECAST_STEPS)[:, 0]  # close 컬럼
            vol   = float(np.log(close / close.shift(1)).dropna().tail(VOL_DAYS).std())
            return pred, vol

        def _run_choi(priority: dict, choi: dict | None = None) -> tuple:
            """(pred_price_d5, vol_20d, pred_prices_array) 반환."""
            if choi is None:
                choi = _fetch_choi()
            close  = choi["close"]
            cfg    = priority["config"]
            mdl_nm = priority["model"]

            if mdl_nm == "ARIMA":
                prices, vol = _predict_arima(close, cfg)
            elif mdl_nm == "Prophet":
                prices, vol = _predict_prophet(close, cfg)
            elif mdl_nm == "VECM":
                prices, vol = _predict_vecm(choi, cfg)
            else:
                raise ValueError(f"Unknown Choi model: {mdl_nm}")

            # CHOI_FORECAST_STEPS 개의 가격 중 D+5 BDay = index 4
            d5_price = float(prices[4]) if len(prices) > 4 else float(prices[-1])
            return d5_price, vol, prices

        def _build_choi_forecast(prices: np.ndarray, base: float, vol: float) -> list[dict]:
            """D+1~D+5 forecast_json (HORIZON까지만; 차분 모델의 먼 horizon 음수 폭주 방지).
            CI는 sqrt(h)로 확장. 음수/NaN 가격은 null 처리 (MySQL JSON 컬럼 보호)."""
            out = []
            for h in range(1, HORIZON + 1):
                if h - 1 >= len(prices):
                    break
                pp = float(prices[h - 1])
                if not np.isfinite(pp) or pp <= 0:
                    out.append({"horizon": h, "date": str((today + BDay(h)).date()),
                                "price": None, "ci_upper": None, "ci_lower": None})
                    continue
                lr   = float(np.log(pp / base)) if base > 0 else 0.0
                u, l = _ci(base, lr, vol, h)
                out.append({
                    "horizon":  h,
                    "date":     str((today + BDay(h)).date()),
                    "price":    round(pp, 2),
                    "ci_upper": u if np.isfinite(u) else None,
                    "ci_lower": l if np.isfinite(l) else None,
                })
            return out

        # ──────────────────────────────────────────────────────────────────
        # SU 모델 (sklearn / PatchTST)
        # ──────────────────────────────────────────────────────────────────

        # PatchTST 클래스 정의 (SU 코드 기준)
        class _RevIN(nn.Module):
            def __init__(self, n: int, eps: float = 1e-5):
                super().__init__()
                self.eps    = eps
                self.weight = nn.Parameter(torch.ones(1, 1, n))
                self.bias   = nn.Parameter(torch.zeros(1, 1, n))

            def forward(self, x: torch.Tensor, mode: str) -> torch.Tensor:
                if mode == "norm":
                    self._mean = x.mean(1, keepdim=True)
                    self._std  = x.std(1, keepdim=True) + self.eps
                    return (x - self._mean) / self._std * self.weight + self.bias
                return (x - self.bias) / self.weight * self._std + self._mean

        class _AdvancedPatchTST(nn.Module):
            def __init__(self, c_in: int = 9, seq_len: int = 512, pred_len: int = 5,
                         patch_len: int = 16, stride: int = 8, d_model: int = 64,
                         n_heads: int = 4, n_layers: int = 2, dropout: float = 0.1):
                super().__init__()
                self.c_in      = c_in
                self.patch_len = patch_len
                self.stride    = stride
                num_patches    = (seq_len - patch_len) // stride + 1
                self.revin     = _RevIN(c_in)
                self.patch_emb = nn.Linear(patch_len, d_model)
                self.pos_emb   = nn.Parameter(torch.zeros(1, num_patches, d_model))
                enc_layer      = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=n_heads, dim_feedforward=d_model * 4,
                    dropout=dropout, batch_first=True, activation="gelu")
                self.encoder   = nn.TransformerEncoder(enc_layer, num_layers=n_layers)
                self.head      = nn.Linear(num_patches * d_model, pred_len)

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                B = x.shape[0]
                x  = self.revin(x, "norm")
                # 채널별 패치 처리
                xc = x.permute(0, 2, 1).reshape(B * self.c_in, x.shape[1])
                patches = xc.unfold(1, self.patch_len, self.stride)
                emb = self.patch_emb(patches) + self.pos_emb
                enc = self.encoder(emb)
                out = self.head(enc.reshape(B * self.c_in, -1)).reshape(B, self.c_in, -1)
                # 모든 채널 합산 → 단일 D+5 로그수익률 스칼라
                return out[:, 0, :].sum(dim=-1)

        def _fetch_su() -> pd.DataFrame:
            """pykrx + FDR + MySQL price 테이블로 SU 피처 DataFrame 구성."""
            import FinanceDataReader as fdr
            from pykrx import stock as pkrx

            start_str = "20210101"
            today_str = today.strftime("%Y%m%d")

            # KOSPI 지수 수익률
            kospi = pkrx.get_index_ohlcv_by_date(start_str, today_str, "1001")
            kospi.index = pd.to_datetime(kospi.index)
            kospi_ret = np.log(kospi["종가"] / kospi["종가"].shift(1)).rename("kospi_ret")

            # 거시 변수 (FDR)
            macro_map = {
                "S&P500": ("sp500", "sp500_ret"),
                "NDX":    ("ndx",   "ndx_ret"),
                "USD/KRW":("usdkrw","usdkrw_ret"),
                "VIX":    ("vix",   None),
            }
            macro = pd.DataFrame()
            for sym, (col, ret_col) in macro_map.items():
                d = fdr.DataReader(sym, "20210101")[["Close"]].rename(columns={"Close": col})
                d.index = pd.to_datetime(d.index)
                macro = d if macro.empty else macro.join(d, how="outer")
            macro = macro.ffill()
            for col, ret_col in [("sp500","sp500_ret"),("ndx","ndx_ret"),("usdkrw","usdkrw_ret")]:
                macro[ret_col] = np.log(macro[col] / macro[col].shift(1))
            macro["vix_chg"] = macro["vix"].diff()
            macro = macro[["sp500_ret", "ndx_ret", "usdkrw_ret", "vix_chg"]]
            macro = macro.replace([np.inf, -np.inf], np.nan)

            # 종목 OHLCV (MySQL price 테이블 → 파케이 파일 대신 사용)
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT date, close, volume FROM price WHERE ticker = :t ORDER BY date"),
                    {"t": ticker},
                ).fetchall()
            df = pd.DataFrame(rows, columns=["date", "close", "volume"])
            df["date"]   = pd.to_datetime(df["date"])
            df["close"]  = df["close"].astype(float)
            df["volume"] = df["volume"].astype(float)
            df = df.set_index("date").sort_index()

            # 기본 피처
            df["ret_1d"]   = np.log(df["close"] / df["close"].shift(1))
            df["ret_5d"]   = np.log(df["close"] / df["close"].shift(5))
            df["ret_20d"]  = np.log(df["close"] / df["close"].shift(20))
            df["vol_norm"] = df["volume"] / df["volume"].rolling(20).mean()

            df = df.join(kospi_ret, how="left").join(macro, how="left")
            df = df.replace([np.inf, -np.inf], np.nan)

            # MSAR 레짐 피처 (MarkovAutoregression)
            try:
                from statsmodels.tsa.regime_switching.markov_autoregression \
                    import MarkovAutoregression
                ret_s = df["ret_1d"].dropna()
                res   = MarkovAutoregression(
                    ret_s.values, k_regimes=2, order=1,
                    switching_ar=False, switching_variance=True
                ).fit(disp=False, maxiter=150)
                fp   = res.filtered_marginal_probabilities
                avgs = [float(np.average(ret_s.values[-len(fp):],
                              weights=fp[:, k])) for k in range(2)]
                bull = int(np.argmax(avgs))
                prob = pd.Series(fp[:, bull],
                                 index=ret_s.index[-len(fp):]).reindex(df.index).ffill()
                df["regime_prob"]     = prob
                df["regime_duration"] = (
                    (prob > 0.5).astype(int)
                    .groupby((prob > 0.5).ne((prob > 0.5).shift()).cumsum())
                    .cumcount() + 1
                )
                df["regime_change"]   = (prob > 0.5).ne((prob > 0.5).shift()).astype(int)
            except Exception as e:
                log.warning(f"[{ticker}] MSAR 실패, 기본값 사용: {e}")
                df["regime_prob"]     = 0.5
                df["regime_duration"] = 1
                df["regime_change"]   = 0

            return df

        def _load_su_model(cfg: dict) -> tuple:
            """S3에서 pkl 다운로드 후 로드. (model, is_patchtst) 반환."""
            import boto3
            s3_key     = cfg["s3_key"]
            local_path = Path(S3_PKL_DIR) / Path(s3_key).name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if not local_path.exists():
                boto3.client("s3").download_file(S3_BUCKET, s3_key, str(local_path))
            if "state_dict_key" in cfg:
                with open(local_path, "rb") as f:
                    state_dicts = pickle.load(f)
                m = _AdvancedPatchTST()
                m.load_state_dict(state_dicts[cfg["state_dict_key"]], strict=False)
                m.eval()
                return m, True
            with open(local_path, "rb") as f:
                return pickle.load(f), False

        def _su_single_pred(model, df: pd.DataFrame, feat_cols: list[str],
                             base_dt: pd.Timestamp, is_patchtst: bool) -> float | None:
            """base_dt 기준 D+5 로그수익률 예측."""
            try:
                sub = df[df.index <= base_dt]
                if not is_patchtst:
                    row = sub.dropna(subset=feat_cols).tail(1)
                    if row.empty:
                        return None
                    X = np.nan_to_num(row[feat_cols].values)
                    return float(model.predict(X)[0])
                else:
                    seq = sub.dropna(subset=BASE_FEAT).tail(SU_SEQ_LEN)
                    if len(seq) < SU_SEQ_LEN:
                        return None
                    sv  = seq[BASE_FEAT].values.astype(np.float32)
                    xt  = torch.tensor(sv).unsqueeze(0)
                    with torch.no_grad():
                        raw = float(model(xt).item())
                    # RevIN 역정규화: 모델 내부에서 이미 처리하지만 스케일 보정
                    mu  = float(sv[:, 0].mean())
                    sig = float(sv[:, 0].std()) + 1e-8
                    return float(np.clip(raw * sig + mu, -0.15, 0.15))
            except Exception as e:
                log.warning(f"[{ticker}] SU 단일 예측 실패 @ {base_dt.date()}: {e}")
                return None

        def _run_su(priority: dict, df: pd.DataFrame | None = None) -> tuple:
            """(pred_price_d5, vol_20d, forecast_list) 반환.
            forecast_list: D+1~D+5 롤링 방식 5개 포인트."""
            if df is None:
                df = _fetch_su()
            cfg      = priority["config"]
            model, is_patchtst = _load_su_model(cfg)
            # config의 features 수가 실제 모델과 다를 수 있어(예: 096770 config=11 vs 모델=9),
            # sklearn 모델은 모델이 기대하는 피처 수(n_features_in_)를 신뢰한다.
            n_feat   = cfg.get("features", 9)
            if not is_patchtst and hasattr(model, "n_features_in_"):
                n_feat = int(model.n_features_in_)
            feat_cols = [f for f in ALL_FEAT if f in df.columns][:n_feat]

            vol        = float(df["ret_1d"].dropna().tail(VOL_DAYS).std())
            base_price = float(df["close"].iloc[-1])

            # 오늘 기준 D+5 메인 예측
            lr_d5 = _su_single_pred(model, df, feat_cols, today, is_patchtst)
            if lr_d5 is None:
                raise RuntimeError(f"[{ticker}] SU D+5 메인 예측 실패")
            lr_d5     = float(np.clip(lr_d5, -0.3, 0.3))
            pred_d5   = base_price * np.exp(lr_d5)

            # D+1~D+5 롤링 forecast_json
            # base_dt = today - (HORIZON - h) BDay 에서 예측한 D+5가 today + h BDay
            forecast = []
            for h in range(1, HORIZON + 1):
                base_dt   = today - BDay(HORIZON - h)
                target_dt = today + BDay(h)
                bp  = df["close"].asof(base_dt)
                bp  = float(bp) if not np.isnan(float(bp)) else base_price
                lr  = _su_single_pred(model, df, feat_cols, base_dt, is_patchtst)
                if lr is None:
                    lr = lr_d5
                lr  = float(np.clip(lr, -0.3, 0.3))
                pp  = bp * np.exp(lr)
                u, l = _ci(bp, lr, vol, HORIZON)
                forecast.append({
                    "horizon":  h,
                    "date":     str(target_dt.date()),
                    "price":    round(pp, 2),
                    "ci_upper": u,
                    "ci_lower": l,
                })

            return pred_d5, vol, forecast

        # ──────────────────────────────────────────────────────────────────
        # 메인 플로우
        # ──────────────────────────────────────────────────────────────────
        try:
            p1        = info["priority_1"]
            p2        = info["priority_2"]
            target_dt = (today + BDay(HORIZON)).date()
            drift_enabled = info.get("drift_enabled", True)

            def _threshold(priority: dict) -> float:
                baseline = priority.get("mape")
                return round(baseline * DRIFT_MULTIPLIER, 4) if baseline is not None else 0.0

            choi_data: dict | None = None
            su_df:     pd.DataFrame | None = None

            # Step 0: model_config 읽기 (강제 2순위 전환 여부) ────────────
            def _check_model_config() -> str | None:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT force_priority FROM model_config WHERE ticker = :t"),
                        {"t": ticker},
                    ).fetchone()
                return row[0] if row else None

            force_priority = _check_model_config()

            # Step 1: 예측 실행 ───────────────────────────────────────────
            if force_priority == "priority_2":
                # model_config에 의한 강제 2순위 전환
                log.info(
                    f"[{ticker}/{name}] model_config 강제 전환 "
                    f"→ {p2['model']}({p2['source']}) 사용"
                )
                threshold = _threshold(p2)
                if p2["source"] == "Choi":
                    choi_data = _fetch_choi()
                    d5, vol, prices = _run_choi(p2, choi_data)
                    base_price    = float(choi_data["close"].iloc[-1])
                    forecast_json = _build_choi_forecast(prices, base_price, vol)
                else:
                    su_df = _fetch_su()
                    d5, vol, forecast_json = _run_su(p2, su_df)
                    base_price = float(su_df["close"].iloc[-1])
                model_used   = "priority_2"
                model_name   = p2["model"]
                model_source = p2["source"]
            elif p1["source"] == "Choi":
                threshold = _threshold(p1)
                choi_data = _fetch_choi()
                d5, vol, prices = _run_choi(p1, choi_data)
                base_price    = float(choi_data["close"].iloc[-1])
                forecast_json = _build_choi_forecast(prices, base_price, vol)
                model_used   = "priority_1"
                model_name   = p1["model"]
                model_source = p1["source"]
            else:
                threshold = _threshold(p1)
                su_df = _fetch_su()
                d5, vol, forecast_json = _run_su(p1, su_df)
                base_price = float(su_df["close"].iloc[-1])
                model_used   = "priority_1"
                model_name   = p1["model"]
                model_source = p1["source"]

            lr_d5      = float(np.log(d5 / base_price)) if base_price > 0 else 0.0
            ci_u, ci_l = _ci(base_price, lr_d5, vol, HORIZON)

            # Step 2: 드리프트 감지 ───────────────────────────────────────
            rolling_mape, n_samples = _rolling_mape()
            drift   = (
                drift_enabled
                and rolling_mape is not None
                and rolling_mape > threshold
            )
            retrain = False

            # Step 3: 드리프트 시 2순위 실행 (force_priority 없을 때만) ──
            if drift and force_priority != "priority_2":
                log.info(
                    f"[{ticker}/{name}] 드리프트 감지 — "
                    f"MAPE {rolling_mape:.2f}% > threshold {threshold:.2f}%"
                )
                try:
                    if p2["source"] == "Choi":
                        if choi_data is None:
                            choi_data = _fetch_choi()
                        d5, vol, prices = _run_choi(p2, choi_data)
                        base_price    = float(choi_data["close"].iloc[-1])
                        forecast_json = _build_choi_forecast(prices, base_price, vol)
                    else:
                        if su_df is None:
                            su_df = _fetch_su()
                        d5, vol, forecast_json = _run_su(p2, su_df)
                        base_price = float(su_df["close"].iloc[-1])

                    lr_d5   = float(np.log(d5 / base_price)) if base_price > 0 else 0.0
                    ci_u, ci_l = _ci(base_price, lr_d5, vol, HORIZON)
                    model_used   = "priority_2"
                    model_name   = p2["model"]
                    model_source = p2["source"]

                    # 2순위도 임계값 초과 → 재학습 필요
                    p2_threshold = _threshold(p2)
                    if p2_threshold and rolling_mape > p2_threshold:
                        retrain = True
                        log.warning(f"[{ticker}/{name}] 2순위도 임계값 초과 → 재학습 필요")

                except Exception as e2:
                    log.error(f"[{ticker}/{name}] 2순위 예측 실패, 1순위 결과 유지: {e2}")
                    model_used   = "priority_1"
                    model_name   = p1["model"]
                    model_source = p1["source"]

            # Step 4: MySQL UPSERT ────────────────────────────────────────
            record = {
                "ticker":        ticker,
                "date":          str(today.date()),
                "target_date":   str(target_dt),
                "model_used":    model_used,
                "model_name":    model_name,
                "model_source":  model_source,
                "base_price":    round(base_price, 4),
                "pred_price_d5": round(d5, 4),
                "pred_return_d5":round(lr_d5, 6),
                "ci_pct":        CI_PCT,
                "ci_upper_d5":   ci_u,
                "ci_lower_d5":   ci_l,
                "vol_20d":       round(vol, 6),
                "drift_detected":int(drift),
                "rolling_mape":  round(rolling_mape, 4) if rolling_mape else None,
                "threshold":     threshold,
                "retrain_needed":int(retrain),
                "forecast_json": json.dumps(forecast_json, ensure_ascii=False),
            }
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO prediction
                            (ticker, date, target_date, model_used, model_name,
                             model_source, base_price, pred_price_d5, pred_return_d5,
                             ci_pct, ci_upper_d5, ci_lower_d5, vol_20d,
                             drift_detected, rolling_mape, threshold,
                             retrain_needed, forecast_json)
                        VALUES
                            (:ticker, :date, :target_date, :model_used, :model_name,
                             :model_source, :base_price, :pred_price_d5, :pred_return_d5,
                             :ci_pct, :ci_upper_d5, :ci_lower_d5, :vol_20d,
                             :drift_detected, :rolling_mape, :threshold,
                             :retrain_needed, :forecast_json)
                        ON DUPLICATE KEY UPDATE
                            model_used     = VALUES(model_used),
                            model_name     = VALUES(model_name),
                            model_source   = VALUES(model_source),
                            pred_price_d5  = VALUES(pred_price_d5),
                            pred_return_d5 = VALUES(pred_return_d5),
                            ci_upper_d5    = VALUES(ci_upper_d5),
                            ci_lower_d5    = VALUES(ci_lower_d5),
                            vol_20d        = VALUES(vol_20d),
                            drift_detected = VALUES(drift_detected),
                            rolling_mape   = VALUES(rolling_mape),
                            retrain_needed = VALUES(retrain_needed),
                            forecast_json  = VALUES(forecast_json),
                            created_at     = CURRENT_TIMESTAMP
                    """),
                    record,
                )

            # Step 5: MLflow 예측 run 기록 ────────────────────────────
            try:
                mlflow.set_experiment(f"stock_prediction/{ticker}")
                with mlflow.start_run(run_name=f"{today.date()}_{model_name}"):
                    mlflow.log_params({
                        "ticker":       ticker,
                        "name":         name,
                        "model_name":   model_name,
                        "model_source": model_source,
                        "model_used":   model_used,
                        "threshold":    threshold,
                        "ci_pct":       CI_PCT,
                    })
                    mlflow.log_metrics({
                        "pred_price_d5":  round(d5, 2),
                        "pred_return_d5": round(lr_d5, 6),
                        "vol_20d":        round(vol, 6),
                        "rolling_mape":   round(rolling_mape, 4) if rolling_mape else -1.0,
                        "drift_detected": float(drift),
                        "retrain_needed": float(retrain),
                        "ci_upper_d5":    ci_u,
                        "ci_lower_d5":    ci_l,
                    })
                    mlflow.set_tags({
                        "date":        str(today.date()),
                        "target_date": str(target_dt),
                        "base_price":  str(round(base_price, 2)),
                    })
            except Exception as me:
                log.warning(f"[{ticker}/{name}] MLflow logging 실패 (예측은 정상): {me}")

            # Step 6: retrain_needed 시 재학습 DAG 트리거 ──────────────
            if retrain:
                try:
                    from airflow.operators.trigger_dagrun import TriggerDagRunOperator
                    TriggerDagRunOperator(
                        task_id=f"trigger_retrain_{ticker}",
                        trigger_dag_id="finance_model_retrain",
                        conf={"ticker": ticker},
                        wait_for_completion=False,
                    ).execute(context={})
                    log.info(f"[{ticker}/{name}] 재학습 DAG 트리거 완료")
                except Exception as te:
                    log.error(f"[{ticker}/{name}] 재학습 DAG 트리거 실패: {te}")



            log.info(
                f"[{ticker}/{name}] 완료 — {model_name}({model_source}) "
                f"D+5={d5:,.0f}원  CI=[{ci_l:,.0f}, {ci_u:,.0f}]  "
                f"drift={'Y' if drift else 'N'}  retrain={'Y' if retrain else 'N'}"
            )
            return {
                "ticker":        ticker,
                "name":          name,
                "model_name":    model_name,
                "model_source":  model_source,
                "model_used":    model_used,
                "pred_price_d5": round(d5, 2),
                "rolling_mape":  rolling_mape,
                "threshold":     threshold,
                "drift_detected":drift,
                "retrain_needed":retrain,
                "status":        "success",
            }

        except Exception as exc:
            log.error(f"[{ticker}/{name}] 예측 실패: {exc}", exc_info=True)
            return {
                "ticker":        ticker,
                "name":          name,
                "status":        "failed",
                "error":         str(exc),
                "drift_detected":False,
                "retrain_needed":False,
            }

    # ── DAG 흐름 ──────────────────────────────────────────────────────────
    predict_and_save.expand(ticker=list(MODEL_PRIORITY.keys()))


finance_stock_predict_daily()
