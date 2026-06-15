"""
가격 국면별 DART 공시 LLM 요약

국면 기간(start_date ~ end_date) 내 로컬 DART 공시를 수집하여
공시 사실만 요약하고 materiality를 판단한다 (주가 인과 추론 제외).

입력:
  - data/dart/{corp_name}_{ticker_code}/*.json  (로컬)
  - data/{ticker_code}/regime_news_summary_{ticker_code}.json  (국면 정의)

출력: data/{ticker_code}/regime_dart_summary_{ticker_code}.json

실행:
    python script/regime_dart_summary.py --ticker 005930
    python script/regime_dart_summary.py --ticker 005930 --provider gemini
    python script/regime_dart_summary.py --ticker 005930 --dry-run
    python script/regime_dart_summary.py --ticker 005930 --rerun-ids 3 7
"""

import argparse
import json
import logging
import os
import time
from pathlib import Path

import FinanceDataReader as fdr
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy import stats

load_dotenv(".env", override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────

DART_DIR        = Path("data/dart")
MAX_DART_CHARS  = 8_000   # 문서 당 최대 글자 수
MAX_DART_COUNT  = 10      # 국면 당 최대 공시 수

KIND_PRIORITY = {
    "정기공시":     0,
    "주요사항보고": 1,
    "공정공시":     2,
    "지분공시":     3,
    "미분류":       4,
    "":             5,
}

DEFAULT_MODEL = {
    "groq":       "llama-3.3-70b-versatile",
    "gemini":     "gemini-2.5-flash",
    "openrouter": "gpt-oss-120b:free",
}
SLEEP_SEC = {"groq": 40, "gemini": 10, "openrouter": 5}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

REQUIRED_KEYS = {"overall_summary", "disclosures", "materiality"}

_SYSTEM = """\
당신은 한국 주식시장 공시(DART) 전문 분석가입니다.
주어진 DART 공시 문서를 사실에 기반하여 요약합니다.
주가 방향이나 등락 원인을 추론하지 마세요.
공시 내용 자체만 보고 판단하세요.
반드시 JSON 형식으로만 응답하세요. 설명 텍스트는 포함하지 마세요."""

_USER_TMPL = """\
{start} ~ {end} ({days}일) {name}({code}) 국면 기간의 DART 공시입니다.
섹터: {sector}

■ 공시 목록 ({dart_count}건)
{dart_context}

■ 작성 규칙
  · 각 공시의 summary는 문서에 명시된 사실만 기재하세요.
  · 수치(금액·비율·날짜)는 원문 그대로 인용하세요. 환산·추정 금지.
  · 주가 영향, 상승/하락 원인 추론은 절대 하지 마세요.
  · materiality는 공시 내용만 보고 판단하세요 (주가 방향 참고 금지).
    - high  : 실적발표, 유상증자, CB·BW 발행, M&A, 대규모 계약·투자
    - medium: IR 개최, 임원 변동, 소규모 주요사항보고
    - low   : 소량 지분 변동, 단순 통지성 공시
    - none  : 공시 없음 또는 주가와 무관한 행정성 내용만 있는 경우
  · 공시가 없으면 disclosures는 빈 배열 []로, materiality는 "none"으로 두세요.

위 공시를 요약하고 아래 JSON으로만 응답하세요:
{{
  "overall_summary": "전체 공시를 한 줄로 요약 (없으면 '해당 기간 공시 없음')",
  "disclosures": [
    {{
      "rcept_dt":  "YYYY-MM-DD",
      "kind_label": "공시 종류",
      "report_nm":  "보고서명",
      "summary":    "공시 내용 요약 (100자 이내, 수치 원문 그대로)"
    }}
  ],
  "materiality": "high|medium|low|none"
}}"""


# ── DART 파일 로드 ────────────────────────────────────────────────────

def _find_dart_dir(ticker_code: str) -> Path | None:
    for d in DART_DIR.iterdir():
        if d.is_dir() and d.name.endswith(f"_{ticker_code}"):
            return d
    return None


def _load_dart_docs(dart_dir: Path, start: str, end: str) -> list[dict]:
    docs = []
    for f in dart_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rcept_dt = data.get("rcept_dt", "")
        if not rcept_dt or not (start <= rcept_dt <= end):
            continue
        docs.append(data)

    docs.sort(key=lambda d: (
        KIND_PRIORITY.get(d.get("kind_label") or "", 5),
        d.get("rcept_dt", ""),
    ))
    return docs[:MAX_DART_COUNT]


def _build_dart_context(docs: list[dict]) -> str:
    if not docs:
        return "(해당 기간 공시 없음)"
    parts = []
    for d in docs:
        kind  = d.get("kind_label") or "미분류"
        dt    = d.get("rcept_dt", "")
        nm    = d.get("report_nm", "")
        text  = (d.get("full_text") or "")[:MAX_DART_CHARS]
        tail  = "…" if len(d.get("full_text") or "") > MAX_DART_CHARS else ""
        parts.append(f"▶ {dt}  [{kind}]  {nm}\n{text}{tail}")
    return "\n\n".join(parts)


# ── 국면 도출 ─────────────────────────────────────────────────────────

def _detect_regimes(ticker_code: str, start: str, end: str) -> list[dict]:
    df = fdr.DataReader(ticker_code, start, end)
    returns = df["Close"].pct_change().dropna()
    volume  = df["Volume"]

    dirs = returns.map(lambda x: "상승" if x > 0 else "하락")
    regimes, cur_dir = [], dirs.iloc[0]
    cur_start, cur_dates = dirs.index[0], [dirs.index[0]]
    for date, d in dirs.iloc[1:].items():
        if d == cur_dir:
            cur_dates.append(date)
        else:
            regimes.append({"direction": cur_dir, "start": cur_start,
                            "end": cur_dates[-1], "days": len(cur_dates),
                            "dates": cur_dates})
            cur_dir, cur_start, cur_dates = d, date, [date]
    regimes.append({"direction": cur_dir, "start": cur_start,
                    "end": cur_dates[-1], "days": len(cur_dates), "dates": cur_dates})

    # noise merge
    iqr = float(returns.quantile(0.75)) - float(returns.quantile(0.25))
    changed = True
    while changed:
        changed = False
        for i, reg in enumerate(regimes):
            if reg["days"] > 2:
                continue
            valid = [d for d in reg["dates"] if d in returns.index]
            cum = float((1 + returns.loc[valid]).prod() - 1) if valid else 0.0
            if abs(cum) >= iqr:
                continue
            n = len(regimes)
            if n == 1:
                break
            if i == 0:
                merged_dates = sorted(regimes[0]["dates"] + regimes[1]["dates"])
                merged = {**regimes[1], "start": merged_dates[0], "end": merged_dates[-1],
                          "days": len(merged_dates), "dates": merged_dates}
                regimes = [merged] + regimes[2:]
            elif i == n - 1:
                merged_dates = sorted(regimes[-2]["dates"] + regimes[-1]["dates"])
                merged = {**regimes[-2], "start": merged_dates[0], "end": merged_dates[-1],
                          "days": len(merged_dates), "dates": merged_dates}
                regimes = regimes[:-2] + [merged]
            else:
                merged_dates = sorted(regimes[i-1]["dates"] + reg["dates"] + regimes[i+1]["dates"])
                merged = {**regimes[i-1], "start": merged_dates[0], "end": merged_dates[-1],
                          "days": len(merged_dates), "dates": merged_dates}
                regimes = regimes[:i-1] + [merged] + regimes[i+2:]
            changed = True
            break

    def vol_trend(dates):
        valid = [d for d in dates if d in volume.index]
        if len(valid) < 3:
            return "혼조"
        v = volume.loc[valid].values.astype(float)
        slope, _, r_value, _, _ = stats.linregress(np.arange(len(v)), v)
        if abs(r_value) < 0.3:
            return "혼조"
        norm = slope / (v.mean() + 1e-9)
        return "증가" if norm > 0.005 else ("감소" if norm < -0.005 else "혼조")

    result = []
    for reg in regimes:
        valid = [d for d in reg["dates"] if d in returns.index]
        cum = float((1 + returns.loc[valid]).prod() - 1) if valid else 0.0
        result.append({
            "start":      reg["start"].strftime("%Y-%m-%d"),
            "end":        reg["end"].strftime("%Y-%m-%d"),
            "days":       reg["days"],
            "direction":  reg["direction"],
            "cum_return": round(cum, 6),
            "vol_trend":  vol_trend(reg["dates"]),
        })
    return result


def _load_regimes_from_summary(ticker_code: str) -> list[dict] | None:
    path = Path(f"data/{ticker_code}/regime_news_summary_{ticker_code}.json")
    if not path.exists():
        return None
    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "start":      r["start"],
            "end":        r["end"],
            "days":       r["days"],
            "direction":  r["direction"],
            "cum_return": r["cum_return"],
            "vol_trend":  r.get("vol_trend", "혼조"),
        }
        for r in records
    ]


