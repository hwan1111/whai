"""
script/fill_gaps_playwright.py
──────────────────────────────
Playwright(실제 Chrome) 기반 빈 날짜 보완 수집기

- 10개 종목 폴더를 스캔하여 JSON이 없는 날짜만 타겟 수집
- 실제 Chrome을 headless 모드로 구동 → 네이버 봇 감지 우회
- 검색 결과 HTML을 BeautifulSoup으로 파싱 (기존 로직 재사용)
- 이미 수집된 날짜는 자동 스킵
"""

import json
import time
import random
import logging
from datetime import date, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "news"
LOG_PATH = BASE_DIR / "data" / "gap_fill.log"

START_DATE = date(2020, 1, 1)
END_DATE   = date.today()

DELAY_MIN = 2.5   # 요청 간 최소 대기(초)
DELAY_MAX = 5.0   # 요청 간 최대 대기(초)

# ─────────────────────────────────────────────
# 수집 대상 종목 (10개)
# ─────────────────────────────────────────────
STOCKS = [
    # 반도체
    ("삼성전자",             "005930"),
    ("SK하이닉스",           "000660"),
    # 자동차
    ("현대차",              "005380"),
    ("기아",               "000270"),
    # 방산
    ("LIG디펜스앤에어로스페이스", "079550"),
    ("한화에어로스페이스",      "012450"),
    # 금융
    ("KB금융",              "105560"),
    ("신한지주",             "055550"),
    # 화학
    ("LG화학",              "051910"),
    ("SK이노베이션",          "096770"),
]

# ─────────────────────────────────────────────
# 사명 변경 이력 (날짜 이전엔 구 이름으로 검색)
# ─────────────────────────────────────────────
NAME_ALIASES: dict[str, list[tuple]] = {
    # LIG넥스원 → LIG디펜스앤에어로스페이스 (2026-03-31 사명 변경)
    "LIG디펜스앤에어로스페이스": [
        (date(2026, 3, 31), "LIG넥스원"),
    ],
}

def get_search_names(company_name: str, target_date: date) -> list[str]:
    """사명 변경 이력을 반영한 검색어 목록 (우선순위 순)
    - 1순위: 해당 날짜의 구 사명
    - 마지막: 현재 사명 (폴백)
    """
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
# 유틸
# ─────────────────────────────────────────────
def date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def find_missing(company_name: str, ticker: str) -> list:
    """JSON 파일이 없는 날짜 목록 반환"""
    folder = DATA_DIR / f"{company_name}_{ticker}"
    return [
        d for d in date_range(START_DATE, END_DATE)
        if not (folder / f"{d.isoformat()}.json").exists()
    ]


# ─────────────────────────────────────────────
# Playwright 검색 → BeautifulSoup 파싱
# ─────────────────────────────────────────────
def search_naver(page, company_name: str, target_date: date) -> dict | None:
    """
    Playwright로 네이버 뉴스 검색 - 다중 사명 + 쿼리 폴백
    - "{name} 주가" → "{name}" 순서로 시도
    - 결과없으면 다음 사명으로 자동 폴백
    """
    from urllib.parse import quote, urlparse
    search_names = get_search_names(company_name, target_date)
    date_str = target_date.strftime("%Y%m%d")

    SKIP_DOMAINS = {"naver.com", "nid.naver.com", "help.naver.com"}

    def is_article_url(href: str) -> bool:
        """홈페이지 URL이 아닌 실제 기사 URL인지 확인"""
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
                    page.wait_for_selector(
                        "._fe_news_collection a, .list_news a", timeout=5_000
                    )
                except PWTimeout:
                    pass
            except PWTimeout:
                logger.warning(f"  타임아웃: {company_name} {target_date} [{query}]")
                continue # 다음 검색어로
            except Exception as e:
                err_msg = str(e).lower()
                logger.warning(f"  페이지 로드 오류 [{company_name} {target_date}]: {e}")
                if "crash" in err_msg or "closed" in err_msg or "disconnected" in err_msg:
                    raise  # 치명적 오류는 메인 루프로 던져서 브라우저를 재시작하게 함
                continue

            try:
                candidates = page.query_selector_all(
                    "._fe_news_collection a, .list_news a, .group_news a"
                )
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






def fetch_fulltext(page, link: str) -> str | None:
    """기사 URL에 접속하여 본문 추출 (네이버 내부 + 외부 언론사 모두 지원)"""
    if not link or not link.startswith("http"):
        return None
    try:
        # domcontentloaded: HTML 파싱 완료 시점 (광고/추적기 무한로딩 무관)
        # 이후 2.5초 추가 대기로 JS 렌더링 본문 캡처
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

    # 3순위: page.evaluate() — React SPA 등 JS 렌더링 사이트
    # 브라우저 DOM에서 텍스트가 가장 많은 요소 찾기
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



def save_article(company_name: str, ticker: str, article: dict, fulltext: str | None):
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


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def fill_gaps():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 빈 날짜 집계
    gap_map = {}
    total_missing = 0
    for company_name, ticker in STOCKS:
        missing = find_missing(company_name, ticker)
        gap_map[(company_name, ticker)] = missing
        total_missing += len(missing)
        logger.info(f"  {company_name}: 빈 날짜 {len(missing)}개")

    logger.info(f"\n총 보완 대상: {total_missing}개 날짜\n")
    if total_missing == 0:
        logger.info("빈 날짜 없음 - 수집 완료 상태!")
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
                    logger.info(f"[{idx}/{total_stocks}] {company_name} - 빈 날짜 없음, 스킵")
                    continue

                logger.info(f"[{idx}/{total_stocks}] {company_name} ({ticker}) - {len(missing_dates)}개 보완 수집 시작")
                collected = 0

                for target_date in missing_dates:
                    # 30개 수집할 때마다 브라우저 재시작 (메모리 세척)
                    if global_collected > 0 and global_collected % 30 == 0:
                        logger.info("  [System] 브라우저 메모리 세척을 위한 재시작...")
                        browser.close()
                        browser, page = init_browser()

                    fp = DATA_DIR / f"{company_name}_{ticker}" / f"{target_date.isoformat()}.json"
                    if fp.exists(): continue

                    try:
                        article = search_naver(page, company_name, target_date)
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

                        fulltext = fetch_fulltext(page, article["link"])
                        save_article(company_name, ticker, article, fulltext)
                        collected += 1
                        global_collected += 1
                        logger.info(
                            f"  저장: {target_date} | {article['title'][:45]}..."
                            + (" [전문X]" if not fulltext else "")
                        )
                        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

                    except Exception as e:
                        if "crash" in str(e).lower() or "closed" in str(e).lower():
                            logger.warning(f"  [Error] 브라우저 충돌 감지 ({e}). 재시작 중...")
                            try: browser.close()
                            except: pass
                            browser, page = init_browser()
                            # 충돌 난 날짜는 다음 루프에서 다시 시도됨 (fp.exists()가 False이므로)
                        else:
                            logger.error(f"  [Error] 알 수 없는 오류: {e}")

                logger.info(f"  → {company_name} 보완 완료: {collected}개")

        finally:
            browser.close()
            logger.info("\n=== 전체 보완 수집 완료 ===")



if __name__ == "__main__":
    fill_gaps()
