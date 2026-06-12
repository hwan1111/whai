"""
prediction 테이블 백필 스크립트 (일회성 유틸리티)

목적:
    finance_stock_predict_daily DAG는 매일 1건씩 예측을 쌓는다.
    rolling MAPE / 드리프트 감지는 과거 예측 5건(MIN_DRIFT_SAMPLES) 이상이 쌓여야
    동작하므로, 신규 배포 직후엔 며칠을 기다려야 한다.
    이 스크립트는 과거 ~N거래일을 "그 시점 기준"으로 예측해 prediction 테이블을
    미리 채워, rolling MAPE / 드리프트 감지를 즉시 활성화한다 (발표용).

방식 (DAG 로직 충실 재현):
    - Choi(ARIMA/Prophet/VECM): as_of 시점까지 데이터를 잘라 매번 새로 학습 → 진짜 walk-forward
    - SU(sklearn/PatchTST): S3 pretrained pkl 사용. pkl은 과거 전체로 사전학습됐으므로
      엄밀히는 in-sample(편향). "배포된 시스템이 그날 냈을 예측의 충실한 재현"으로 해석할 것.
    - 드리프트 켜기: 오래된 날짜→최신 순으로 채우며 1순위 빗나가면 2순위로 전환(운영 그대로).
      retrain_needed는 DB 기록만 (실제 재학습/PatchTST 수동학습은 백필 범위 밖).

주의:
    - MODEL_PRIORITY / 상수 / 예측 로직은 finance_stock_predict_daily.py 에서 복제했다.
      DAG가 바뀌면 이 파일도 동기화할 것 (일회성 백필이라 중복 허용).
    - MLflow 기록은 생략 (목적은 prediction 테이블 채우기). retrain DAG 트리거도 생략.
    - 로컬 실행 전제: .env + config/certs/ca.pem 존재, S3/yfinance/pykrx 접근 가능.

실행:
    python script/others/backfill_predictions.py            # 기본 30거래일
    python script/others/backfill_predictions.py --days 40
    python script/others/backfill_predictions.py --dry-run  # DB 쓰기 없이 출력만
    python script/others/backfill_predictions.py --tickers 005930,000270
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pandas.tseries.offsets import BDay
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Prophet(cmdstanpy)은 임시폴더 경로에 비ASCII(한글 사용자명 등)가 있으면 Stan CSV 파싱
# 실패("An error occurred when parsing Stan csv")가 난다. ASCII 경로로 임시폴더를 고정.
# (로컬 Windows 전용 우회 — EC2 리눅스/DAG에는 무관)
import tempfile
_ASCII_TMP = PROJECT_ROOT / ".cache" / "tmp"
_ASCII_TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = os.environ["TEMP"] = os.environ["TMPDIR"] = str(_ASCII_TMP)
tempfile.tempdir = str(_ASCII_TMP)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

# ── 상수 (DAG 복제) ─────────────────────────────────────────────────────────
S3_BUCKET           = "whai-stock-models"
S3_PKL_DIR          = str(PROJECT_ROOT / ".cache" / "su_models")
CI_Z                = 1.28
CI_PCT              = 0.80
HORIZON             = 5
DRIFT_MULTIPLIER    = 1.5
VOL_DAYS            = 20
MIN_DRIFT_SAMPLES   = 5
CHOI_FORECAST_STEPS = 25
SU_SEQ_LEN          = 512

BASE_FEAT = ['ret_1d', 'ret_5d', 'ret_20d', 'vol_norm',
             'kospi_ret', 'sp500_ret', 'ndx_ret', 'usdkrw_ret', 'vix_chg']
ALL_FEAT  = BASE_FEAT + ['regime_prob', 'regime_duration', 'regime_change']

# ── 종목별 우선순위 (DAG 복제 — 변경 시 동기화) ──────────────────────────────
MODEL_PRIORITY: dict[str, dict] = {
    '105560': {'name': 'KB금융',
        'priority_1': {'model': 'ARIMA', 'source': 'Choi', 'mape': 1.56,
            'config': {'order': (3, 0, 0), 'preprocess': 'log', 'train_window': 'Super_Short'}},
        'priority_2': {'model': 'LGBMRegressor', 'source': 'SU', 'mape': 7.07,
            'config': {'features': 9, 's3_key': 'pretrained/saved_models/105560.pkl'}}},
    '055550': {'name': '신한지주',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 1.72,
            'config': {'preprocess': 'diff1', 'train_window': 'Short'}},
        'priority_2': {'model': 'XGBRegressor', 'source': 'SU', 'mape': 2.08,
            'config': {'features': 12, 's3_key': 'pretrained/saved_models/055550.pkl'}}},
    '012450': {'name': '한화에어로스페이스',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 3.43,
            'config': {'preprocess': 'ret', 'train_window': 'Mid_Short'}},
        'priority_2': {'model': 'LGBMRegressor', 'source': 'SU', 'mape': 11.94,
            'config': {'features': 12, 's3_key': 'pretrained/saved_models/012450.pkl'}}},
    '000270': {'name': '기아',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 3.52,
            'config': {'preprocess': 'raw', 'train_window': 'Recent'}},
        'priority_2': {'model': 'ElasticNet', 'source': 'SU', 'mape': 7.44,
            'config': {'features': 12, 's3_key': 'pretrained/saved_models/000270.pkl'}}},
    '051910': {'name': 'LG화학',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 4.78,
            'config': {'preprocess': 'diff1', 'train_window': 'Full'}},
        'priority_2': {'model': 'PatchTST', 'source': 'SU', 'mape': 8.08,
            'config': {'features': 9, 's3_key': 'pretrained/patchtst_v18_model.pkl', 'state_dict_key': 'LG Chem'}}},
    '096770': {'name': 'SK이노베이션',
        'priority_1': {'model': 'LGBMRegressor', 'source': 'SU', 'mape': 5.21,
            'config': {'features': 11, 's3_key': 'pretrained/saved_models/096770.pkl'}},
        'priority_2': {'model': 'ARIMA', 'source': 'Choi', 'mape': 5.36,
            'config': {'order': (0, 0, 3), 'preprocess': 'raw', 'train_window': 'Super_Short'}}},
    '079550': {'name': 'LIG넥스원',
        'priority_1': {'model': 'HuberRegressor', 'source': 'SU', 'mape': 5.68,
            'config': {'features': 12, 's3_key': 'pretrained/saved_models/079550.pkl'}},
        'priority_2': {'model': 'VECM', 'source': 'Choi', 'mape': 5.70,
            'config': {'preprocess': 'level', 'train_window': 'Mid',
                       'exog_cols': ['KOSPI200', 'WTI', 'VIX'], 'fixed_cols': ['close', 'volume'],
                       'deterministic': 'co'}}},
    '005380': {'name': '현대차',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 7.82,
            'config': {'preprocess': 'log', 'train_window': 'Short'}},
        'priority_2': {'model': 'PatchTST', 'source': 'SU', 'mape': 9.87,
            'config': {'features': 9, 's3_key': 'pretrained/patchtst_v18_model.pkl', 'state_dict_key': 'Hyundai Motor'}}},
    '005930': {'name': '삼성전자',
        'priority_1': {'model': 'ExtraTreesRegressor', 'source': 'SU', 'mape': 5.09,
            'config': {'features': 12, 's3_key': 'pretrained/saved_models/005930.pkl'}},
        'priority_2': {'model': 'Prophet', 'source': 'Choi', 'mape': 10.22,
            'config': {'preprocess': 'diff1', 'train_window': 'Super_Short'}}},
    '000660': {'name': 'SK하이닉스',
        'priority_1': {'model': 'PatchTST', 'source': 'SU', 'mape': 10.84,
            'config': {'features': 9, 's3_key': 'pretrained/patchtst_v18_model.pkl', 'state_dict_key': 'SK Hynix'}},
        'priority_2': {'model': 'Prophet', 'source': 'Choi', 'mape': 13.13,
            'config': {'preprocess': 'log_diff2', 'train_window': 'Recent'}}},
}


# ── DB ──────────────────────────────────────────────────────────────────────
def get_engine():
    raw = os.environ["SERVICE_DATABASE_URL"]
    ca  = str(PROJECT_ROOT / "config" / "certs" / "ca.pem")
    if "ssl_ca=" in raw:
        url  = raw.split("?")[0] + "?charset=utf8mb4"
        args = {"ssl": {"ca": ca}}
    else:
        url, args = raw, {}
    return create_engine(url, connect_args=args, pool_pre_ping=True)


# ── 공통 유틸 ────────────────────────────────────────────────────────────────
def _window_start(name: str, ref: pd.Timestamp) -> pd.Timestamp:
    months = {"Super_Short": 6, "Short": 18, "Mid_Short": 24,
              "Recent": 30, "Mid": 36, "Mid_Long": 42, "Long": 48}
    if name in months:
        return ref - pd.DateOffset(months=months[name])
    return pd.Timestamp("2020-01-01")


def _ci(base: float, log_ret: float, vol: float, h: int) -> tuple[float, float]:
    half = CI_Z * vol * np.sqrt(h)
    return (round(base * np.exp(log_ret + half), 2),
            round(base * np.exp(log_ret - half), 2))


# ── CHOI 모델 ────────────────────────────────────────────────────────────────
def _choi_preprocess(series: pd.Series, name: str) -> pd.Series:
    ops = {
        "raw": lambda s: s, "log": lambda s: np.log(s),
        "diff1": lambda s: s.diff().dropna(), "ret": lambda s: np.log(s).diff().dropna(),
        "diff2": lambda s: s.diff().diff().dropna(),
        "log_diff2": lambda s: np.log(s).diff().diff().dropna(),
        "seas5": lambda s: s.diff(5).dropna(), "log_seas5": lambda s: np.log(s).diff(5).dropna(),
        "level": lambda s: s,
    }
    return ops.get(name, lambda s: s)(series)


def _choi_inverse(pred: np.ndarray, pp: str, lv: dict) -> np.ndarray:
    pred = np.asarray(pred, dtype=float)
    lp   = lv["last_price"]
    if pp == "raw":   return pred
    if pp == "log":   return np.exp(pred)
    if pp == "diff1": return lp + np.cumsum(pred)
    if pp == "ret":   return lp * np.exp(np.cumsum(pred))
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
    return {"last_price": float(raw.iloc[-1]),
            "last_d1": float(raw.diff().dropna().iloc[-1]),
            "last_log": float(log_s.iloc[-1]),
            "last_ld1": float(log_s.diff().dropna().iloc[-1]),
            "tail5": raw.values[-5:], "tail5_log": log_s.values[-5:]}


def fetch_choi_full(ticker: str) -> dict:
    """yfinance 전체 데이터 1회 다운로드 (시점별 truncation은 호출부에서)."""
    import yfinance as yf

    def _col(raw: pd.DataFrame, name: str) -> pd.Series:
        """MultiIndex/단일 컬럼 모두에서 name 컬럼을 1차원 Series로 추출."""
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.copy()
            raw.columns = raw.columns.get_level_values(0)
        s = raw[name]
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s

    yfcode = f"{ticker}.KS"
    raw = yf.download(yfcode, start="2020-01-01", auto_adjust=True, progress=False, timeout=60)
    close  = _col(raw, "Close").dropna().rename("close")
    volume = _col(raw, "Volume").rename("volume")
    exog = {}
    for col, sym in [("KOSPI200", "^KS200"), ("USDKRW", "KRW=X"), ("WTI", "CL=F"), ("VIX", "^VIX")]:
        d = yf.download(sym, start="2020-01-01", auto_adjust=True, progress=False, timeout=60)
        exog[col] = _col(d, "Close").rename(col)
    return {"close": close, "volume": volume, "exog": exog}


def _truncate_choi(choi_full: dict, as_of: pd.Timestamp) -> dict:
    """as_of 시점까지로 자르기 (미래 데이터 누수 방지)."""
    return {
        "close":  choi_full["close"][choi_full["close"].index <= as_of],
        "volume": choi_full["volume"][choi_full["volume"].index <= as_of],
        "exog":   {k: v[v.index <= as_of] for k, v in choi_full["exog"].items()},
    }


def _predict_arima(close: pd.Series, cfg: dict, as_of: pd.Timestamp):
    from statsmodels.tsa.arima.model import ARIMA as StatsARIMA
    pp  = cfg["preprocess"]
    raw = close[close.index >= _window_start(cfg["train_window"], as_of)]
    if len(raw) < 30:
        raw = close
    lv   = _choi_last_vals(raw)
    trpp = _choi_preprocess(raw, pp)
    mdl  = StatsARIMA(trpp, order=cfg["order"]).fit(disp=False)
    pred = _choi_inverse(mdl.forecast(CHOI_FORECAST_STEPS).values, pp, lv)
    vol  = float(np.log(raw / raw.shift(1)).dropna().tail(VOL_DAYS).std())
    return pred, vol


def _predict_prophet(close: pd.Series, cfg: dict, as_of: pd.Timestamp):
    from prophet import Prophet
    pp  = cfg["preprocess"]
    raw = close[close.index >= _window_start(cfg["train_window"], as_of)]
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


def _predict_vecm(choi: dict, cfg: dict, as_of: pd.Timestamp):
    from statsmodels.tsa.vector_ar.vecm import VECM, select_coint_rank
    close, volume = choi["close"], choi["volume"]
    panel = pd.DataFrame({"close": close, "volume": volume})
    for col in cfg.get("exog_cols", []):
        panel[col] = choi["exog"].get(col, pd.Series(dtype=float))
    panel = panel.ffill().bfill().dropna()
    panel = panel[panel.index >= _window_start(cfg["train_window"], as_of)]
    cols  = cfg.get("fixed_cols", ["close", "volume"]) + cfg.get("exog_cols", [])
    panel = panel[[c for c in cols if c in panel.columns]]
    det   = cfg.get("deterministic", "co")
    rank  = max(select_coint_rank(panel, det=det, k_ar_diff=1).rank, 1)
    mdl   = VECM(panel, deterministic=det, k_ar_diff=1, coint_rank=rank).fit()
    pred  = mdl.predict(steps=CHOI_FORECAST_STEPS)[:, 0]
    vol   = float(np.log(close / close.shift(1)).dropna().tail(VOL_DAYS).std())
    return pred, vol


def run_choi(priority: dict, choi: dict, as_of: pd.Timestamp):
    cfg, mdl_nm = priority["config"], priority["model"]
    if mdl_nm == "ARIMA":
        prices, vol = _predict_arima(choi["close"], cfg, as_of)
    elif mdl_nm == "Prophet":
        prices, vol = _predict_prophet(choi["close"], cfg, as_of)
    elif mdl_nm == "VECM":
        prices, vol = _predict_vecm(choi, cfg, as_of)
    else:
        raise ValueError(f"Unknown Choi model: {mdl_nm}")
    d5 = float(prices[4]) if len(prices) > 4 else float(prices[-1])
    return d5, vol, prices


def build_choi_forecast(prices: np.ndarray, base: float, vol: float, as_of: pd.Timestamp):
    """D+1~D+5만 저장 (차분 모델 먼 horizon 음수 폭주 방지). 음수/NaN은 null."""
    out = []
    for h in range(1, HORIZON + 1):
        if h - 1 >= len(prices):
            break
        pp = float(prices[h - 1])
        if not np.isfinite(pp) or pp <= 0:
            out.append({"horizon": h, "date": str((as_of + BDay(h)).date()),
                        "price": None, "ci_upper": None, "ci_lower": None})
            continue
        lr = float(np.log(pp / base)) if base > 0 else 0.0
        u, l = _ci(base, lr, vol, h)
        out.append({"horizon": h, "date": str((as_of + BDay(h)).date()),
                    "price": round(pp, 2),
                    "ci_upper": u if np.isfinite(u) else None,
                    "ci_lower": l if np.isfinite(l) else None})
    return out


# ── SU 모델 ──────────────────────────────────────────────────────────────────
# torch는 PatchTST(3종목)에서만 필요하므로 lazy import. (torch 미설치/DLL 오류 환경에서
# 나머지 종목은 정상 동작하도록 — DAG 원본도 태스크 내부에서 import하는 패턴)
_PATCHTST_CLASSES: dict = {}


def _get_patchtst():
    """torch import + PatchTST 클래스 정의를 최초 호출 시 1회 수행."""
    if _PATCHTST_CLASSES:
        return _PATCHTST_CLASSES
    import torch
    import torch.nn as nn

    class _RevIN(nn.Module):
        def __init__(self, n: int, eps: float = 1e-5):
            super().__init__()
            self.eps = eps
            self.weight = nn.Parameter(torch.ones(1, 1, n))
            self.bias   = nn.Parameter(torch.zeros(1, 1, n))

        def forward(self, x, mode):
            if mode == "norm":
                self._mean = x.mean(1, keepdim=True)
                self._std  = x.std(1, keepdim=True) + self.eps
                return (x - self._mean) / self._std * self.weight + self.bias
            return (x - self.bias) / self.weight * self._std + self._mean

    class _AdvancedPatchTST(nn.Module):
        def __init__(self, c_in=9, seq_len=512, pred_len=5, patch_len=16, stride=8,
                     d_model=64, n_heads=4, n_layers=2, dropout=0.1):
            super().__init__()
            self.c_in = c_in; self.patch_len = patch_len; self.stride = stride
            num_patches = (seq_len - patch_len) // stride + 1
            self.revin = _RevIN(c_in)
            self.patch_emb = nn.Linear(patch_len, d_model)
            self.pos_emb = nn.Parameter(torch.zeros(1, num_patches, d_model))
            enc_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=n_heads,
                dim_feedforward=d_model * 4, dropout=dropout, batch_first=True, activation="gelu")
            self.encoder = nn.TransformerEncoder(enc_layer, num_layers=n_layers)
            self.head = nn.Linear(num_patches * d_model, pred_len)

        def forward(self, x):
            B = x.shape[0]
            x = self.revin(x, "norm")
            xc = x.permute(0, 2, 1).reshape(B * self.c_in, x.shape[1])
            patches = xc.unfold(1, self.patch_len, self.stride)
            emb = self.patch_emb(patches) + self.pos_emb
            enc = self.encoder(emb)
            out = self.head(enc.reshape(B * self.c_in, -1)).reshape(B, self.c_in, -1)
            return out[:, 0, :].sum(dim=-1)

    _PATCHTST_CLASSES.update({"torch": torch, "PatchTST": _AdvancedPatchTST})
    return _PATCHTST_CLASSES


def fetch_su_full(ticker: str, engine) -> pd.DataFrame:
    """SU 피처 DataFrame 전체 1회 구성 (시점별 truncation은 호출부에서).

    주의: MSAR 레짐 피처는 전체 구간으로 1회 계산한다. pkl이 과거 전체로 사전학습된
    in-sample 특성상, 레짐 피처의 미세한 누수는 무시 가능 수준으로 본다.
    """
    import FinanceDataReader as fdr
    from pykrx import stock as pkrx

    # KOSPI 종합지수 (pkrx 1001). KRX 로그인 필요 → .env의 KRX_ID/KRX_PW 사용.
    kospi = pkrx.get_index_ohlcv_by_date("20210101", "20261231", "1001")
    kospi.index = pd.to_datetime(kospi.index)
    kospi_ret = np.log(kospi["종가"] / kospi["종가"].shift(1)).rename("kospi_ret")

    macro = pd.DataFrame()
    for sym, col in [("S&P500", "sp500"), ("NDX", "ndx"), ("USD/KRW", "usdkrw"), ("VIX", "vix")]:
        d = fdr.DataReader(sym, "20210101")[["Close"]].rename(columns={"Close": col})
        d.index = pd.to_datetime(d.index)
        macro = d if macro.empty else macro.join(d, how="outer")
    macro = macro.ffill()
    for col, ret_col in [("sp500", "sp500_ret"), ("ndx", "ndx_ret"), ("usdkrw", "usdkrw_ret")]:
        macro[ret_col] = np.log(macro[col] / macro[col].shift(1))
    macro["vix_chg"] = macro["vix"].diff()
    macro = macro[["sp500_ret", "ndx_ret", "usdkrw_ret", "vix_chg"]].replace([np.inf, -np.inf], np.nan)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT date, close, volume FROM price WHERE ticker = :t ORDER BY date"),
            {"t": ticker}).fetchall()
    df = pd.DataFrame(rows, columns=["date", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df = df.set_index("date").sort_index()

    df["ret_1d"]   = np.log(df["close"] / df["close"].shift(1))
    df["ret_5d"]   = np.log(df["close"] / df["close"].shift(5))
    df["ret_20d"]  = np.log(df["close"] / df["close"].shift(20))
    df["vol_norm"] = df["volume"] / df["volume"].rolling(20).mean()
    df = df.join(kospi_ret, how="left").join(macro, how="left").replace([np.inf, -np.inf], np.nan)

    try:
        from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression
        ret_s = df["ret_1d"].dropna()
        res = MarkovAutoregression(ret_s.values, k_regimes=2, order=1,
                                   switching_ar=False, switching_variance=True).fit(disp=False, maxiter=150)
        fp = res.filtered_marginal_probabilities
        avgs = [float(np.average(ret_s.values[-len(fp):], weights=fp[:, k])) for k in range(2)]
        bull = int(np.argmax(avgs))
        prob = pd.Series(fp[:, bull], index=ret_s.index[-len(fp):]).reindex(df.index).ffill()
        df["regime_prob"] = prob
        df["regime_duration"] = ((prob > 0.5).astype(int)
            .groupby((prob > 0.5).ne((prob > 0.5).shift()).cumsum()).cumcount() + 1)
        df["regime_change"] = (prob > 0.5).ne((prob > 0.5).shift()).astype(int)
    except Exception as e:
        log.warning(f"[{ticker}] MSAR 실패, 기본값: {e}")
        df["regime_prob"], df["regime_duration"], df["regime_change"] = 0.5, 1, 0
    return df


_SU_MODEL_CACHE: dict[str, tuple] = {}


def load_su_model(cfg: dict) -> tuple:
    import boto3
    s3_key = cfg["s3_key"]
    if s3_key in _SU_MODEL_CACHE:
        return _SU_MODEL_CACHE[s3_key]
    local_path = Path(S3_PKL_DIR) / Path(s3_key).name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if not local_path.exists():
        boto3.client("s3").download_file(S3_BUCKET, s3_key, str(local_path))
    if "state_dict_key" in cfg:
        with open(local_path, "rb") as f:
            state_dicts = pickle.load(f)
        PatchTST = _get_patchtst()["PatchTST"]
        m = PatchTST()
        m.load_state_dict(state_dicts[cfg["state_dict_key"]], strict=False)
        m.eval()
        result = (m, True)
    else:
        with open(local_path, "rb") as f:
            result = (pickle.load(f), False)
    _SU_MODEL_CACHE[s3_key] = result
    return result


def _su_single_pred(model, df, feat_cols, base_dt, is_patchtst):
    try:
        sub = df[df.index <= base_dt]
        if not is_patchtst:
            row = sub.dropna(subset=feat_cols).tail(1)
            if row.empty:
                return None
            X = np.nan_to_num(row[feat_cols].values)
            return float(model.predict(X)[0])
        seq = sub.dropna(subset=BASE_FEAT).tail(SU_SEQ_LEN)
        if len(seq) < SU_SEQ_LEN:
            return None
        torch = _get_patchtst()["torch"]
        sv = seq[BASE_FEAT].values.astype(np.float32)
        xt = torch.tensor(sv).unsqueeze(0)
        with torch.no_grad():
            raw = float(model(xt).item())
        mu, sig = float(sv[:, 0].mean()), float(sv[:, 0].std()) + 1e-8
        return float(np.clip(raw * sig + mu, -0.15, 0.15))
    except Exception as e:
        log.warning(f"SU 단일 예측 실패 @ {base_dt.date()}: {e}")
        return None


def run_su(priority: dict, df_full: pd.DataFrame, as_of: pd.Timestamp):
    """as_of 시점 기준 SU 예측. df는 as_of까지로 잘라 사용."""
    df  = df_full[df_full.index <= as_of]
    cfg = priority["config"]
    n_feat = cfg.get("features", 9)
    feat_cols = [f for f in ALL_FEAT if f in df.columns][:n_feat]
    model, is_patchtst = load_su_model(cfg)
    vol = float(df["ret_1d"].dropna().tail(VOL_DAYS).std())
    base_price = float(df["close"].iloc[-1])

    lr_d5 = _su_single_pred(model, df, feat_cols, as_of, is_patchtst)
    if lr_d5 is None:
        raise RuntimeError("SU D+5 메인 예측 실패")
    lr_d5 = float(np.clip(lr_d5, -0.3, 0.3))
    pred_d5 = base_price * np.exp(lr_d5)

    forecast = []
    for h in range(1, HORIZON + 1):
        base_dt   = as_of - BDay(HORIZON - h)
        target_dt = as_of + BDay(h)
        bp = df["close"].asof(base_dt)
        bp = float(bp) if not np.isnan(float(bp)) else base_price
        lr = _su_single_pred(model, df, feat_cols, base_dt, is_patchtst)
        if lr is None:
            lr = lr_d5
        lr = float(np.clip(lr, -0.3, 0.3))
        pp = bp * np.exp(lr)
        u, l = _ci(bp, lr, vol, HORIZON)
        forecast.append({"horizon": h, "date": str(target_dt.date()),
                         "price": round(pp, 2), "ci_upper": u, "ci_lower": l})
    return pred_d5, vol, forecast


# ── rolling MAPE (DAG 쿼리 복제) ─────────────────────────────────────────────
def rolling_mape(engine, ticker: str, as_of: pd.Timestamp):
    sql = text("""
        SELECT p.pred_price_d5, pr.close
          FROM prediction p
          JOIN price pr ON pr.ticker = :t AND pr.date = p.target_date
         WHERE p.ticker = :t AND p.target_date <= :today AND pr.close IS NOT NULL
         ORDER BY p.date DESC LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"t": ticker, "today": as_of.date(), "lim": VOL_DAYS}).fetchall()
    if len(rows) < MIN_DRIFT_SAMPLES:
        return None, len(rows)
    mapes = [abs(float(p) - float(a)) / float(a) * 100 for p, a in rows if a]
    return (float(np.mean(mapes)) if mapes else None), len(mapes)