# ── LLM 호출 ─────────────────────────────────────────────────────────

class DailyQuotaExceeded(Exception):
    pass


def _parse_openai_response(response) -> tuple[dict, int, int]:
    import re
    content = response.choices[0].message.content
    if not content:
        raise ValueError("응답 content 없음")
    text = content.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    s, e = text.find("{"), text.rfind("}") + 1
    if s == -1 or e == 0:
        raise ValueError(f"JSON 없음: {text[:120]}")
    return json.loads(text[s:e]), response.usage.prompt_tokens, response.usage.completion_tokens


def _call_groq(client, model, system, user):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return _parse_openai_response(resp)


def _call_openrouter(client, model, system, user):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        max_tokens=800,
    )
    return _parse_openai_response(resp)


def _call_gemini(client, model, system, user):
    from google.genai import types
    resp = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=800,
            response_mime_type="application/json",
        ),
        contents=user,
    )
    text = resp.text.strip() if resp.text else ""
    if not text:
        raise ValueError("Gemini 응답 비어 있음")
    s, e = text.find("{"), text.rfind("}") + 1
    if s == -1 or e == 0:
        raise ValueError(f"JSON 없음: {text[:120]}")
    meta = resp.usage_metadata
    return json.loads(text[s:e]), meta.prompt_token_count, meta.candidates_token_count


