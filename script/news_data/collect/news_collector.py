"""
script/news_collector.py
뉴스 수집기 - 멀티 프로바이더 폴백 지원

수집 순서: 네이버 → 구글 → 다음
각 프로바이더가 403이면 자동으로 다음 프로바이더로 전환
"""

import re
import json
import time
import random
import logging
import requests
from datetime import date, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR  = BASE_DIR / "data" / "news"
LOG_PATH  = BASE_DIR / "data" / "news_collect.log"

START_DATE = date(2020, 1, 1)
END_DATE   = date.today()

REQUEST_DELAY_MIN     = 2.0
REQUEST_DELAY_MAX     = 4.0
CONSECUTIVE_403_LIMIT = 5      # 프로바이더당 연속 403 허용 횟수
COOLDOWN_SECONDS      = 600    # 전체 프로바이더 차단 시 대기(10분)

# ─────────────────────────────────────────────
# User-Agent 풀 (랜덤 선택으로 봇 감지 회피)
# ─────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def _get_headers(referer: str = "https://www.naver.com/") -> dict:
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer":         referer,
    }

# ─────────────────────────────────────────────
# 수집 대상 (주식 10개 + USD/KRW)
# 반도체 / 자동차 / 방산 / 금융 / 화학 / 환율
# ─────────────────────────────────────────────
STOCKS = [
    # 반도체
    ("삼성전자",            "005930"),
    ("SK하이닉스",          "000660"),
    # 자동차
    ("현대차",             "005380"),
    ("기아",               "000270"),
    # 방산
    ("LIG디펜스앤에어로스페이스", "079550"),
    ("한화에어로스페이스",     "012450"),
    # 금융
    ("KB금융",             "105560"),
    ("신한지주",            "055550"),
    # 화학
    ("LG화학",             "051910"),
    ("SK이노베이션",         "096770"),
    # 환율
    ("원달러환율",           "USD_KRW"),
]

# ─────────────────────────────────────────────
# 사명 변경 이력 (날짜 이전엔 구 이름으로 검색)
# ─────────────────────────────────────────────
NAME_ALIASES: dict[str, list[tuple]] = {
    # LIG넥스원 → LIG디펜스앤에어로스페이스 (2026-03-31 사명 변경)
    "LIG디펜스앤에어로스페이스": [
        (date(2026, 3, 31), "LIG넥스원"),
    ],
    "원달러환율": [
        (date.max, "원 달러 환율"),
        (date.max, "원·달러 환율"),
    ],
}

def get_search_names(company_name: str, target_date: date) -> list[str]:
    """사명 변경 이력을 반영한 검색어 목록 반환 (우선순위 순)
    - 1순위: 해당 날짜의 구 사명
    - 마지막: 현재 사명 (폴백)
    """
    names = []
    for change_date, old_name in NAME_ALIASES.get(company_name, []):
        if target_date < change_date:
            names.append(old_name)
    if company_name not in names:
        names.append(company_name)  # 현재 사명을 항상 마지막에 폴백으로 추가
    return names


# ─────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 검색 프로바이더
# ─────────────────────────────────────────────

def search_naver(company_name: str, target_date: date) -> dict | str | None:
    """
    네이버 뉴스 검색 페이지 크롤링
    - 사명 변경 이력을 반영하여 구 사명부터 시도
    - BLOCKED 시 즉시 반환 (다른 이름으로도 IP 차단은 해결안 됨)
    - 결과없음(None) 시만 다음 사명으로 폴백
    반환: dict(기사정보) | "BLOCKED"(403) | None(결과없음)
    """
    search_names = get_search_names(company_name, target_date)
    date_str = target_date.strftime("%Y%m%d")

    for search_name in search_names:
        query = f"{search_name} 주가"
        url = (
            "https://search.naver.com/search.naver"
            f"?where=news&query={requests.utils.quote(query)}"
            f"&nso=so:sim,p:from{date_str}to{date_str}&start=1"
        )
        try:
            resp = requests.get(url, headers=_get_headers("https://www.naver.com/"), timeout=10)
            resp.raise_for_status()
            result = _parse_naver_result(resp.text, target_date)
            if result is not None:
                if search_name != company_name:
                    logger.info(f"  [{search_name}] 이름으로 수집")
                return result  # 결과 있으면 바로 반환
            # 결과없으면 다음 사명으로 시도
            logger.info(f"  [{search_name}] 결과없음 → 다음 이름 시도")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                logger.warning(f"[NAVER 403] {company_name} {target_date}")
                return "BLOCKED"  # IP 차단 → 이름 바꿔도 소용없음
            logger.warning(f"[NAVER ERR] {company_name} {target_date}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[NAVER ERR] {company_name} {target_date}: {e}")
            return None

    return None  # 모든 이름 시도했는데 결과 없음


