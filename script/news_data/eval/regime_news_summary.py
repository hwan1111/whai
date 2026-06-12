"""
가격 국면별 뉴스 LLM 요약

test3.py 에서 도출한 가격 국면을 입력으로 받아
각 구간의 뉴스를 LLM 으로 요약한다.

출력: data/regime_news_summary_{TICKER_CODE}.json

실행:
    python script/regime_news_summary.py
    python script/regime_news_summary.py --provider gemini
    python script/regime_news_summary.py --start 2020-01-01 --end 2026-05-12
    python script/regime_news_summary.py --dry-run
"""

import argparse
import json
import logging
import os
import time
from datetime import timedelta
from pathlib import Path

import boto3
import FinanceDataReader as fdr
import numpy as np
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from scipy import stats

load_dotenv(".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


START_DATE = "2020-01-01"
END_DATE   = "2026-05-28"

TICKER_MAP: dict[str, tuple[str, str]] = {
    "005930":   ("삼성전자",                  "반도체"),
    "000660":   ("SK하이닉스",                "반도체"),
    "005380":   ("현대차",                    "자동차"),
    "000270":   ("기아",                      "자동차"),
    "079550":   ("LIG디펜스앤에어로스페이스", "방산"),
    "051910":   ("LG화학",                    "화학"),
    "096770":   ("SK이노베이션",              "에너지"),
    "055550":   ("신한지주",                  "금융"),
    "105560":   ("KB금융",                    "금융"),
    "012450":   ("한화에어로스페이스",        "방산"),
    "KOSPI200": ("코스피200",                 "시장지수"),
    "USD_KRW":  ("원달러",                    "환율"),
}

# ticker_code와 FinanceDataReader 코드가 다른 경우
FDR_CODE_MAP: dict[str, str] = {
    "KOSPI200": "KS200",
    "USD_KRW":  "USD/KRW",
}

S3_BUCKET = "fisa-news-archive"
S3_PREFIX = "raw"

MAX_NEWS_CHARS  = 1_300
MAX_NEWS_COUNT  = 20   # 장기 구간 토큰 폭증 방지: 구간 내 최대 기사 수
NEWS_PRE        = 1   # 구간 시작 전 뉴스 탐색 캘린더일
NEWS_POST       = 1    # 구간 종료 후 뉴스 탐색 캘린더일

DEFAULT_MODEL = {
    "groq":       "llama-3.3-70b-versatile",
    "gemini":     "gemini-2.5-flash",
    "openrouter": "gpt-oss-120b:free"
}
SLEEP_SEC = {"groq": 40, "gemini": 10, "openrouter": 5}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DIR_STR = {"상승": "상승 ▲", "하락": "하락 ▼"}

_SYSTEM = """\
당신은 한국 주식시장 전문 애널리스트입니다.
주어진 주가 국면(기간, 방향, 거래량 추세)의 이동 원인을
뉴스를 종합해 분석합니다.
반드시 JSON 형식으로만 응답하세요. 설명 텍스트는 포함하지 마세요."""

_USER_TMPL = """\
{start} ~ {end} ({days}일간) {name}({code})의 주가가 {dir_str} {cum_ret:+.1%} 이동했습니다.

■ 구간 요약
  · 방향: {direction}  누적 수익률: {cum_ret:+.2%}
  · 거래량 추세: {vol_trend}  (구간 {days}일)
  · 섹터: {sector}

■ 뉴스 (구간 시작 {news_pre}일 전 ~ 종료 {news_post}일 후, 최대 {max_news_count}건)
{news_context}

■ 작성 규칙
  · evidence 의 quote 는 위 뉴스 원문에서 근거가 되는 핵심 구절만 직접 인용하세요 (전후 맥락 포함 최대 80자).
  · 수치(숫자+단위)는 원문에서 글자 그대로 복사하세요. 단위 환산·요약 절대 금지입니다.
    예) 원문 "8,500억원" → quote에 반드시 "8,500억원"  (→ "8.5조원"으로 환산 금지)
    예) 원문 "3.7%" → quote에 반드시 "3.7%"  (→ "약 4%" 등으로 변경 금지)
  · 원문에 없는 수치는 작성 금지입니다.
  · 뉴스가 없는 경우 evidence 는 빈 배열 [] 로 두세요.

위 정보를 바탕으로 이 구간의 주가 이동 원인을 분석하고 아래 JSON 으로만 응답하세요:
{{
  "cause":       "주요 원인 한 줄 (100자 이내)",
  "evidence":    [
    {{"date": "YYYY-MM-DD", "quote": "원문 핵심 구절 직접 인용 (최대 40자)", "point": "이 구절이 가격 변동과 연결되는 이유 (50자 이내)"}},
    {{"date": "YYYY-MM-DD", "quote": "원문 핵심 구절 직접 인용 (최대 40자)", "point": "이 구절 선정 이유(50자 이내)"}},
  ],
  "vol_insight": "거래량 추세가 시사하는 수급 특성 (50자 이내)",
  "confidence":  "high|medium|low",
  "reasoning":   "판단 근거 (200자 이내)"
}}"""


# ── 국면 탐지 (test3.py 핵심 로직 인라인) ────────────────────────────

def _fetch_price_volume(code: str, start: str, end: str) -> tuple[pd.Series, pd.Series]:
    df = fdr.DataReader(code, start, end)
    return df["Close"].pct_change().dropna(), df["Volume"]


def _detect_price_regimes(returns: pd.Series) -> list[dict]:
    s = returns.dropna()
    dirs = s.map(lambda x: "상승" if x > 0 else "하락")
    regimes, cur_dir, cur_start, cur_dates = [], dirs.iloc[0], dirs.index[0], [dirs.index[0]]
    for date, d in dirs.iloc[1:].items():
        if d == cur_dir:
            cur_dates.append(date)
        else:
            regimes.append({"direction": cur_dir, "start": cur_start,
                            "end": cur_dates[-1], "days": len(cur_dates), "dates": cur_dates})
            cur_dir, cur_start, cur_dates = d, date, [date]
    regimes.append({"direction": cur_dir, "start": cur_start,
                    "end": cur_dates[-1], "days": len(cur_dates), "dates": cur_dates})
    return regimes


def _cum_return(returns: pd.Series, dates: list) -> float:
    valid = [d for d in dates if d in returns.index]
    return float((1 + returns.loc[valid]).prod() - 1) if valid else 0.0


def _merge_noise(regimes: list[dict], returns: pd.Series) -> list[dict]:
    r = returns.dropna()
    iqr = float(r.quantile(0.75)) - float(r.quantile(0.25))
    result = [{**reg, "dates": list(reg["dates"])} for reg in regimes]
    changed = True
    while changed:
        changed = False
        for i, reg in enumerate(result):
            if reg["days"] > 2:
                continue
            if abs(_cum_return(returns, reg["dates"])) >= iqr:
                continue
            n = len(result)
            if n == 1:
                break
            if i == 0:
                dates = sorted(result[0]["dates"] + result[1]["dates"])
                merged = {**result[1], "start": dates[0], "end": dates[-1],
                          "days": len(dates), "dates": dates}
                result = [merged] + result[2:]
            elif i == n - 1:
                dates = sorted(result[-2]["dates"] + result[-1]["dates"])
                merged = {**result[-2], "start": dates[0], "end": dates[-1],
                          "days": len(dates), "dates": dates}
                result = result[:-2] + [merged]
            else:
                dates = sorted(result[i-1]["dates"] + reg["dates"] + result[i+1]["dates"])
                merged = {**result[i-1], "start": dates[0], "end": dates[-1],
                          "days": len(dates), "dates": dates}
                result = result[:i-1] + [merged] + result[i+2:]
            changed = True
            break
    return result


def _vol_trend(volume: pd.Series, dates: list,
               slope_thr: float = 0.005, min_r: float = 0.3) -> str:
    valid = [d for d in dates if d in volume.index]
    if len(valid) < 3:
        return "혼조"
    v = volume.loc[valid].values.astype(float)
    slope, _, r_value, _, _ = stats.linregress(np.arange(len(v)), v)
    if abs(r_value) < min_r:
        return "혼조"
    norm = slope / (v.mean() + 1e-9)
    if norm > slope_thr:
        return "증가"
    if norm < -slope_thr:
        return "감소"
    return "혼조"


# ── S3 뉴스 수집 ──────────────────────────────────────────────────────

def _fetch_regime_news(s3_client, ticker_code: str,
                       start: pd.Timestamp, end: pd.Timestamp,
                       pre_days: int, post_days: int) -> list[dict]:
    articles = []
    cur = start - timedelta(days=pre_days)
    fin = end   + timedelta(days=post_days)
    seen: set[str] = set()
    while cur <= fin:
        key = f"{S3_PREFIX}/{ticker_code}/{cur.year}/{cur.month:02d}/{cur.strftime('%Y-%m-%d')}.json"
        try:
            obj  = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
            data = json.loads(obj["Body"].read().decode("utf-8"))
            uid  = f"{data.get('pub_date','')}|{data.get('title','')}"
            if uid not in seen:
                seen.add(uid)
                articles.append(data)
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                log.warning(f"  S3 오류 {key}: {e}")
        except Exception as e:
            log.warning(f"  S3 fetch 실패 {key}: {e}")
        cur += timedelta(days=1)
    return articles


def _build_news_context(articles: list[dict]) -> str:
    if not articles:
        return "(해당 기간 뉴스 없음)"
    sorted_articles = sorted(articles, key=lambda x: x.get("pub_date", ""))[:MAX_NEWS_COUNT]
    parts = []
    for a in sorted_articles:
        fulltext = a.get("fulltext") or ""
        body = fulltext[:MAX_NEWS_CHARS] + ("…" if len(fulltext) > MAX_NEWS_CHARS else "")
        parts.append(f"▶ {a.get('pub_date','')}  {a.get('title','')}\n{body}")
    return "\n\n".join(parts)


# ── LLM 호출 ─────────────────────────────────────────────────────────

class DailyQuotaExceeded(Exception):
    pass


def _parse_openai_response(response) -> tuple[dict, int, int]:
    """Groq / OpenRouter 공통 응답 파싱."""
    import re
    content = response.choices[0].message.content
    if not content:
        raise ValueError("응답 content가 None 또는 빈 문자열")
    text = content.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    s, e = text.find("{"), text.rfind("}") + 1
    if s == -1 or e == 0:
        raise ValueError(f"JSON 없음: {text[:120]}")
    return json.loads(text[s:e]), response.usage.prompt_tokens, response.usage.completion_tokens


def _call_groq(client, model: str, system: str, user: str) -> tuple[dict, int, int]:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    return _parse_openai_response(response)


def _call_openrouter(client, model: str, system: str, user: str) -> tuple[dict, int, int]:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        max_tokens=1200,
    )
    return _parse_openai_response(response)