# ── UPSERT (DAG SQL 복제) ────────────────────────────────────────────────────
_UPSERT = text("""
    INSERT INTO prediction
        (ticker, date, target_date, model_used, model_name, model_source,
         base_price, pred_price_d5, pred_return_d5, ci_pct, ci_upper_d5, ci_lower_d5,
         vol_20d, drift_detected, rolling_mape, threshold, retrain_needed, forecast_json)
    VALUES
        (:ticker, :date, :target_date, :model_used, :model_name, :model_source,
         :base_price, :pred_price_d5, :pred_return_d5, :ci_pct, :ci_upper_d5, :ci_lower_d5,
         :vol_20d, :drift_detected, :rolling_mape, :threshold, :retrain_needed, :forecast_json)
    ON DUPLICATE KEY UPDATE
        model_used=VALUES(model_used), model_name=VALUES(model_name),
        model_source=VALUES(model_source), pred_price_d5=VALUES(pred_price_d5),
        pred_return_d5=VALUES(pred_return_d5), ci_upper_d5=VALUES(ci_upper_d5),
        ci_lower_d5=VALUES(ci_lower_d5), vol_20d=VALUES(vol_20d),
        drift_detected=VALUES(drift_detected), rolling_mape=VALUES(rolling_mape),
        retrain_needed=VALUES(retrain_needed), forecast_json=VALUES(forecast_json),
        created_at=CURRENT_TIMESTAMP
""")


