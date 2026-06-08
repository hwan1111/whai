from __future__ import annotations

from datetime import datetime
from typing import Literal

import pandas as pd

# 종목코드 → 표시명 (코드가 안정적인 식별자)
TICKERS: dict[str, str] = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "005380": "현대차",
    "000270": "기아",
    "079550": "LIG넥스원",
    "012450": "한화에어로스페이스",
    "105560": "KB금융",
    "055550": "신한지주",
    "051910": "LG화학",
    "096770": "SK이노베이션",
}

ScaleMode = Literal["indexed", "pct_change", "raw"]

_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


def _fetch_prices(codes: list[str], start: str, end: str) -> pd.DataFrame:
    try:
        import FinanceDataReader as fdr
    except ImportError:
        raise ImportError("pip install finance-datareader")

    series = {code: fdr.DataReader(code, start, end)["Close"] for code in codes}
    return pd.DataFrame(series).dropna()


def get_price_data(
    codes: list[str] | None = None,
    start: str = "2020-01-01",
    end: str | None = None,
    mode: ScaleMode = "indexed",
) -> dict:
    """
    FastAPI 응답용 JSON-serializable 가격 데이터 반환.

    Response schema:
        {
            "meta": {"mode": str, "start": str, "end": str},
            "series": [
                {
                    "code": str,
                    "name": str,
                    "color": str,
                    "data": [{"date": "YYYY-MM-DD", "value": float}, ...]
                }
            ]
        }
    """
    codes = codes or list(TICKERS.keys())
    end = end or datetime.today().strftime("%Y-%m-%d")

    unknown = [c for c in codes if c not in TICKERS]
    if unknown:
        raise ValueError(f"알 수 없는 종목코드: {unknown}")

    price_df = _fetch_prices(codes, start, end)

    if mode == "indexed":
        plot_df = price_df / price_df.iloc[0] * 100
    elif mode == "pct_change":
        plot_df = (price_df / price_df.iloc[0] - 1) * 100
    else:
        plot_df = price_df

    series = [
        {
            "code": code,
            "name": TICKERS.get(code, code),
            "color": _COLORS[i % len(_COLORS)],
            "data": [
                {"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
                for d, v in plot_df[code].items()
            ],
        }
        for i, code in enumerate(codes)
    ]

    return {"meta": {"mode": mode, "start": start, "end": end}, "series": series}


def plot_price_chart(
    codes: list[str] | None = None,
    start: str = "2020-01-01",
    end: str | None = None,
    mode: ScaleMode = "indexed",
):
    """
    탐색용 Plotly 선 차트. get_price_data() 래퍼.

    Returns:
        plotly.graph_objects.Figure
        .show()           — 브라우저 표시
        .write_html(path) — HTML 파일 저장
        .to_json()        — Plotly JSON (react-plotly.js 연동 시)
    """
    import plotly.graph_objects as go

    payload = get_price_data(codes=codes, start=start, end=end, mode=mode)
    meta = payload["meta"]

    y_titles: dict[str, str] = {
        "indexed": "지수 (첫날=100)",
        "pct_change": "누적 등락률 (%)",
        "raw": "종가 (원)",
    }

    fig = go.Figure()
    for s in payload["series"]:
        fig.add_trace(go.Scatter(
            x=[p["date"] for p in s["data"]],
            y=[p["value"] for p in s["data"]],
            name=s["name"],
            line=dict(color=s["color"], width=1.8),
            hovertemplate=f"<b>{s['name']}</b><br>%{{x}}<br>%{{y:.2f}}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=f"종목별 주가 비교  ({meta['start']} ~ {meta['end']})", font=dict(size=16)),
        xaxis_title="날짜",
        yaxis_title=y_titles[meta["mode"]],
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        template="plotly_white",
        height=520,
    )

    return fig
