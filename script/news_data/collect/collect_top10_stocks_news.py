"""
script/collect_top10_stocks_news.py
대표 10개 종목 뉴스 수집기 (Requests + Playwright 통합 버전)

수집 순서: 
- 1단계 (Requests): Naver → Google 고속 크롤링
- 2단계 (Playwright): 크롤링 실패 및 차단으로 누락된 날짜에 대해 Chrome 브라우저 기반 우회 보완 수집
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
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR  = BASE_DIR / "data" / "news"
LOG_PATH  = BASE_DIR / "data" / "collect_top10_stocks.log"

START_DATE = date(2020, 1, 1)
END_DATE   = date.today()

REQUEST_DELAY_MIN     = 2.0
REQUEST_DELAY_MAX     = 4.0
CONSECUTIVE_403_LIMIT = 5      # 프로바이더당 연속 403 허용 횟수
COOLDOWN_SECONDS      = 600    # 전체 프로바이더 차단 시 대기(10분)

# Playwright 보완 수집 설정
PW_DELAY_MIN = 2.5
PW_DELAY_MAX = 5.0

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
# 수집 대상 종목 (10개)
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
]

# ─────────────────────────────────────────────
# 사명 변경 이력
# ─────────────────────────────────────────────
NAME_ALIASES: dict[str, list[tuple]] = {
    "LIG디펜스앤에어로스페이스": [
        (date(2026, 3, 31), "LIG넥스원"),
    ],
}

def get_search_names(company_name: str, target_date: date) -> list[str]:
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
# 1단계 (Requests 방식) 검색 함수들
# ─────────────────────────────────────────────

def search_naver(company_name: str, target_date: date) -> dict | str | None:
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
                return result
            logger.info(f"  [{search_name}] 결과없음 → 다음 이름 시도")
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

def search_daum(company_name: str, target_date: date) -> dict | str | None:
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
    for sel in ["a.tit-g", "a.fn-tit", ".item-title a", ".news-item a", "a[href*='news']"]:
        tags = soup.select(sel)
        for a in tags:
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if href and title and len(title) > 5:
                return {"title": title, "link": href, "pub_date": target_date.isoformat(), "source": "daum"}
    return None

def search_google(company_name: str, target_date: date) -> dict | str | None:
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
# Requests 폴백 및 본문 파서
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

def fetch_fulltext_requests(link: str) -> str | None:
    if not link:
        return None
    if "n.news.naver.com" in link:
        return _fetch_naver_fulltext_requests(link)
    return _fetch_generic_fulltext_requests(link)

def _fetch_naver_fulltext_requests(url: str) -> str | None:
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

def _fetch_generic_fulltext_requests(url: str) -> str | None:
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
# 공통 저장 및 유틸
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
        "source":       article.get("source", "naver"),
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
# 1단계 고속 수집 루프 (Requests)
# ─────────────────────────────────────────────
def collect_all_requests():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total_stocks = len(STOCKS)
    total_days   = (END_DATE - START_DATE).days + 1
    logger.info(f"Requests 고속 수집 시작: {START_DATE} ~ {END_DATE} ({total_days}일) × {total_stocks}종목")
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
                    logger.warning(f"  ⛔ {consecutive_block}일 연속 전체차단 → {COOLDOWN_SECONDS//60}분 쿨다운 시작")
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
            fulltext = fetch_fulltext_requests(article["link"])
            save_article(company_name, ticker, article, fulltext)
            collected += 1

            src_tag = f"[{article.get('source', '?').upper()}]"
            logger.info(f"  저장 {src_tag}: {target_date} | {article['title'][:40]}..." + (" [전문X]" if not fulltext else ""))
            time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

        logger.info(f"  → {company_name} Requests 완료: 수집 {collected}건 / 스킵 {skipped}건")

    logger.info("Requests 고속 수집 단계 완료!\n")


# ─────────────────────────────────────────────
# 2단계 보완 수집 루프 (Playwright)
# ─────────────────────────────────────────────

def find_missing(company_name: str, ticker: str) -> list:
    folder = DATA_DIR / f"{company_name}_{ticker}"
    # 비어 있거나 아예 파일이 존재하지 않는 날짜 찾기
    missing_dates = []
    for d in date_range(START_DATE, END_DATE):
        fp = folder / f"{d.isoformat()}.json"
        if not fp.exists():
            missing_dates.append(d)
        else:
            # 빈 파일 체크 (수집 결과가 없어서 빈 json으로 생성된 것 제외하고 진짜 데이터가 날아갔거나 본문 수집에 완전히 실패한 경우 재수집하고 싶다면 체크)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = json.load(f)
                # 타이틀이 비어있는 빈 기사 저장형식이 아니라, 크래시 등으로 빈 데이터가 생겼다면 채우기
                if not content.get("title") and content.get("link"):
                    missing_dates.append(d)
            except Exception:
                missing_dates.append(d)
    return missing_dates

def search_naver_playwright(page, company_name: str, target_date: date) -> dict | None:
    from urllib.parse import quote, urlparse
    search_names = get_search_names(company_name, target_date)
    date_str = target_date.strftime("%Y%m%d")
    SKIP_DOMAINS = {"naver.com", "nid.naver.com", "help.naver.com"}

    def is_article_url(href: str) -> bool:
        try:
            p = urlparse(href)
            path  = p.path.rstrip("/")
            if not path or len(path) < 3:
                return False
            if any(c in path for c in [".", "=", "-", "_"]):
                return True
            if p.query:
                return True
            return len(path) > 4
        except Exception:
            return False

    for suffix in [" 주가", ""]:
        for search_name in search_names:
            query = f"{search_name}{suffix}"
            url = (
                f"https://search.naver.com/search.naver"
                f"?where=news&query={quote(query)}"
                f"&nso=so:sim,p:from{date_str}to{date_str}&start=1"
            )

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                try:
                    page.wait_for_selector("._fe_news_collection a, .list_news a", timeout=5_000)
                except PWTimeout:
                    pass
            except PWTimeout:
                logger.warning(f"  타임아웃: {company_name} {target_date} [{query}]")
                continue
            except Exception as e:
                err_msg = str(e).lower()
                logger.warning(f"  페이지 로드 오류 [{company_name} {target_date}]: {e}")
                if "crash" in err_msg or "closed" in err_msg or "disconnected" in err_msg:
                    raise
                continue

            try:
                candidates = page.query_selector_all("._fe_news_collection a, .list_news a, .group_news a")
                for el in candidates:
                    href  = el.get_attribute("href") or ""
                    title = (el.inner_text() or "").strip()
                    if (
                        href.startswith("http")
                        and len(title) >= 10
                        and not any(d in href for d in SKIP_DOMAINS)
                        and not title.startswith("구독")
                        and is_article_url(href)
                    ):
                        if suffix == "":
                            logger.info(f"  [{search_name}] 기업명 단독 쿼리로 수집")
                        elif search_name != company_name:
                            logger.info(f"  [{search_name}] 과거 사명 쿼리로 수집")
                        return {
                            "title":    title,
                            "link":     href,
                            "pub_date": target_date.isoformat(),
                            "source":   "naver",
                        }
            except Exception as e:
                logger.warning(f"  셀렉터 오류 [{company_name} {target_date}]: {e}")

    logger.info(f"  [{company_name}] {target_date} 결과없음 (모든 조합 시도)")
    return None

def fetch_fulltext_playwright(page, link: str) -> str | None:
    if not link or not link.startswith("http"):
        return None
    try:
        page.goto(link, wait_until="domcontentloaded", timeout=15_000)
        page.wait_for_timeout(2_500)
        html = page.content()
    except Exception as e:
        logger.warning(f"  전문 로드 오류 [{link}]: {e}")
        return None

    soup = BeautifulSoup(html, "html.parser")

    # 1순위: 네이버/언론사 공통 본문 셀렉터
    for sel in ["#dic_area", "#articeBody", ".newsct_article",
                "article", ".article_body", ".article-body",
                ".news_body", ".view_con", "#news_body_area",
                ".article_txt", ".news_content", ".cont_article"]:
        el = soup.select_one(sel)
        if el:
            lines = [l.strip() for l in el.get_text().splitlines() if l.strip()]
            text = "\n".join(lines)
            if len(text) > 100:
                return text

    # 2순위: p 태그 폴백 (BeautifulSoup)
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        tag.decompose()
    paras = [p.get_text().strip() for p in soup.find_all("p")]
    meaningful = [p for p in paras if len(p) >= 30]
    if meaningful:
        return "\n".join(meaningful)

    # 3순위: JS 렌더링 사이트 폴백
    try:
        js_text = page.evaluate("""
        () => {
            const SKIP = ['script','style','nav','header','footer','aside'];
            let best = { el: null, len: 0 };
            document.querySelectorAll('div, section, main, article').forEach(el => {
                if (SKIP.some(t => el.tagName.toLowerCase() === t)) return;
                const text = (el.innerText || '').trim();
                if (text.length > best.len && el.children.length < 20) {
                    best = { el, len: text.length };
                }
            });
            return best.el ? best.el.innerText.trim() : '';
        }
        """)
        if js_text and len(js_text) > 100:
            lines = [l.strip() for l in js_text.splitlines() if l.strip()]
            return "\n".join(lines)
    except Exception as e:
        logger.warning(f"  JS 본문 추출 오류: {e}")

    return None

def fill_gaps_playwright():
    logger.info("Playwright 빈 날짜 보완 수집을 시작합니다...")
    # 빈 날짜 집계
    gap_map = {}
    total_missing = 0
    for company_name, ticker in STOCKS:
        missing = find_missing(company_name, ticker)
        gap_map[(company_name, ticker)] = missing
        total_missing += len(missing)
        logger.info(f"  {company_name}: 빈 날짜 {len(missing)}개")

    logger.info(f"총 보완 대상: {total_missing}개 날짜")
    if total_missing == 0:
        logger.info("빈 날짜가 없습니다. 보완 단계를 스킵합니다.")
        return

    with sync_playwright() as pw:
        def init_browser():
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                locale="ko-KR",
            )
            page = ctx.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return browser, page

        browser, page = init_browser()
        total_stocks = len(STOCKS)
        global_collected = 0

        try:
            for idx, (company_name, ticker) in enumerate(STOCKS, 1):
                missing_dates = gap_map[(company_name, ticker)]
                if not missing_dates:
                    continue

                logger.info(f"[{idx}/{total_stocks}] {company_name} ({ticker}) - {len(missing_dates)}개 보완 시작")
                collected = 0

                for target_date in missing_dates:
                    if global_collected > 0 and global_collected % 30 == 0:
                        logger.info("  [System] 브라우저 메모리 세척을 위한 재시작...")
                        browser.close()
                        browser, page = init_browser()

                    fp = DATA_DIR / f"{company_name}_{ticker}" / f"{target_date.isoformat()}.json"
                    if fp.exists():
                        # 파일이 있는데 내용이 없는 경우를 제외하고 정상 파일 존재 시 스킵
                        try:
                            with open(fp, "r", encoding="utf-8") as f:
                                content = json.load(f)
                            if content.get("title"):
                                continue
                        except Exception:
                            pass

                    try:
                        article = search_naver_playwright(page, company_name, target_date)
                        if not article:
                            logger.info(f"  기사 없음 (빈 파일 생성하여 향후 스킵): {target_date}")
                            empty_article = {
                                "title": "",
                                "link": "",
                                "pub_date": target_date.isoformat(),
                                "source": "naver"
                            }
                            save_article(company_name, ticker, empty_article, "")
                            time.sleep(random.uniform(1.0, 2.0))
                            continue

                        fulltext = fetch_fulltext_playwright(page, article["link"])
                        save_article(company_name, ticker, article, fulltext)
                        collected += 1
                        global_collected += 1
                        logger.info(f"  저장: {target_date} | {article['title'][:45]}..." + (" [전문X]" if not fulltext else ""))
                        time.sleep(random.uniform(PW_DELAY_MIN, PW_DELAY_MAX))

                    except Exception as e:
                        if "crash" in str(e).lower() or "closed" in str(e).lower():
                            logger.warning(f"  [Error] 브라우저 충돌 감지 ({e}). 재시작 중...")
                            try: browser.close()
                            except: pass
                            browser, page = init_browser()
                        else:
                            logger.error(f"  [Error] 알 수 없는 오류: {e}")

                logger.info(f"  → {company_name} 보완 완료: {collected}개")
        finally:
            browser.close()
            logger.info("=== Playwright 보완 수집 단계 완료 ===")

# ─────────────────────────────────────────────
# 메인 통합 제어
# ─────────────────────────────────────────────
def main():
    logger.info("=========================================")
    logger.info("대표 10개 종목 뉴스 수집 및 보완 실행")
    logger.info("=========================================")
    
    # 1단계: Requests 기반 고속 수집
    collect_all_requests()
    
    # 2단계: Playwright 기반 누락 날짜 보완 수집
    fill_gaps_playwright()
    
    logger.info("모든 뉴스 수집 및 보완 단계가 완료되었습니다.")

if __name__ == "__main__":
    main()