def _parse_naver_result(html: str, target_date: date) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    for mark in soup.find_all("mark"):
        parent     = mark.parent
        title_text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))
        container  = parent
        for _ in range(8):
            if not container:
                break
            for a in container.find_all("a", href=True):
                href = a["href"]
                if "n.news.naver.com" in href and href not in seen:
                    seen.add(href)
                    return {"title": title_text, "link": href, "pub_date": target_date.isoformat(), "source": "naver"}
            container = container.parent
    return None


def search_daum(company_name: str, target_date: date) -> dict | str | None:
    """
    다음 뉴스 검색 페이지 크롤링
    반환: dict | "BLOCKED" | None
    """
    date_str = target_date.strftime("%Y%m%d")
    query    = f"{company_name} 주가"
    url = (
        "https://search.daum.net/search"
        f"?w=news&q={requests.utils.quote(query)}"
        f"&period=d&date={date_str}&sort=accuracy"
    )
    try:
        resp = requests.get(url, headers=_get_headers("https://www.daum.net/"), timeout=10)
        resp.raise_for_status()
        return _parse_daum_result(resp.text, target_date)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            logger.warning(f"[DAUM 403] {company_name} {target_date}")
            return "BLOCKED"
        logger.warning(f"[DAUM ERR] {company_name} {target_date}: {e}")
        return None
    except Exception as e:
        logger.warning(f"[DAUM ERR] {company_name} {target_date}: {e}")
        return None


def _parse_daum_result(html: str, target_date: date) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    # 다음 뉴스 검색 결과 구조
    for sel in ["a.tit-g", "a.fn-tit", ".item-title a", ".news-item a", "a[href*='news']"]:
        tags = soup.select(sel)
        for a in tags:
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if href and title and len(title) > 5:
                return {"title": title, "link": href, "pub_date": target_date.isoformat(), "source": "daum"}
    return None


def search_google(company_name: str, target_date: date) -> dict | str | None:
    """
    구글 뉴스 검색 크롤링
    반환: dict | "BLOCKED" | None
    """
    d = target_date
    query    = f"{company_name} 주가"
    date_min = f"{d.month}/{d.day}/{d.year}"
    url = (
        "https://www.google.com/search"
        f"?q={requests.utils.quote(query)}&tbm=nws"
        f"&tbs=cdr:1,cd_min:{date_min},cd_max:{date_min}"
        "&hl=ko&gl=kr&num=1"
    )
    try:
        resp = requests.get(url, headers=_get_headers("https://www.google.com/"), timeout=10)
        resp.raise_for_status()
        return _parse_google_result(resp.text, target_date)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code in (403, 429):
            logger.warning(f"[GOOGLE 403] {company_name} {target_date}")
            return "BLOCKED"
        logger.warning(f"[GOOGLE ERR] {company_name} {target_date}: {e}")
        return None
    except Exception as e:
        logger.warning(f"[GOOGLE ERR] {company_name} {target_date}: {e}")
        return None


def _parse_google_result(html: str, target_date: date) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    # 구글 뉴스 결과 구조
    for sel in ["div.SoaBEf a", "a.WlydOe", "div.dbsr a", "h3 > a", "a[data-ved]"]:
        for a in soup.select(sel):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            # 구글 리다이렉트 URL 정리
            if href.startswith("/url?q="):
                href = href.split("/url?q=")[1].split("&")[0]
            if href and title and len(title) > 5 and href.startswith("http"):
                return {"title": title, "link": href, "pub_date": target_date.isoformat(), "source": "google"}
    return None


# ─────────────────────────────────────────────
# 폴백 검색 (Naver → Daum → Google)
# ─────────────────────────────────────────────

PROVIDERS = [
    ("naver",  search_naver),
    ("google", search_google),  # 네이버 차단 시 폴백
]

def search_with_fallback(company_name: str, target_date: date) -> dict | str | None:
    """
    프로바이더 순서대로 시도.
    - BLOCKED(403): 다음 프로바이더로 전환
    - None(결과없음): 해당 날짜 기사 없음으로 처리 → 폴백 안 함
    - dict: 성공
    - "ALL_BLOCKED": 모든 프로바이더가 차단됨 → 쿨다운 카운트
    """
    all_blocked = True  # 모든 프로바이더가 BLOCKED인지 추적

    for provider_name, provider_fn in PROVIDERS:
        result = provider_fn(company_name, target_date)

        if result == "BLOCKED":
            logger.info(f"  [{provider_name.upper()} 차단] → 다음 프로바이더 시도...")
            time.sleep(random.uniform(2.0, 3.0))
            continue

        # None(결과없음) 또는 dict(성공) → 차단이 아님
        all_blocked = False
        return result

    if all_blocked:
        return "ALL_BLOCKED"  # 네이버 + 구글 모두 차단
    return None  # 전체 프로바이더 차단 시



# ─────────────────────────────────────────────
# 전문 크롤링
# ─────────────────────────────────────────────

def fetch_fulltext(link: str) -> str | None:
    """URL에 따라 네이버 뉴스 파서 또는 범용 파서 사용"""
    if not link:
        return None
    if "n.news.naver.com" in link:
        return _fetch_naver_fulltext(link)
    return _fetch_generic_fulltext(link)


