#!/usr/bin/env python3
"""
공통 이동 이벤트 KOSPI200 동일가중지수 기반 시장기여/고유수익률 분해

시장팩터: KOSPI200 동일가중지수 ETF 수익률
    1순위: KODEX 200동일가중 (252650)
    2순위: TIGER 200동일가중 (252000)
    fallback: KS200 시가총액가중

각 종목 국면 기간에 대해 계산:
    beta       : 국면 시작 직전 60거래일 OLS β (vs KOSPI200 동일가중)
    total_cum  : 국면 전체 누적 수익률
    market_cum : β × R_ew 누적 (시장기여분)
    idio_cum   : total_cum - market_cum (고유 수익률)

Usage:
    python script/calc_ex_index.py
    python script/calc_ex_index.py --input data/common_events_005930_005380.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(_handler)
logger.propagate = False

BETA_WINDOW = 60  # β 추정 롤링 윈도우 (거래일)

# KOSPI200 동일가중 ETF 티커 우선순위
_EW_ETF_CANDIDATES = [
    ("252650", "KODEX 200동일가중"),
    ("252000", "TIGER 200동일가중"),
]


# ── 데이터 조회 ───────────────────────────────────────────────────────────────

def fetch_ks200_ew(fromdate: str, todate: str) -> pd.Series:
    """
    KOSPI200 동일가중 수익률 시계열.
    ETF 종가 기반 — 구성종목 200개 직접 조회 불필요.
    """
    from_dt = pd.Timestamp(fromdate).strftime("%Y-%m-%d")
    to_dt   = pd.Timestamp(todate).strftime("%Y-%m-%d")

    for ticker, name in _EW_ETF_CANDIDATES:
        try:
            df = fdr.DataReader(ticker, from_dt, to_dt)
            if not df.empty and "Close" in df.columns:
                r = df["Close"].astype(float).pct_change().rename("R_KS200_EW")
                logger.info(f"동일가중지수 소스: {name} ({ticker})  {len(r)}행")
                return r
        except Exception as e:
            logger.warning(f"{name} ({ticker}) 조회 실패: {e}")

    logger.warning("동일가중 ETF 조회 전량 실패 → 시가총액가중 KS200 fallback")
    df = fdr.DataReader("KS200", from_dt, to_dt)
    return df["Close"].astype(float).pct_change().rename("R_KS200_EW")


def fetch_stock(ticker: str, fromdate: str, todate: str) -> pd.Series:
    from_dt = pd.Timestamp(fromdate).strftime("%Y-%m-%d")
    to_dt   = pd.Timestamp(todate).strftime("%Y-%m-%d")
    df = fdr.DataReader(ticker, from_dt, to_dt)
    return df["Close"].astype(float).pct_change().rename(f"R_{ticker}")


# ── 계산 ──────────────────────────────────────────────────────────────────────

def estimate_beta(r_i: pd.Series, r_mkt: pd.Series) -> tuple[float, float]:
    """β = cov(R_i, R_mkt) / var(R_mkt), R² = corr². 데이터 5개 미만이면 (NaN, NaN)."""
    df = pd.concat([r_i, r_mkt], axis=1).dropna()
    if len(df) < 5:
        return float("nan"), float("nan")
    cov = np.cov(df.iloc[:, 0].values, df.iloc[:, 1].values)
    if cov[1, 1] == 0:
        return float("nan"), float("nan")
    beta = float(cov[0, 1] / cov[1, 1])
    r2   = float((cov[0, 1] ** 2) / (cov[0, 0] * cov[1, 1])) if cov[0, 0] != 0 else float("nan")
    return beta, r2


def decompose(r_i: pd.Series, r_mkt: pd.Series, beta: float) -> dict:
    """
    국면 수익률 분해
      total_cum  = Π(1 + R_i) - 1
      market_cum = Π(1 + β × R_mkt) - 1
      idio_cum   = total_cum - market_cum
    """
    idx   = r_i.index.intersection(r_mkt.index)
    ri    = r_i.reindex(idx).fillna(0)
    rmkt  = r_mkt.reindex(idx).fillna(0)
    total = float((1 + ri).prod() - 1)

    if np.isnan(beta):
        return {"total_cum": round(total, 4), "market_cum": None, "idio_cum": None}

    market = float((1 + beta * rmkt).prod() - 1)
    return {
        "total_cum":  round(total, 4),
        "market_cum": round(market, 4),
        "idio_cum":   round(total - market, 4),
    }


# ── 이벤트 처리 ───────────────────────────────────────────────────────────────

def enrich_event(
    event: dict,
    tickers: list[str],
    r_ew: pd.Series,
    stock_returns: dict[str, pd.Series],
) -> dict:
    out = dict(event)

    for ticker in tickers:
        if ticker not in event:
            continue

        ev         = dict(event[ticker])
        start, end = ev["period"].split("~")
        r_i        = stock_returns[ticker]

        # β: 국면 시작 직전 BETA_WINDOW 거래일
        valid_idx = r_ew.dropna().index
        start_pos = valid_idx.searchsorted(pd.Timestamp(start))
        beta_idx  = valid_idx[max(0, start_pos - BETA_WINDOW):start_pos]
        beta, r2  = estimate_beta(r_i.reindex(beta_idx), r_ew.reindex(beta_idx))

        dec = decompose(r_i.loc[start:end], r_ew.loc[start:end], beta)

        ev["ks200_ew"] = {
            "beta": round(beta, 4) if not np.isnan(beta) else None,
            "r2":   round(r2,   4) if not np.isnan(r2)   else None,
            **dec,
        }
        out[ticker] = ev

    return out


# ── 요약 ──────────────────────────────────────────────────────────────────────

def print_summary(events: list[dict], tickers: list[str]) -> None:
    logger.info("\n" + "=" * 60)
    logger.info("KOSPI200 동일가중 기준 β / 수익률 분해 요약")
    logger.info("=" * 60)
    for ticker in tickers:
        betas, idios, markets = [], [], []
        for ev in events:
            if ticker not in ev:
                continue
            kb = ev[ticker].get("ks200_ew", {})
            if kb.get("beta") is not None:
                betas.append(kb["beta"])
            if kb.get("idio_cum") is not None:
                idios.append(kb["idio_cum"])
            if kb.get("market_cum") is not None:
                markets.append(kb["market_cum"])

        logger.info(f"\n[{ticker}]  β 계산 가능: {len(betas)}건")
        if betas:
            logger.info(f"  β 평균:        {sum(betas)/len(betas):.3f}")
            logger.info(f"  β 범위:        {min(betas):.3f} ~ {max(betas):.3f}")
            logger.info(f"  시장기여 평균: {sum(markets)/len(markets):.3f}")
            logger.info(f"  고유수익 평균: {sum(idios)/len(idios):.3f}")


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="KOSPI200 동일가중지수 기반 β/수익률 분해")
    parser.add_argument(
        "--input",
        default=str(project_root / "data" / "common_events_000660_079550.json"),
        help="공통 이벤트 JSON 경로",
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = input_path.with_name(input_path.stem + "_ex.json")

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    events  = data["events"]
    tickers = sorted({t for ev in events for t in ev if len(t) == 6 and t.isdigit()})
    logger.info(f"✓ 이벤트: {len(events)}건  종목: {tickers}")

    starts = [ev[t]["period"].split("~")[0] for ev in events for t in tickers if t in ev]
    ends   = [ev[t]["period"].split("~")[1] for ev in events for t in tickers if t in ev]

    fetch_from = (pd.Timestamp(min(starts)) - pd.offsets.BDay(90)).strftime("%Y%m%d")
    fetch_to   = pd.Timestamp(max(ends)).strftime("%Y%m%d")

    logger.info(f"데이터 조회: {fetch_from} ~ {fetch_to}")

    r_ew = fetch_ks200_ew(fetch_from, fetch_to)

    stock_returns: dict[str, pd.Series] = {}
    for ticker in tickers:
        logger.info(f"[{ticker}] 종가 조회 중...")
        stock_returns[ticker] = fetch_stock(ticker, fetch_from, fetch_to)

    enriched = []
    for i, ev in enumerate(events):
        logger.info(f"[{i+1:02d}/{len(events)}] rank={ev['rank']}  {ev['date']}")
        enriched.append(enrich_event(ev, tickers, r_ew, stock_returns))

    output = {**data, "events": enriched}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n✓ 저장 완료: {output_path}")
    print_summary(enriched, tickers)


if __name__ == "__main__":
    main()