def _call_gemini(client, model: str, system: str, user: str) -> tuple[dict, int, int]:
    from google.genai import types
    response = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=800,
            response_mime_type="application/json",
        ),
        contents=user,
    )
    text = response.text.strip() if response.text else ""
    if not text:
        raise ValueError("Gemini 응답 text가 비어 있음")
    s, e = text.find("{"), text.rfind("}") + 1
    if s == -1 or e == 0:
        raise ValueError(f"JSON 없음: {text[:120]}")
    meta = response.usage_metadata
    return json.loads(text[s:e]), meta.prompt_token_count, meta.candidates_token_count


def _call_with_retry(provider: str, client, model: str,
                     system: str, user: str,
                     retries: int = 3) -> tuple[dict, int, int]:
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
                raise DailyQuotaExceeded(f"크레딧 부족 (402): {e}")
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

def run(ticker_code: str,
        ticker_name: str,
        sector:      str,
        provider:    str = "groq",
        model:       str | None = None,
        start:       str = START_DATE,
        end:         str = END_DATE,
        dry_run:     bool = False,
        rerun_ids:   set[int] | None = None) -> None:
    rerun_ids   = rerun_ids or set()
    model       = model or DEFAULT_MODEL[provider]
    sleep_sec   = SLEEP_SEC[provider]
    output_path = Path(f"data/{ticker_code}/regime_news_summary_{ticker_code}.json")

    llm_client = None
    if not dry_run:
        if provider == "groq":
            import groq as groq_lib
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise EnvironmentError(".env에 GROQ_API_KEY 없음")
            llm_client = groq_lib.Groq(api_key=api_key)
        elif provider == "openrouter":
            from openai import OpenAI
            api_key = os.getenv("GPT_API_KEY", "")
            if not api_key:
                raise EnvironmentError(".env에 GPT_API_KEY 없음")
            llm_client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        else:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                raise EnvironmentError(".env에 GEMINI_API_KEY 없음")
            llm_client = genai.Client(api_key=api_key)

    s3_client = boto3.client("s3")

    # ── 국면 도출 ─────────────────────────────────────────────────────
    log.info(f"가격 데이터 수집: {ticker_name}({ticker_code})  {start} ~ {end}")
    fdr_code = FDR_CODE_MAP.get(ticker_code, ticker_code)
    returns, volume = _fetch_price_volume(fdr_code, start, end)
    raw_regimes     = _detect_price_regimes(returns)
    regimes         = _merge_noise(raw_regimes, returns)
    log.info(f"국면: {len(raw_regimes)}개 → 병합 후 {len(regimes)}개")

    # ── 기존 결과 로드 ────────────────────────────────────────────────
    results: list[dict] = []
    if output_path.exists():
        try:
            results = json.loads(output_path.read_text(encoding="utf-8"))
            log.info(f"기존 결과 {len(results)}건 로드")
        except Exception:
            pass
    else:
        # 로컬 파일 없으면 S3 백업에서 복구 (upload 후 삭제된 경우)
        try:
            s3_key = f"processed/{ticker_code}/regime_news_summary_{ticker_code}.json"
            obj = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            results = json.loads(obj["Body"].read().decode("utf-8"))
            log.info(f"S3 백업에서 기존 결과 {len(results)}건 복구: {s3_key}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except ClientError:
            pass

    REQUIRED_KEYS = {"cause", "evidence", "vol_insight", "confidence", "reasoning"}

    valid_done: set[str] = set()
    for r in results:
        key = r.get("regime_key", "")
        if not key:
            continue
        rid      = r.get("regime_id")
        analysis = r.get("llm_analysis", {})
        is_valid = REQUIRED_KEYS.issubset(analysis.keys())
        if is_valid and rid not in rerun_ids:
            valid_done.add(key)
        else:
            reason = "강제 재처리" if rid in rerun_ids else "필수 키 누락"
            log.info(f"  → [{rid}] {reason}, 재처리 대상으로 분류")
            results = [x for x in results if x.get("regime_key") != key]

    done_keys: set[str] = valid_done
    total_in = total_out = 0

    # ── 국면 순회 ─────────────────────────────────────────────────────
    for i, reg in enumerate(regimes, 1):
        regime_key = f"{reg['start'].strftime('%Y-%m-%d')}_{reg['end'].strftime('%Y-%m-%d')}"
        start_str  = reg["start"].strftime("%Y-%m-%d")
        end_str    = reg["end"].strftime("%Y-%m-%d")
        cum_ret    = _cum_return(returns, reg["dates"])
        vol_trend  = _vol_trend(volume, reg["dates"])
        dir_str    = DIR_STR.get(reg["direction"], reg["direction"])

        news_articles = _fetch_regime_news(s3_client, ticker_code,
                                           reg["start"], reg["end"],
                                           NEWS_PRE, NEWS_POST)

        log.info(
            f"[{i:>2}/{len(regimes)}] {start_str}~{end_str} ({reg['days']:>2}일) "
            f"{dir_str} {cum_ret:+.1%}  거래량:{vol_trend}  뉴스 {len(news_articles)}건"
        )

        if dry_run:
            continue

        if regime_key in done_keys:
            log.info(f"  → 이미 완료, 스킵")
            continue

        news_context = _build_news_context(news_articles)

        user_prompt = _USER_TMPL.format(
            start=start_str, end=end_str, days=reg["days"],
            name=ticker_name, code=ticker_code,
            dir_str=dir_str, cum_ret=cum_ret,
            direction=reg["direction"], vol_trend=vol_trend,
            sector=sector,
            news_pre=NEWS_PRE, news_post=NEWS_POST,
            max_news_count=MAX_NEWS_COUNT,
            news_context=news_context,
        )

        try:
            answer, tok_in, tok_out = _call_with_retry(
                provider, llm_client, model, _SYSTEM, user_prompt
            )
        except DailyQuotaExceeded as e:
            log.error(f"일일 할당량 소진 — 중단\n  원인: {e}")
            break
        except Exception as e:
            log.warning(f"  실패: {e}")
            continue

        missing = REQUIRED_KEYS - answer.keys()
        if missing:
            log.warning(f"  필수 키 누락 {missing} — 저장 건너뜀 (재실행 시 --rerun-ids {i})")
            continue

        total_in  += tok_in
        total_out += tok_out
        log.info(f"  토큰 in={tok_in}  out={tok_out}  (누계 in={total_in} out={total_out})")

        results.append({
            "regime_id":    i,
            "regime_key":   regime_key,
            "ticker":       ticker_name,
            "ticker_code":  ticker_code,
            "start":        start_str,
            "end":          end_str,
            "days":         reg["days"],
            "direction":    reg["direction"],
            "cum_return":   round(cum_ret, 6),
            "vol_trend":    vol_trend,
            "news_count":   len(news_articles),
            "tokens_in":    tok_in,
            "tokens_out":   tok_out,
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
    parser = argparse.ArgumentParser(description="가격 국면별 뉴스 LLM 요약")
    parser.add_argument("--ticker",    required=True, choices=list(TICKER_MAP),
                        help="종목 코드 (예: 005930)")
    parser.add_argument("--provider",  choices=["groq", "gemini", "openrouter"], default="groq")
    parser.add_argument("--model",     default=None)
    parser.add_argument("--start",     default=START_DATE)
    parser.add_argument("--end",       default=END_DATE)
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--rerun-ids", nargs="+", type=int, default=[],
                        metavar="ID", help="강제 재처리할 regime_id (예: --rerun-ids 21 22)")
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
