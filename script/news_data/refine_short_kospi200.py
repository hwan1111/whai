import os
import re
import glob
import json
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
DATA_DIR = 'data/news'
KOSPI_FOLDER = os.path.join(DATA_DIR, "코스피200_KOSPI200")
LOG_PATH = os.path.join(DATA_DIR, "kospi200_refine.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

def _get_headers(referer: str = "https://www.naver.com/") -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": referer,
    }

# ─────────────────────────────────────────────
# 전처리 로직
# ─────────────────────────────────────────────
def clean_financial_news(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"(<저작권자|▶|ⓒ).*$", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "", text)
    text = re.sub(r"\[머니투데이.*?\]", "", text)
    text = re.sub(r"\(.*?\=연합뉴스\)", "", text)
    text = re.sub(r"사진\s*=\s*\S+", "", text)
    text = re.sub(r"사진제공\s*=\s*\S+", "", text)
    text = re.sub(r"[^\w\s.,%+\-가-힣]", " ", text)
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r" +", " ", text)
    return text.strip()

# ─────────────────────────────────────────────
# Requests 기반 검색어 후보군 추출
# ─────────────────────────────────────────────
def get_naver_candidates_requests(date_str: str) -> list[dict]:
    candidates = []
    seen = set()
    search_queries = ["코스피200", "코스피 200"]
    
    date_raw = date_str.replace("-", "")
    date_dot = date_str.replace("-", ".")
    for query in search_queries:
        url = (
            "https://search.naver.com/search.naver"
            f"?where=news&query={requests.utils.quote(query)}"
            f"&sm=tab_opt&pd=3&ds={date_dot}&de={date_dot}"
            f"&nso=so:sim,p:from{date_raw}to{date_raw},a:all&start=1"
        )
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=10)
            if resp.status_code == 403:
                logger.warning(f"  [Requests 차단] {date_str} -> Playwright 폴백")
                return "BLOCKED"
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            for mark in soup.find_all("mark"):
                parent = mark.parent
                title = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))
                container = parent
                for _ in range(8):
                    if not container:
                        break
                    for a in container.find_all("a", href=True):
                        href = a["href"]
                        if "n.news.naver.com" in href and href not in seen:
                            seen.add(href)
                            candidates.append({"title": title, "link": href, "source": "naver"})
                    container = container.parent
        except Exception as e:
            logger.warning(f"  [Requests 에러] {date_str} ({query}): {e}")
            
    return candidates