def _fetch_naver_fulltext(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=_get_headers("https://news.naver.com/"), timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for sel in ["#dic_area", "#articeBody", ".newsct_article", "#content"]:
            tag = soup.select_one(sel)
            if tag:
                return _clean_text(tag.get_text(separator="\n"))
        return None
    except Exception as e:
        logger.warning(f"[전문 실패-naver] {url}: {e}")
        return None


def _fetch_generic_fulltext(url: str) -> str | None:
    """네이버 외 일반 언론사 기사 전문 크롤링"""
    try:
        resp = requests.get(url, headers=_get_headers(url), timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # 불필요한 태그 제거
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()
        # 본문 선택자 순서대로 시도
        for sel in [
            "article",
            "[class*='article-body']", "[class*='article_body']",
            "[class*='news-content']", "[class*='news_content']",
            "[id*='article']", "[id*='content']",
            ".article", ".content", "main",
        ]:
            tag = soup.select_one(sel)
            if tag:
                text = _clean_text(tag.get_text(separator="\n"))
                if len(text) > 200:  # 너무 짧으면 본문 아닐 가능성
                    return text
        return None
    except Exception as e:
        logger.warning(f"[전문 실패-generic] {url}: {e}")
        return None


def _clean_text(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 저장
# ─────────────────────────────────────────────

def save_article(company_name: str, ticker: str, article: dict, fulltext: str | None) -> Path:
    folder = DATA_DIR / f"{company_name}_{ticker}"
    folder.mkdir(parents=True, exist_ok=True)
    filepath = folder / f"{article['pub_date']}.json"
    doc = {
        "pub_date":     article["pub_date"],
        "ticker":       ticker,
        "company_name": company_name,
        "title":        article["title"],
        "fulltext":     fulltext,
        "link":         article["link"],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return filepath


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


# ─────────────────────────────────────────────
# 메인 수집 루프
# ─────────────────────────────────────────────

def collect_all(start: date | None = None, end: date | None = None) -> None:
    start = start or START_DATE
    end   = end   or END_DATE
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total_stocks = len(STOCKS)
    total_days   = (end - start).days + 1
    logger.info(f"수집 시작: {start} ~ {end} ({total_days}일) × {total_stocks}종목")
    provider_order = " → ".join(name.upper() for name, _ in PROVIDERS)
    logger.info(f"프로바이더 순서: {provider_order}")

    for stock_idx, (company_name, ticker) in enumerate(STOCKS, 1):
        logger.info(f"[{stock_idx}/{total_stocks}] {company_name} ({ticker})")

        collected        = 0
        skipped          = 0
        consecutive_block = 0  # 연속 전체차단일 카운터

        for target_date in date_range(start, end):
            filepath = DATA_DIR / f"{company_name}_{ticker}" / f"{target_date.isoformat()}.json"

            # 이미 수집된 날짜 스킵
            if filepath.exists():
                skipped += 1
                consecutive_block = 0
                continue

            # 폴백 검색
            article = search_with_fallback(company_name, target_date)

            if article == "ALL_BLOCKED":
                # 네이버 + 구글 둘 다 차단
                skipped += 1
                consecutive_block += 1
                logger.warning(f"  ⛔ 전체차단 [{consecutive_block}일째] {target_date}")
                if consecutive_block >= CONSECUTIVE_403_LIMIT:
                    logger.warning(
                        f"  ⛔ {consecutive_block}일 연속 전체차단 → "
                        f"{COOLDOWN_SECONDS//60}분 쿨다운 시작"
                    )
                    time.sleep(COOLDOWN_SECONDS)
                    consecutive_block = 0
                else:
                    time.sleep(random.uniform(3.0, 5.0))
                continue

            if not article:
                # 결과 없음 (차단이 아님)
                skipped += 1
                consecutive_block = 0
                time.sleep(random.uniform(0.5, 1.0))
                continue

            consecutive_block = 0

            # 전문 크롤링
            fulltext = fetch_fulltext(article["link"])

            # 저장
            save_article(company_name, ticker, article, fulltext)
            collected += 1

            src_tag = f"[{article.get('source', '?').upper()}]"
            logger.info(
                f"  저장 {src_tag}: {target_date} | {article['title'][:40]}..."
                + (" [전문X]" if not fulltext else "")
            )

            time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

        logger.info(f"  → {company_name} 완료: 수집 {collected}건 / 스킵 {skipped}건")

    logger.info("전체 수집 완료!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="뉴스 수집기")
    parser.add_argument("--start", default=None, help="수집 시작일 YYYY-MM-DD (기본: 2020-01-01)")
    parser.add_argument("--end",   default=None, help="수집 종료일 YYYY-MM-DD (기본: 오늘)")
    args = parser.parse_args()
    collect_all(
        start=date.fromisoformat(args.start) if args.start else None,
        end=date.fromisoformat(args.end)     if args.end   else None,
    )
