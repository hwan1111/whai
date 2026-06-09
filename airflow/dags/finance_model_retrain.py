"""
SU 모델 재학습 DAG.

트리거 전용 (schedule=None) — finance_stock_predict_daily.py에서 retrain_needed=True 시 자동 트리거.
  dag_run.conf = {"ticker": "096770"}

흐름:
  retrain_model → update_model_config

재학습 대상 결정:
  SU sklearn (1순위)  → 데이터 수집 → refit → S3 업로드 → 검증 → model_config 갱신
  SU PatchTST (1순위) → 자동 재학습 불가 → force_priority_2 기록 (SU 팀원 수동 재학습 필요)
  Choi (1순위)이고 p2 SU sklearn → p2 sklearn refit → S3 업로드 → 검증
  Choi (1순위)이고 p2 PatchTST   → 별도 조치 없음 (Choi가 매일 재학습 중)

검증:
  최근 20거래일 hold-out MAPE.  baseline_mape × 1.5 이하면 model_config 초기화 (정상 복귀).

PatchTST 복구 절차 (수동):
  1. SU 팀원이 노트북으로 재학습 → S3 whai-stock-models/su/patchtst_v18_model.pkl 업로드
  2. model_config 테이블에서 해당 ticker row 삭제
  3. 다음 날 예측 DAG가 새 pkl 다운로드 → 자동 복귀
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task

log = logging.getLogger(__name__)

PROJECT_ROOT   = Path(__file__).resolve().parents[2]
S3_BUCKET      = "whai-stock-models"
S3_PKL_DIR     = "/tmp/su_models"
DRIFT_MULTIPLIER = 1.5
VOL_DAYS         = 20
MIN_TRAIN_ROWS   = 200   # refit 최소 데이터 수

# MODEL_PRIORITY는 predict DAG와 동일 (재학습 대상 확인용)
MODEL_PRIORITY: dict[str, dict] = {
    '105560': {
        'name': 'KB금융',
        'priority_1': {'model': 'ARIMA',  'source': 'Choi', 'mape': 1.56,
                       'config': {'order': (3,0,0), 'preprocess': 'log', 'train_window': 'Super_Short'}},
        'priority_2': {'model': 'LGBMRegressor', 'source': 'SU',   'mape': 7.07,
                       'config': {'features': 9,  's3_key': 'su/saved_models/105560.pkl'}},
    },
    '055550': {
        'name': '신한지주',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 1.72,
                       'config': {'preprocess': 'diff1', 'train_window': 'Short'}},
        'priority_2': {'model': 'XGBRegressor',  'source': 'SU',   'mape': 2.08,
                       'config': {'features': 12, 's3_key': 'su/saved_models/055550.pkl'}},
    },
    '012450': {
        'name': '한화에어로스페이스',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 3.43,
                       'config': {'preprocess': 'ret', 'train_window': 'Mid_Short'}},
        'priority_2': {'model': 'LGBMRegressor', 'source': 'SU',   'mape': 11.94,
                       'config': {'features': 12, 's3_key': 'su/saved_models/012450.pkl'}},
    },
    '000270': {
        'name': '기아',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 3.52,
                       'config': {'preprocess': 'raw', 'train_window': 'Recent'}},
        'priority_2': {'model': 'ElasticNet',    'source': 'SU',   'mape': 7.44,
                       'config': {'features': 12, 's3_key': 'su/saved_models/000270.pkl'}},
    },
    '051910': {
        'name': 'LG화학',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 4.78,
                       'config': {'preprocess': 'diff1', 'train_window': 'Full'}},
        'priority_2': {'model': 'PatchTST',      'source': 'SU',   'mape': 8.08,
                       'config': {'features': 9,  's3_key': 'su/patchtst_v18_model.pkl',
                                  'state_dict_key': 'LG Chem'}},
    },
    '096770': {
        'name': 'SK이노베이션',
        'priority_1': {'model': 'LGBMRegressor', 'source': 'SU',   'mape': 5.21,
                       'config': {'features': 11, 's3_key': 'su/saved_models/096770.pkl'}},
        'priority_2': {'model': 'ARIMA',  'source': 'Choi', 'mape': 5.36,
                       'config': {'order': (0,0,3), 'preprocess': 'raw', 'train_window': 'Super_Short'}},
    },
    '079550': {
        'name': 'LIG넥스원',
        'priority_1': {'model': 'HuberRegressor','source': 'SU',   'mape': 5.68,
                       'config': {'features': 12, 's3_key': 'su/saved_models/079550.pkl'}},
        'priority_2': {'model': 'VECM',   'source': 'Choi', 'mape': 5.70,
                       'config': {'preprocess': 'level', 'train_window': 'Mid',
                                  'exog_cols': ['KOSPI200','WTI','VIX'],
                                  'fixed_cols': ['close','volume'], 'deterministic': 'co'}},
    },
    '005380': {
        'name': '현대차',
        'priority_1': {'model': 'Prophet', 'source': 'Choi', 'mape': 7.82,
                       'config': {'preprocess': 'log', 'train_window': 'Short'}},
        'priority_2': {'model': 'PatchTST',      'source': 'SU',   'mape': 9.87,
                       'config': {'features': 9,  's3_key': 'su/patchtst_v18_model.pkl',
                                  'state_dict_key': 'Hyundai Motor'}},
    },
    '005930': {
        'name': '삼성전자',
        'priority_1': {'model': 'ExtraTreesRegressor','source': 'SU','mape': 5.09,
                       'config': {'features': 12, 's3_key': 'su/saved_models/005930.pkl'}},
        'priority_2': {'model': 'Prophet', 'source': 'Choi', 'mape': 10.22,
                       'config': {'preprocess': 'diff1', 'train_window': 'Super_Short'}},
    },
    '000660': {
        'name': 'SK하이닉스',
        'priority_1': {'model': 'PatchTST',      'source': 'SU',   'mape': 10.84,
                       'config': {'features': 9,  's3_key': 'su/patchtst_v18_model.pkl',
                                  'state_dict_key': 'SK Hynix'}},
        'priority_2': {'model': 'Prophet', 'source': 'Choi', 'mape': 13.13,
                       'config': {'preprocess': 'log_diff2', 'train_window': 'Recent'}},
    },
}

BASE_FEAT = ['ret_1d', 'ret_5d', 'ret_20d', 'vol_norm',
             'kospi_ret', 'sp500_ret', 'ndx_ret', 'usdkrw_ret', 'vix_chg']
ALL_FEAT  = BASE_FEAT + ['regime_prob', 'regime_duration', 'regime_change']

default_args = {
    "owner":           "ml-eng",
    "depends_on_past": False,
    "start_date":      datetime(2026, 6, 9),
    "retries":         1,
    "retry_delay":     timedelta(minutes=10),
}


@dag(
    dag_id="finance_model_retrain",
    default_args=default_args,
    schedule=None,      # TriggerDagRunOperator 전용
    catchup=False,
    tags=["finance", "retrain"],
    doc_md=__doc__,
)
def finance_model_retrain():

    @task
    def retrain_model(**context) -> dict:
        """종목 모델 재학습. action 결과 dict 반환."""
        import os
        import pickle
        import warnings

        import boto3
        import numpy as np
        import pandas as pd
        import FinanceDataReader as fdr
        from dotenv import load_dotenv
        from pykrx import stock as pkrx
        from sqlalchemy import create_engine, text

        warnings.filterwarnings("ignore")
        load_dotenv(PROJECT_ROOT / ".env.local", override=True)

        ticker = context["dag_run"].conf.get("ticker", "")
        if ticker not in MODEL_PRIORITY:
            raise ValueError(f"알 수 없는 ticker: {ticker}")

        info = MODEL_PRIORITY[ticker]
        name = info["name"]
        p1   = info["priority_1"]
        p2   = info["priority_2"]

        # ── DB 연결 ────────────────────────────────────────────────────
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
        today  = pd.Timestamp.today().normalize()

        # ── 재학습 대상 결정 ───────────────────────────────────────────
        # p1이 SU → p1 재학습
        # p1이 Choi이고 p2가 SU → p2 재학습
        # PatchTST 개입 시 → force_priority_2
        def _target_su(info: dict) -> tuple[dict, str] | None:
            """재학습할 SU 모델 (cfg, 'priority_1'|'priority_2') 반환. 없으면 None."""
            if p1["source"] == "SU":
                return p1, "priority_1"
            if p2["source"] == "SU":
                return p2, "priority_2"
            return None

        target = _target_su(info)
        if target is None:
            log.info(f"[{ticker}/{name}] 양쪽 모두 Choi — 매일 재학습 중, 별도 조치 없음")
            return {"action": "no_action", "ticker": ticker}

        su_model_info, which_priority = target

        # PatchTST는 자동 재학습 불가
        if su_model_info["model"] == "PatchTST":
            log.warning(
                f"[{ticker}/{name}] PatchTST drift 감지 → Choi({which_priority}의 반대) 강제 전환.\n"
                f"SU 팀원: 재학습 후 s3://{S3_BUCKET}/su/patchtst_v18_model.pkl 업로드,\n"
                f"완료 후 model_config 테이블에서 {ticker} row 삭제 시 자동 복구."
            )
            return {"action": "force_priority_2", "ticker": ticker,
                    "reason": f"PatchTST drift - 수동 재학습 필요 ({which_priority})",
                    "retrain_type": "patchtst"}

        # ── SU sklearn 재학습 ──────────────────────────────────────────
        cfg     = su_model_info["config"]
        s3_key  = cfg["s3_key"]
        n_feat  = cfg.get("features", 9)

        log.info(f"[{ticker}/{name}] {su_model_info['model']} ({which_priority}) refit 시작")

        # 1. 피처 데이터 수집 (MySQL price + 거시지표)
        def _fetch_features() -> pd.DataFrame:
            start_str = "20210101"
            today_str = today.strftime("%Y%m%d")

            kospi = pkrx.get_index_ohlcv_by_date(start_str, today_str, "1001")
            kospi.index = pd.to_datetime(kospi.index)
            kospi_ret = np.log(kospi["종가"] / kospi["종가"].shift(1)).rename("kospi_ret")

            macro_map = {
                "S&P500": "sp500", "NDX": "ndx", "USD/KRW": "usdkrw", "VIX": "vix",
            }
            macro = pd.DataFrame()
            for sym, col in macro_map.items():
                d = fdr.DataReader(sym, "20210101")[["Close"]].rename(columns={"Close": col})
                d.index = pd.to_datetime(d.index)
                macro = d if macro.empty else macro.join(d, how="outer")
            macro = macro.ffill()
            macro["sp500_ret"]  = np.log(macro["sp500"]  / macro["sp500"].shift(1))
            macro["ndx_ret"]    = np.log(macro["ndx"]    / macro["ndx"].shift(1))
            macro["usdkrw_ret"] = np.log(macro["usdkrw"] / macro["usdkrw"].shift(1))
            macro["vix_chg"]    = macro["vix"].diff()
            macro = macro[["sp500_ret", "ndx_ret", "usdkrw_ret", "vix_chg"]]
            macro = macro.replace([np.inf, -np.inf], np.nan)

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

            df["ret_1d"]   = np.log(df["close"] / df["close"].shift(1))
            df["ret_5d"]   = np.log(df["close"] / df["close"].shift(5))
            df["ret_20d"]  = np.log(df["close"] / df["close"].shift(20))
            df["vol_norm"] = df["volume"] / df["volume"].rolling(20).mean()

            df = df.join(kospi_ret, how="left").join(macro, how="left")
            df = df.replace([np.inf, -np.inf], np.nan)
            df["regime_prob"]     = 0.5
            df["regime_duration"] = 1
            df["regime_change"]   = 0
            return df

        df = _fetch_features()
        feat_cols = [f for f in ALL_FEAT if f in df.columns][:n_feat]

        # D+5 타깃 로그수익률
        df = df.copy()
        df["target"] = np.log(df["close"].shift(-5) / df["close"])
        df_clean = df.dropna(subset=feat_cols + ["target"])

        if len(df_clean) < MIN_TRAIN_ROWS + VOL_DAYS:
            log.error(f"[{ticker}/{name}] 학습 데이터 부족 ({len(df_clean)}행)")
            return {"action": "force_priority_2", "ticker": ticker,
                    "reason": f"학습 데이터 부족: {len(df_clean)}행"}

        # hold-out: 마지막 20행은 검증용으로 분리
        df_train = df_clean.iloc[:-VOL_DAYS]
        df_val   = df_clean.iloc[-VOL_DAYS:]

        X_train = df_train[feat_cols].values
        y_train = df_train["target"].values

        # 2. S3에서 현재 모델 다운로드 (모델 클래스 유지)
        local_path = Path(S3_PKL_DIR) / f"retrain_{ticker}.pkl"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client = boto3.client("s3")
        s3_client.download_file(S3_BUCKET, s3_key, str(local_path))
        with open(local_path, "rb") as f:
            model = pickle.load(f)

        # 3. refit
        model.fit(X_train, y_train)

        # 4. 검증 (hold-out 20거래일 MAPE)
        X_val     = df_val[feat_cols].values
        close_val = df_val["close"].values
        preds     = model.predict(X_val)
        mapes = []
        for i, (lr_pred, base_c) in enumerate(zip(preds, close_val)):
            pred_price   = float(base_c) * np.exp(float(np.clip(lr_pred, -0.3, 0.3)))
            actual_price = df_val["close"].iloc[i] * np.exp(df_val["target"].iloc[i])
            if actual_price > 0:
                mapes.append(abs(pred_price - actual_price) / actual_price * 100)
        val_mape  = float(np.mean(mapes)) if mapes else 999.0
        threshold = su_model_info["mape"] * DRIFT_MULTIPLIER

        log.info(
            f"[{ticker}/{name}] refit 완료 — val MAPE {val_mape:.2f}% "
            f"(threshold {threshold:.2f}%)"
        )

        # 5. S3 업로드 (검증 결과와 무관하게 업로드 — 최선 모델 유지)
        with open(local_path, "wb") as f:
            pickle.dump(model, f)
        s3_client.upload_file(str(local_path), S3_BUCKET, s3_key)
        log.info(f"[{ticker}/{name}] 새 pkl → s3://{S3_BUCKET}/{s3_key} 업로드 완료")

        if val_mape <= threshold:
            return {"action": "retrain_success", "ticker": ticker,
                    "mape": round(val_mape, 4), "which": which_priority}
        else:
            return {"action": "force_priority_2", "ticker": ticker,
                    "reason": f"refit 후 MAPE {val_mape:.2f}% > threshold {threshold:.2f}%",
                    "retrain_type": "sklearn"}

    @task
    def update_model_config(retrain_result: dict, **context):
        """재학습 결과에 따라 model_config 테이블 갱신."""
        import os
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text

        load_dotenv(PROJECT_ROOT / ".env.local", override=True)

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
        action = retrain_result.get("action")
        ticker = retrain_result.get("ticker", "")
        name   = MODEL_PRIORITY.get(ticker, {}).get("name", ticker)

        if action == "no_action":
            log.info(f"[{ticker}/{name}] 조치 없음")
            return

        if action == "retrain_success":
            # model_config row 삭제 → 정상 운영 복귀
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM model_config WHERE ticker = :t"),
                    {"t": ticker},
                )
            log.info(
                f"[{ticker}/{name}] 재학습 성공 (MAPE {retrain_result.get('mape'):.2f}%) "
                f"→ model_config 초기화, 정상 운영 복귀"
            )

        elif action == "force_priority_2":
            reason       = retrain_result.get("reason", "")
            retrain_type = retrain_result.get("retrain_type", "")
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO model_config (ticker, force_priority, reason, retrain_type)
                        VALUES (:t, 'priority_2', :r, :rt)
                        ON DUPLICATE KEY UPDATE
                            force_priority = 'priority_2',
                            reason         = VALUES(reason),
                            retrain_type   = VALUES(retrain_type)
                    """),
                    {"t": ticker, "r": reason, "rt": retrain_type},
                )
            log.warning(f"[{ticker}/{name}] force_priority_2 기록 — {reason}")

    # ── DAG 흐름 ──────────────────────────────────────────────────────────
    result = retrain_model()
    update_model_config(result)


finance_model_retrain()