def _call_with_retry(provider, client, model, system, user, retries=3):
    import groq as groq_lib
    for attempt in range(retries):
        try:
            if provider == "groq":
                return _call_groq(client, model, system, user)
            elif provider == "openrouter":
                return _call_openrouter(client, model, system, user)
            else:
                return _call_gemini(client, model, system, user)
        except groq_lib.RateLimitError as e:
            msg = str(e).lower()
            if any(s in msg for s in ("daily", "per day", "day quota")):
                raise DailyQuotaExceeded(str(e))
            wait = 30 * (attempt + 1)
            log.info(f"  rate limit — {wait}초 대기")
            time.sleep(wait)
        except Exception as e:
            if "402" in str(e):
                raise DailyQuotaExceeded(f"크레딧 부족: {e}")
            if "429" in str(e) or "quota" in str(e).lower():
                if attempt < retries - 1:
                    wait = 60 * (attempt + 1)
                    log.info(f"  429/quota — {wait}초 대기")
                    time.sleep(wait)
                else:
                    raise DailyQuotaExceeded(str(e))
            elif attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                raise
    raise DailyQuotaExceeded("3회 연속 실패")


# ── 메인 ─────────────────────────────────────────────────────────────

def run(
    ticker_code: str,
    ticker_name: str,
    sector:      str,
    provider:    str = "groq",
    model:       str | None = None,
    start:       str = "2020-01-01",
    end:         str = "2026-05-28",
    dry_run:     bool = False,
    rerun_ids:   set[int] | None = None,
) -> None:
    rerun_ids = rerun_ids or set()
    model     = model or DEFAULT_MODEL[provider]
    sleep_sec = SLEEP_SEC[provider]

    dart_dir = _find_dart_dir(ticker_code)
    if dart_dir is None:
        log.error(f"data/dart/ 에서 {ticker_code} 디렉터리를 찾을 수 없습니다.")
        return
    log.info(f"DART 디렉터리: {dart_dir}")

    # 국면 로드 (뉴스 요약 결과 우선, 없으면 가격 데이터에서 도출)
    regimes = _load_regimes_from_summary(ticker_code)
    if regimes:
        log.info(f"국면 {len(regimes)}건 로드 (regime_news_summary)")
    else:
        log.info(f"가격 데이터에서 국면 도출: {ticker_code}  {start} ~ {end}")
        regimes = _detect_regimes(ticker_code, start, end)
        log.info(f"국면 {len(regimes)}건 도출")

    output_path = Path(f"data/{ticker_code}/regime_dart_summary_{ticker_code}.json")

    # 기존 결과 로드
    results: list[dict] = []
    if output_path.exists():
        try:
            results = json.loads(output_path.read_text(encoding="utf-8"))
            log.info(f"기존 결과 {len(results)}건 로드")
        except Exception:
            pass

    valid_done: set[str] = set()
    for r in results:
        key = r.get("regime_key", "")
        if not key:
            continue
        rid      = r.get("regime_id")
        analysis = r.get("llm_analysis", {})
        if REQUIRED_KEYS.issubset(analysis.keys()) and rid not in rerun_ids:
            valid_done.add(key)
        else:
            reason = "강제 재처리" if rid in rerun_ids else "필수 키 누락"
            log.info(f"  → [{rid}] {reason}, 재처리 대상")
            results = [x for x in results if x.get("regime_key") != key]

    done_keys = valid_done

    llm_client = None
    if not dry_run:
        if provider == "groq":
            import groq as groq_lib
            llm_client = groq_lib.Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        elif provider == "openrouter":
            from openai import OpenAI
            llm_client = OpenAI(api_key=os.getenv("GPT_API_KEY", ""),
                                base_url=OPENROUTER_BASE_URL)
        else:
            from google import genai
            llm_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

    total_in = total_out = 0

    for i, reg in enumerate(regimes, 1):
        regime_key = f"{reg['start']}_{reg['end']}"
        docs       = _load_dart_docs(dart_dir, reg["start"], reg["end"])
        dart_ctx   = _build_dart_context(docs)

        log.info(
            f"[{i:>3}/{len(regimes)}] {reg['start']}~{reg['end']} "
            f"({reg['days']:>2}일) {reg['direction']}  DART {len(docs)}건"
        )

        if dry_run:
            continue

        if regime_key in done_keys:
            log.info("  → 이미 완료, 스킵")
            continue

        user_prompt = _USER_TMPL.replace("{start}", reg["start"]) \
                                .replace("{end}",   reg["end"]) \
                                .replace("{days}",  str(reg["days"])) \
                                .replace("{name}",  ticker_name) \
                                .replace("{code}",  ticker_code) \
                                .replace("{sector}", sector) \
                                .replace("{dart_count}", str(len(docs))) \
                                .replace("{dart_context}", dart_ctx)

        try:
            answer, tok_in, tok_out = _call_with_retry(
                provider, llm_client, model, _SYSTEM, user_prompt
            )
        except DailyQuotaExceeded as e:
            log.error(f"일일 할당량 소진 — 중단: {e}")
            break
        except Exception as e:
            log.warning(f"  실패: {e}")
            continue

        missing = REQUIRED_KEYS - answer.keys()
        if missing:
            log.warning(f"  필수 키 누락 {missing} — 스킵")
            continue

        total_in  += tok_in
        total_out += tok_out
        log.info(f"  토큰 in={tok_in}  out={tok_out}  (누계 in={total_in} out={total_out})")

        results.append({
            "regime_id":   i,
            "regime_key":  regime_key,
            "ticker":      ticker_name,
            "ticker_code": ticker_code,
            "start":       reg["start"],
            "end":         reg["end"],
            "days":        reg["days"],
            "direction":   reg["direction"],
            "cum_return":  reg["cum_return"],
            "vol_trend":   reg["vol_trend"],
            "dart_count":  len(docs),
            "tokens_in":   tok_in,
            "tokens_out":  tok_out,
            "llm_analysis": answer,
        })
        done_keys.add(regime_key)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        time.sleep(sleep_sec)

    log.info(
        f"완료: {len(results)}건  "
        f"토큰 합계 in={total_in:,}  out={total_out:,}  → {output_path}"
    )


