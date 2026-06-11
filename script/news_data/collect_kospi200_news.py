"""
script/collect_kospi200_news.py
코스피 200 뉴스 수집기 - 멀티 프로바이더 폴백 지원

수집 순서: 네이버 → 구글
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
BASE_DIR  = Path(__file__).resolve().parent.parent.parent
DATA_DIR  = BASE_DIR / "data" / "news"
LOG_PATH  = BASE_DIR / "data" / "kospi200_news_collect.log"

START_DATE = date(2020, 1, 1)
END_DATE   = date.today() - timedelta(days=1)  # 자정 기준 전일까지

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
# 수집 대상 (코스피 200 단일 키워드)
# ─────────────────────────────────────────────
STOCKS = [
    ("코스피200", "KOSPI200")
]

# 사명 변경이나 별칭 이력 (동일하게 사용하기 위한 구조 매칭)
NAME_ALIASES: dict[str, list[tuple]] = {
    "코스피200": [
        (date(2030, 1, 1), "코스피 200"), # 공백 포함 패턴도 시도하도록 설정
    ],
}

def get_search_names(company_name: str, target_date: date) -> list[str]:
    """사명 변경/별칭 이력을 반영한 검색어 목록 반환 (우선순위 순)"""
    names = []
    for change_date, old_name in NAME_ALIASES.get(company_name, []):
        if target_date < change_date:
            names.append(old_name)
    if company_name not in names:
        names.append(company_name)
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
    """
    search_names = get_search_names(company_name, target_date)
    date_str = target_date.strftime("%Y%m%d")

    for search_name in search_names:
        query = search_name  # "코스피 200" 또는 "코스피200" 직접 검색
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
                return result
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                logger.warning(f"[NAVER 403] {company_name} {target_date}")
                return "BLOCKED"
            logger.warning(f"[NAVER ERR] {company_name} {target_date}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[NAVER ERR] {company_name} {target_date}: {e}")
            return None

    return None


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


def search_google(company_name: str, target_date: date) -> dict | str | None:
    """
    구글 뉴스 검색 크롤링
    """
    d = target_date
    query    = company_name
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
    for sel in ["div.SoaBEf a", "a.WlydOe", "div.dbsr a", "h3 > a", "a[data-ved]"]:
        for a in soup.select(sel):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if href.startswith("/url?q="):
                href = href.split("/url?q=")[1].split("&")[0]
            if href and title and len(title) > 5 and href.startswith("http"):
                return {"title": title, "link": href, "pub_date": target_date.isoformat(), "source": "google"}
    return None


# ─────────────────────────────────────────────
# 폴백 검색 (Naver → Google)
# ─────────────────────────────────────────────

PROVIDERS = [
    ("naver",  search_naver),
    ("google", search_google),
]

def search_with_fallback(company_name: str, target_date: date) -> dict | str | None:
    all_blocked = True

    for provider_name, provider_fn in PROVIDERS:
        result = provider_fn(company_name, target_date)

        if result == "BLOCKED":
            logger.info(f"  [{provider_name.upper()} 차단] → 다음 프로바이더 시도...")
            time.sleep(random.uniform(2.0, 3.0))
            continue

        all_blocked = False
        return result

    if all_blocked:
        return "ALL_BLOCKED"
    return None


# ─────────────────────────────────────────────
# 전문 크롤링
# ─────────────────────────────────────────────

def fetch_fulltext(link: str) -> str | None:
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
    try:
        resp = requests.get(url, headers=_get_headers(url), timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()
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
                if len(text) > 200:
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

def collect_all():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total_stocks = len(STOCKS)
    total_days   = (END_DATE - START_DATE).days + 1
    logger.info(f"KOSPI200 수집 시작: {START_DATE} ~ {END_DATE} ({total_days}일) × {total_stocks}종목")
    provider_order = " → ".join(name.upper() for name, _ in PROVIDERS)
    logger.info(f"프로바이더 순서: {provider_order}")

    for stock_idx, (company_name, ticker) in enumerate(STOCKS, 1):
        logger.info(f"[{stock_idx}/{total_stocks}] {company_name} ({ticker})")

        collected        = 0
        skipped          = 0
        consecutive_block = 0

        for target_date in date_range(START_DATE, END_DATE):
            filepath = DATA_DIR / f"{company_name}_{ticker}" / f"{target_date.isoformat()}.json"

            if filepath.exists():
                skipped += 1
                consecutive_block = 0
                continue

            article = search_with_fallback(company_name, target_date)

            if article == "ALL_BLOCKED":
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
                skipped += 1
                consecutive_block = 0
                time.sleep(random.uniform(0.5, 1.0))
                continue

            consecutive_block = 0
            fulltext = fetch_fulltext(article["link"])
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
    parser = argparse.ArgumentParser(description="KOSPI200 뉴스 수집")
    parser.add_argument("--start", default=None, help="수집 시작일 YYYY-MM-DD (기본: 2020-01-01)")
    parser.add_argument("--end",   default=None, help="수집 종료일 YYYY-MM-DD (기본: 전일)")
    args = parser.parse_args()
    if args.start:
        START_DATE = date.fromisoformat(args.start)
    if args.end:
        END_DATE = date.fromisoformat(args.end)
    collect_all()