# ── 종목 1건 예측 (DAG 메인 플로우 복제, force_priority는 백필에서 None 고정) ──
def predict_one(ticker: str, as_of: pd.Timestamp, engine,
                choi_full: dict | None, su_full: pd.DataFrame | None) -> dict:
    info = MODEL_PRIORITY[ticker]
    name = info["name"]
    p1, p2 = info["priority_1"], info["priority_2"]
    target_dt = (as_of + BDay(HORIZON)).date()

    choi_t = _truncate_choi(choi_full, as_of) if choi_full is not None else None

    # Step 1: 1순위 예측
    threshold = round(p1["mape"] * DRIFT_MULTIPLIER, 4)
    if p1["source"] == "Choi":
        d5, vol, prices = run_choi(p1, choi_t, as_of)
        base_price = float(choi_t["close"].iloc[-1])
        forecast_json = build_choi_forecast(prices, base_price, vol, as_of)
    else:
        d5, vol, forecast_json = run_su(p1, su_full, as_of)
        base_price = float(su_full[su_full.index <= as_of]["close"].iloc[-1])
    model_used, model_name, model_source = "priority_1", p1["model"], p1["source"]

    lr_d5 = float(np.log(d5 / base_price)) if base_price > 0 else 0.0
    ci_u, ci_l = _ci(base_price, lr_d5, vol, HORIZON)

    # Step 2: 드리프트 감지
    rmape, n = rolling_mape(engine, ticker, as_of)
    drift = rmape is not None and rmape > threshold
    retrain = False

    # Step 3: 드리프트 시 2순위 전환
    if drift:
        try:
            if p2["source"] == "Choi":
                d5, vol, prices = run_choi(p2, choi_t if choi_t is not None
                                           else _truncate_choi(fetch_choi_full(ticker), as_of), as_of)
                base_price = float(choi_t["close"].iloc[-1]) if choi_t is not None else base_price
                forecast_json = build_choi_forecast(prices, base_price, vol, as_of)
            else:
                d5, vol, forecast_json = run_su(p2, su_full, as_of)
                base_price = float(su_full[su_full.index <= as_of]["close"].iloc[-1])
            lr_d5 = float(np.log(d5 / base_price)) if base_price > 0 else 0.0
            ci_u, ci_l = _ci(base_price, lr_d5, vol, HORIZON)
            model_used, model_name, model_source = "priority_2", p2["model"], p2["source"]
            if rmape > p2["mape"] * DRIFT_MULTIPLIER:
                retrain = True
        except Exception as e2:
            log.error(f"[{ticker}/{name}] 2순위 실패, 1순위 유지: {e2}")

    return {
        "ticker": ticker, "date": str(as_of.date()), "target_date": str(target_dt),
        "model_used": model_used, "model_name": model_name, "model_source": model_source,
        "base_price": round(base_price, 4), "pred_price_d5": round(d5, 4),
        "pred_return_d5": round(lr_d5, 6), "ci_pct": CI_PCT,
        "ci_upper_d5": ci_u, "ci_lower_d5": ci_l, "vol_20d": round(vol, 6),
        "drift_detected": int(drift),
        "rolling_mape": round(rmape, 4) if rmape else None,
        "threshold": threshold, "retrain_needed": int(retrain),
        "forecast_json": json.dumps(forecast_json, ensure_ascii=False),
        "_n_samples": n,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="백필할 과거 거래일 수")
    ap.add_argument("--tickers", type=str, default="", help="쉼표구분 종목코드 (기본 전체)")
    ap.add_argument("--dry-run", action="store_true", help="DB 쓰기 없이 출력만")
    args = ap.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] or list(MODEL_PRIORITY)
    today = pd.Timestamp.today().normalize()
    as_of_dates = list(pd.bdate_range(end=today - BDay(1), periods=args.days))  # 오래된→최신

    log.info(f"백필 시작: {len(tickers)}종목 × {len(as_of_dates)}거래일 "
             f"({as_of_dates[0].date()} ~ {as_of_dates[-1].date()}), dry_run={args.dry_run}")

    engine = get_engine()

    # 종목별 원본 데이터 1회 프리페치 (시점별 다운로드 방지)
    choi_cache: dict[str, dict] = {}
    su_cache: dict[str, pd.DataFrame] = {}
    for t in tickers:
        info = MODEL_PRIORITY[t]
        need_choi = info["priority_1"]["source"] == "Choi" or info["priority_2"]["source"] == "Choi"
        need_su   = info["priority_1"]["source"] == "SU"   or info["priority_2"]["source"] == "SU"
        log.info(f"[{t}/{info['name']}] 원본 데이터 프리페치 (choi={need_choi}, su={need_su})")
        if need_choi:
            choi_cache[t] = fetch_choi_full(t)
        if need_su:
            su_cache[t] = fetch_su_full(t, engine)

    ok = fail = 0
    for as_of in as_of_dates:
        for t in tickers:
            try:
                rec = predict_one(t, as_of, engine, choi_cache.get(t), su_cache.get(t))
                tag = f"drift→{rec['model_name']}" if rec["drift_detected"] else rec["model_name"]
                log.info(f"  {as_of.date()} [{t}/{MODEL_PRIORITY[t]['name']}] "
                         f"D+5={rec['pred_price_d5']:,.0f} {tag} "
                         f"mape={rec['rolling_mape']} n={rec['_n_samples']}")
                if not args.dry_run:
                    payload = {k: v for k, v in rec.items() if not k.startswith("_")}
                    with engine.begin() as conn:
                        conn.execute(_UPSERT, payload)
                ok += 1
            except Exception as e:
                fail += 1
                log.error(f"  {as_of.date()} [{t}] 실패: {e}")

    log.info(f"백필 완료: 성공 {ok}, 실패 {fail}")


if __name__ == "__main__":
    main()