if __name__ == "__main__":
    # ── 종목 설정 ─────────────────────────────────────────────────────
    TICKER_MAP = {
        "005930": ("삼성전자",                "반도체"),
        "000660": ("SK하이닉스",              "반도체"),
        "005380": ("현대차",                  "자동차"),
        "079550": ("LIG디펜스앤에어로스페이스","방산"),
        "051910": ("LG화학",                  "화학"),
        "096770": ("SK이노베이션",            "에너지"),
        "000270": ("기아",                    "자동차"),
        "055550": ("신한지주",                "금융"),
        "105560": ("KB금융",                  "금융"),
        "012450": ("한화에어로스페이스",      "방산"),
    }

    parser = argparse.ArgumentParser(description="가격 국면별 DART 공시 LLM 요약")
    parser.add_argument("--ticker",   required=True, choices=list(TICKER_MAP), help="종목 코드")
    parser.add_argument("--provider", choices=["groq", "gemini", "openrouter"], default="groq")
    parser.add_argument("--model",    default=None)
    parser.add_argument("--start",    default="2020-01-01")
    parser.add_argument("--end",      default="2026-05-28")
    parser.add_argument("--dry-run",   action="store_true", help="LLM 호출 없이 공시 수집만 확인")
    parser.add_argument("--rerun-ids", nargs="+", type=int, default=[],
                        metavar="ID", help="강제 재처리 regime_id (예: --rerun-ids 3 7)")
    args = parser.parse_args()

    name, sector = TICKER_MAP[args.ticker]
    run(
        ticker_code = args.ticker,
        ticker_name = name,
        sector      = sector,
        provider    = args.provider,
        model       = args.model,
        start       = args.start,
        end         = args.end,
        dry_run     = args.dry_run,
        rerun_ids   = set(args.rerun_ids),
    )