# ─────────────────────────────────────────────
# Playwright 기반 검색어 후보군 추출
# ─────────────────────────────────────────────
def get_naver_candidates_playwright(page, date_str: str) -> list[dict]:
    candidates = []
    seen = set()
    search_queries = ["코스피200", "코스피 200"]
    SKIP_DOMAINS = {"nid.naver.com", "help.naver.com"}
    
    date_raw = date_str.replace("-", "")
    date_dot = date_str.replace("-", ".")
    for query in search_queries:
        url = (
            "https://search.naver.com/search.naver"
            f"?where=news&query={requests.utils.quote(query)}"
            f"&sm=tab_opt&pd=3&ds={date_dot}&de={date_dot}"
            f"&nso=so:sim,p:from{date_raw}to{date_raw},a:all&start=1"
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            try:
                page.wait_for_selector("._fe_news_collection a, .list_news a", timeout=3_000)
            except PWTimeout:
                pass
            
            els = page.query_selector_all("._fe_news_collection a, .list_news a, .group_news a")
            for el in els:
                href = el.get_attribute("href") or ""
                title = (el.inner_text() or "").strip()
                if "n.news.naver.com" in href and href not in seen and not any(d in href for d in SKIP_DOMAINS):
                    seen.add(href)
                    candidates.append({"title": title, "link": href, "source": "naver"})
        except Exception as e:
            logger.warning(f"  [Playwright 에러] {date_str} ({query}): {e}")
            
    return candidates

# ─────────────────────────────────────────────
# Requests 기반 본문 수집
# ─────────────────────────────────────────────
def fetch_fulltext_requests(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=_get_headers("https://news.naver.com/"), timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for sel in ["#dic_area", "#articeBody", ".newsct_article", "#content"]:
            tag = soup.select_one(sel)
            if tag:
                lines = [l.strip() for l in tag.get_text(separator="\n").splitlines() if l.strip()]
                return "\n".join(lines)
        return None
    except Exception:
        return None

# ─────────────────────────────────────────────
# Playwright 기반 본문 수집
# ─────────────────────────────────────────────
def fetch_fulltext_playwright(page, url: str) -> str | None:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        page.wait_for_timeout(1_500)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        for sel in ["#dic_area", "#articeBody", ".newsct_article", "#content"]:
            tag = soup.select_one(sel)
            if tag:
                lines = [l.strip() for l in tag.get_text(separator="\n").splitlines() if l.strip()]
                return "\n".join(lines)
        return None
    except Exception:
        return None

# ─────────────────────────────────────────────
# 기사 저장
# ─────────────────────────────────────────────
def save_article(filepath: str, article: dict, fulltext: str):
    doc = {
        "pub_date": article["pub_date"],
        "ticker": "KOSPI200",
        "company_name": "코스피200",
        "title": article["title"],
        "fulltext": fulltext,
        "link": article["link"],
        "source": article["source"]
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────────
# 메인 제어 루프
# ─────────────────────────────────────────────
def refine_short_files():
    json_files = glob.glob(f"{KOSPI_FOLDER}/**/*.json", recursive=True)
    target_files = []
    
    # 50자 이하인 파일 추출
    for fp in json_files:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
        fulltext = data.get('fulltext', '')
        preprocessed = clean_financial_news(fulltext)
        if len(preprocessed) <= 50:
            target_files.append((fp, os.path.basename(fp).replace(".json", "")))
    # 날짜 순서대로 정렬 (2020-01-01부터 차례대로 처리하기 위함)
    target_files.sort(key=lambda x: x[1])
            
    total_targets = len(target_files)
    logger.info(f"분석 완료: 총 {total_targets}개의 보완 대상 파일(50자 이하)을 식별했습니다.")
    
    if total_targets == 0:
        logger.info("보완할 파일이 없습니다. 종료합니다.")
        return
        
    # 전체 보완 처리 진행
    max_process_limit = 9999
    logger.info(f"전체 보완 대상 {total_targets}개 파일에 대해 순차적 보완 처리를 시작합니다.")
    target_files = target_files[:max_process_limit]
    
    pw = None
    browser = None
    page = None
    
    try:
        requests_blocked = False
        
        for idx, (fp, date_str) in enumerate(target_files, 1):
            logger.info(f"[{idx}/{len(target_files)}] 파일 보완 중... 날짜: {date_str}")
            candidates = []
            
            # 1단계: Requests 시도 (차단되지 않은 경우)
            if not requests_blocked:
                res = get_naver_candidates_requests(date_str)
                if res == "BLOCKED":
                    requests_blocked = True
                else:
                    candidates = res
            
            # 2단계: Requests가 차단되었거나 실패한 경우 Playwright 폴백
            if requests_blocked or not candidates:
                if pw is None:
                    logger.info("  Playwright 브라우저 구동 시작...")
                    pw = sync_playwright().start()
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
                
                candidates = get_naver_candidates_playwright(page, date_str)
            
            if not candidates:
                logger.info(f"  [실패] {date_str}에 대한 다른 후보 기사를 찾을 수 없습니다.")
                continue
                
            # 후보군 본문 수집 루프
            success = False
            for c_idx, candidate in enumerate(candidates, 1):
                link = candidate["link"]
                logger.info(f"    후보 {c_idx}/{len(candidates)} 시도 중: {candidate['title'][:30]}...")
                
                # 본문 다운로드
                if page is not None:
                    fulltext = fetch_fulltext_playwright(page, link)
                else:
                    fulltext = fetch_fulltext_requests(link)
                    
                if not fulltext:
                    continue
                    
                # 전처리 길이 체크
                preprocessed = clean_financial_news(fulltext)
                length = len(preprocessed)
                
                if length >= 50:
                    candidate["pub_date"] = date_str
                    save_article(fp, candidate, fulltext)
                    logger.info(f"    ✨ [보완 성공] 새 본문 길이: {length}자")
                    success = True
                    break
                else:
                    logger.info(f"    [건너뜀] 새 본문도 {length}자로 50자 이하임.")
            
            if not success:
                logger.info(f"  [미해결] 모든 후보 기사가 50자 이하입니다.")
            
            time.sleep(random.uniform(2.0, 3.5))
            
    finally:
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
        logger.info("보완 처리가 완료되었습니다.")

if __name__ == '__main__':
    refine_short_files()
