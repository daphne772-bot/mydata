"""
scraper.py
- 관세청 수출입무역통계(tradedata.go.kr) 크롤링
  1차: 메인 페이지 인라인 JS → 연도별 수출입 실적 추출
  2차: Selenium으로 "수출입 실적" 페이지 접속 → 품목/월별 데이터 추출
  3차: kita.net 무역통계 → fallback
- 봇 탐지 우회 (Anti-Detection)
- WebDriverWait 명시적 대기 (최대 30초)
- 디버깅: 에러 시 스크린샷 + 페이지 소스 저장
"""
import time
import re
import os
import json
import traceback
from datetime import datetime

import requests

# Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException,
        ElementClickInterceptedException, WebDriverException
    )
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# 디버그 경로
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_screenshots")
MAX_WAIT = 30


def _safe_print(msg):
    """cp949 인코딩 문제 방지 출력"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def save_debug(content, name="debug", ext="txt"):
    """디버그 정보를 파일로 저장"""
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(SCREENSHOT_DIR, f"{name}_{timestamp}.{ext}")
        mode = "w" if ext in ("txt", "html", "json") else "wb"
        enc = "utf-8" if mode == "w" else None
        with open(filepath, mode, encoding=enc) as f:
            f.write(content)
        _safe_print(f"[DEBUG] 저장: {filepath}")
        return filepath
    except Exception as e:
        _safe_print(f"[DEBUG] 저장 실패: {e}")
        return None


def save_screenshot(driver, name):
    """Selenium 스크린샷 저장"""
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{name}_{timestamp}.png")
        driver.save_screenshot(path)
        _safe_print(f"[DEBUG] 스크린샷: {path}")
        return path
    except Exception:
        return None


# ═══════════════════════════════════════════════════
#  Chrome WebDriver 생성 (봇 탐지 우회)
# ═══════════════════════════════════════════════════

def create_driver(headless=True):
    """Anti-Detection Chrome WebDriver 생성"""
    if not SELENIUM_AVAILABLE:
        raise ImportError("Selenium이 설치되지 않았습니다")

    options = Options()
    if headless:
        options.add_argument("--headless=new")

    # 봇 탐지 우회
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.6778.109 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")

    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)

    # navigator.webdriver 숨김 + 브라우저 속성 위장
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']});
            window.chrome = {runtime: {}};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : originalQuery(parameters);
        """}
    )

    driver.set_page_load_timeout(60)
    driver.implicitly_wait(3)
    return driver


# ═══════════════════════════════════════════════════
#  1차: tradedata.go.kr 메인 페이지 인라인 데이터 추출
# ═══════════════════════════════════════════════════

def scrape_tradedata_main(progress_callback=None):
    """
    tradedata.go.kr 메인 페이지 HTML에 포함된 인라인 JS 데이터를 추출합니다.
    - 연도별 수출입 실적 (백만 달러)
    - 국가별 수출입 실적
    - 최신 월 수출입 총액 (억 달러)
    """
    if progress_callback:
        progress_callback("tradedata.go.kr 메인 페이지 접속 중...")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.6778.109 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }

    try:
        resp = requests.get(
            "https://tradedata.go.kr/cts/index.do",
            headers=headers, timeout=30, verify=True
        )

        if resp.status_code != 200:
            if progress_callback:
                progress_callback(f"HTTP {resp.status_code}")
            return None

        html = resp.text
        save_debug(html, "tradedata_main_page", "html")

        if progress_callback:
            progress_callback(f"메인 페이지 수신: {len(html)}B")

        result = {
            "yearly_export": {},    # {2021: 644400, 2022: 683585, ...} (백만 달러)
            "yearly_import": {},
            "latest_month": None,   # "2025.01~12" 등
            "latest_export_usd": None,   # 수출 695억 달러 → 69500 (백만달러)
            "latest_import_usd": None,
            "country_export": {},   # {중국: 12965, ...} (백만 달러)
            "country_import": {},
        }

        # 1) 연도별 수출금액 추출 (첫 번째 chart의 expUsdAmtChart.push만)
        #    HTML에 expUsdAmtChart가 두 번 선언됨 (1차: 연도별, 2차: 국가별)
        #    두 번째 'var expUsdAmtChart' 전까지만 사용
        chart_sections = html.split('var expUsdAmtChart')
        first_chart = chart_sections[1] if len(chart_sections) > 1 else html
        # 두 번째 선언 전까지만
        if len(chart_sections) > 2:
            first_chart = chart_sections[1]
        
        exp_matches = re.findall(
            r"expUsdAmtChart\.push\(\{priodTitle:\s*'([^']+)',\s*y:\s*(\d+)\}\)",
            first_chart
        )
        for title, val in exp_matches:
            year_m = re.search(r"(20\d{2})", title)
            if year_m:
                year = int(year_m.group(1))
                result["yearly_export"][year] = int(val)

        # 2) 연도별 수입금액 추출 (첫 번째 chart만)
        imp_matches = re.findall(
            r"impUsdAmtChart\.push\(\{priodTitle:\s*'([^']+)',\s*y:\s*(\d+)\}\)",
            first_chart
        )
        for title, val in imp_matches:
            year_m = re.search(r"(20\d{2})", title)
            if year_m:
                year = int(year_m.group(1))
                result["yearly_import"][year] = int(val)

        # 3) 최신 수출입 총액 (억 달러)
        exp_total = re.search(r"수출\s+(\d+)억\s*달러", html)
        if exp_total:
            result["latest_export_usd"] = int(exp_total.group(1)) * 100  # 억달러 -> 백만달러

        imp_total = re.search(r"수입\s+(\d+)억\s*달러", html)
        if imp_total:
            result["latest_import_usd"] = int(imp_total.group(1)) * 100

        # 4) 기간 추출
        period = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})", html)
        if period:
            result["latest_month"] = f"{period.group(1)} ~ {period.group(2)}"

        # 5) 국가별 실적 (cntyNmChart / expUsdAmtChart in second chart)
        country_names = re.findall(r"cntyNmChart\.push\(\"([^\"]+)\"\)", html)
        country_exp = re.findall(
            r"(?:cntyNmChart\.push.*?\n.*?)*expUsdAmtChart\.push\(\{priodTitle:\s*'([^']+)',\s*y:\s*(\d+)\}\)",
            html
        )
        # 국가 데이터는 두 번째 chart 구간에서 나타남
        if len(country_names) >= 5 and len(country_exp) >= len(exp_matches) + 5:
            for i, name in enumerate(country_names):
                idx = len(exp_matches) + i
                if idx < len(country_exp):
                    result["country_export"][name] = int(country_exp[idx][1])

        if progress_callback:
            years = sorted(result["yearly_export"].keys())
            progress_callback(
                f"연도별 수출: {len(years)}개년 ({min(years) if years else '?'}-{max(years) if years else '?'}), "
                f"국가: {len(result['country_export'])}개"
            )

        return result

    except requests.exceptions.Timeout:
        if progress_callback:
            progress_callback("타임아웃: tradedata.go.kr")
    except requests.exceptions.ConnectionError as e:
        if progress_callback:
            progress_callback(f"연결 오류: {str(e)[:100]}")
    except Exception as e:
        if progress_callback:
            progress_callback(f"오류: {type(e).__name__}: {str(e)[:100]}")
        traceback.print_exc()

    return None


# ═══════════════════════════════════════════════════
#  2차: Selenium으로 수출입 실적 페이지 접속
# ═══════════════════════════════════════════════════

def scrape_tradedata_detail(hs_code, start_year=2024, start_month=1, progress_callback=None):
    """
    Selenium으로 tradedata.go.kr의 "수출입 실적" 페이지에 접속하여
    품목별/월별 상세 데이터를 추출합니다.
    - 메인 페이지 로드 → ets_f_prccMenuLoad JS 실행 → 조회 조건 입력 → 결과 파싱
    """
    if not SELENIUM_AVAILABLE:
        if progress_callback:
            progress_callback("Selenium 미설치")
        return []

    driver = None
    results = []

    try:
        if progress_callback:
            progress_callback("Chrome 브라우저 시작...")
        driver = create_driver(headless=True)

        # 1) 메인 페이지 접속
        driver.get("https://tradedata.go.kr/cts/index.do")
        WebDriverWait(driver, MAX_WAIT).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        if progress_callback:
            progress_callback(f"메인 로드 완료: {driver.title}")

        save_screenshot(driver, "detail_main")

        # 2) "수출입 실적" 페이지로 JS 함수 직접 실행
        #    ets_f_prccMenuLoad('/cts/hmpg/openETS0100019Q.do', {menuId:'ETS_MNK_10200000'})
        if progress_callback:
            progress_callback("수출입 실적 페이지로 이동...")

        driver.execute_script(
            "ets_f_prccMenuLoad('/cts/hmpg/openETS0100019Q.do', {menuId:'ETS_MNK_10200000'});"
        )

        # 페이지 영역이 AJAX로 로드될 때까지 대기
        time.sleep(3)  # AJAX 초기 로딩 대기

        # content 영역이 표시될 때까지 대기
        try:
            WebDriverWait(driver, MAX_WAIT).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#content, .contents, .con_container"))
            )
        except TimeoutException:
            pass  # 이미 표시되어 있을 수 있음

        save_screenshot(driver, "detail_stat_page")
        save_debug(driver.page_source, "detail_stat_page", "html")

        if progress_callback:
            progress_callback(f"실적 페이지 로드됨. URL: {driver.current_url}")

        # 3) 페이지의 모든 입력 필드 로깅 (디버깅)
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        all_selects = driver.find_elements(By.TAG_NAME, "select")

        input_log_lines = [f"=== 입력 필드 총 {len(all_inputs)}개, 셀렉트 {len(all_selects)}개 ==="]
        for inp in all_inputs[:40]:
            try:
                iid = inp.get_attribute("id") or ""
                iname = inp.get_attribute("name") or ""
                itype = inp.get_attribute("type") or ""
                ival = inp.get_attribute("value") or ""
                iph = inp.get_attribute("placeholder") or ""
                vis = inp.is_displayed()
                input_log_lines.append(
                    f"  INPUT id={iid}, name={iname}, type={itype}, value={ival}, "
                    f"ph={iph}, visible={vis}"
                )
            except Exception:
                continue

        for sel in all_selects[:20]:
            try:
                sid = sel.get_attribute("id") or ""
                sname = sel.get_attribute("name") or ""
                opts = sel.find_elements(By.TAG_NAME, "option")
                opt_texts = [o.text for o in opts[:5]]
                input_log_lines.append(
                    f"  SELECT id={sid}, name={sname}, options={opt_texts}"
                )
            except Exception:
                continue

        save_debug("\n".join(input_log_lines), "detail_inputs", "txt")
        if progress_callback:
            progress_callback(f"입력 필드: {len(all_inputs)}개, 셀렉트: {len(all_selects)}개")

        # 4) 조회 조건 설정 시도
        #    디버깅에서 발견: id=ETS0100019Q_hsSgn, name=hsSgn
        hs_input_found = False
        # XPath 사용 (CSS attribute contains selector가 Chrome 145에서 오류)
        hs_xpaths = [
            "//input[@id='ETS0100019Q_hsSgn']",
            "//input[@name='hsSgn']",
            "//input[contains(@id,'hsSgn')]",
            "//input[contains(@name,'hsSgn')]",
            "//input[contains(@id,'hsCode')]",
            "//input[contains(@id,'hsCd')]",
            "//input[contains(@placeholder,'HS')]",
        ]

        for xpath in hs_xpaths:
            try:
                el = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                if el:
                    el.clear()
                    el.send_keys(hs_code)
                    hs_input_found = True
                    if progress_callback:
                        progress_callback(f"HS Code '{hs_code}' 입력 성공 ({xpath})")
                    break
            except (TimeoutException, NoSuchElementException, WebDriverException):
                continue

        if not hs_input_found:
            if progress_callback:
                progress_callback("HS Code 입력란을 찾지 못함 - 기본 조회 시도")

        # 5) 조회 버튼 클릭
        btn_clicked = False
        btn_selectors = [
            "button.btn_search",
            "a.btn_search",
        ]

        # XPath로도 시도
        btn_xpaths = [
            "//button[contains(text(),'조회')]",
            "//a[contains(text(),'조회')]",
            "//span[contains(text(),'조회')]/parent::button",
            "//span[contains(text(),'조회')]/parent::a",
            "//input[@value='조회']",
            "//*[contains(@class,'btn') and contains(@onclick,'search')]",
        ]

        for selector in btn_selectors:
            try:
                btn = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                try:
                    btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", btn)
                btn_clicked = True
                if progress_callback:
                    progress_callback(f"조회 버튼 클릭 (CSS: {selector})")
                break
            except (TimeoutException, NoSuchElementException):
                continue

        if not btn_clicked:
            for xpath in btn_xpaths:
                try:
                    btn = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    try:
                        btn.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", btn)
                    btn_clicked = True
                    if progress_callback:
                        progress_callback(f"조회 버튼 클릭 (XPath: {xpath})")
                    break
                except (TimeoutException, NoSuchElementException):
                    continue

        if not btn_clicked:
            if progress_callback:
                progress_callback("조회 버튼을 찾지 못함")
            save_screenshot(driver, "detail_no_search_btn")

        # 6) 결과 테이블 대기 (Explicit Wait - 최대 30초)
        if progress_callback:
            progress_callback(f"결과 테이블 대기 (최대 {MAX_WAIT}초)...")

        time.sleep(3)  # AJAX 응답 대기

        try:
            WebDriverWait(driver, MAX_WAIT).until(
                EC.presence_of_element_located((By.XPATH, "//table//tbody//tr[td]"))
            )
            if progress_callback:
                progress_callback("테이블 영역 로드 완료")
        except TimeoutException:
            if progress_callback:
                progress_callback("테이블 영역 타임아웃")
            save_screenshot(driver, "detail_no_table")

        save_screenshot(driver, "detail_result")
        save_debug(driver.page_source, "detail_result", "html")

        # 7) 정확한 데이터 테이블 찾기 + 파싱
        results = parse_trade_data(driver, progress_callback)

        if progress_callback:
            progress_callback(f"Selenium 추출 완료: {len(results)}건")

    except WebDriverException as e:
        msg = f"[Selenium] WebDriverException: {str(e)[:150]}"
        _safe_print(msg)
        if driver:
            save_screenshot(driver, "error_webdriver")
            save_debug(driver.page_source, "error_webdriver", "html")
        if progress_callback:
            progress_callback(msg)

    except Exception as e:
        msg = f"[Selenium] {type(e).__name__}: {str(e)[:150]}"
        _safe_print(msg)
        traceback.print_exc()
        if driver:
            try:
                save_screenshot(driver, "error_unknown")
                save_debug(driver.page_source, "error_unknown", "html")
            except Exception:
                pass
        if progress_callback:
            progress_callback(msg)

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return results


# ═══════════════════════════════════════════════════
#  테이블 타겟팅 + 파싱 (핵심 로직)
# ═══════════════════════════════════════════════════

# 데이터 테이블 식별용 키워드
_TABLE_KEYWORDS = ["수출금액", "중량", "수출건수", "수입금액", "무역수지", "수출액"]


def _find_target_table(driver, progress_callback=None):
    """
    페이지 내 모든 <table> 중에서 **<thead> 또는 <th>** 안에
    '수출금액' 또는 '중량' 등 데이터 키워드가 포함된 테이블 하나만 반환합니다.

    Returns:
        target_table (WebElement | None): 데이터 테이블, 없으면 None
    """
    tables = driver.find_elements(By.TAG_NAME, "table")
    if progress_callback:
        progress_callback(f"페이지 내 테이블 총 {len(tables)}개 → 필터링 시작")

    for idx, table in enumerate(tables):
        try:
            # 방법 1: <thead> 텍스트 전체에서 키워드 검색
            thead_els = table.find_elements(By.TAG_NAME, "thead")
            for thead in thead_els:
                thead_text = thead.text
                for kw in _TABLE_KEYWORDS:
                    if kw in thead_text:
                        if progress_callback:
                            progress_callback(
                                f"[필터] 테이블 #{idx} <thead>에서 '{kw}' 발견 → 타겟"
                            )
                        return table

            # 방법 2: <th> 개별 셀에서 키워드 검색 (thead 없는 테이블 대비)
            th_els = table.find_elements(By.TAG_NAME, "th")
            for th in th_els:
                th_text = th.text.strip()
                for kw in _TABLE_KEYWORDS:
                    if kw in th_text:
                        if progress_callback:
                            progress_callback(
                                f"[필터] 테이블 #{idx} <th>에서 '{kw}' 발견 → 타겟"
                            )
                        return table

        except Exception:
            # stale element 등 무시
            continue

    if progress_callback:
        progress_callback("데이터 테이블을 찾을 수 없음 (키워드 미매칭)")
    return None


def parse_trade_data(driver, progress_callback=None):
    """
    Selenium driver에서 수출입 데이터 테이블을 찾아 파싱합니다.

    1단계: 현재 페이지(메인 DOM)에서 _find_target_table로 정확한 테이블 탐색
    2단계: 실패 시 → 페이지 내 모든 iframe을 순회하며 재탐색

    Returns:
        list[dict]: [{"date": "2024-01", "export_usd": 12345}, ...]
    """
    results = []

    # ──────────────────────────────
    #  1단계: 메인 DOM에서 타겟 테이블 검색
    # ──────────────────────────────
    if progress_callback:
        progress_callback("[파싱] 1단계: 메인 DOM에서 데이터 테이블 검색...")

    target_table = _find_target_table(driver, progress_callback)

    if target_table:
        results = _extract_rows_from_table(target_table, progress_callback)
        if results:
            return results

    # ──────────────────────────────
    #  2단계: iframe 내부 순회 검색
    # ──────────────────────────────
    if progress_callback:
        progress_callback("[파싱] 2단계: iframe 내부 탐색 시작...")

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    if progress_callback:
        progress_callback(f"[파싱] iframe {len(iframes)}개 발견")

    for i, iframe in enumerate(iframes):
        try:
            driver.switch_to.frame(iframe)
            if progress_callback:
                progress_callback(f"[파싱] iframe #{i} 진입")

            target_table = _find_target_table(driver, progress_callback)
            if target_table:
                results = _extract_rows_from_table(target_table, progress_callback)
                if results:
                    if progress_callback:
                        progress_callback(
                            f"[파싱] iframe #{i}에서 {len(results)}건 추출 성공"
                        )
                    driver.switch_to.default_content()
                    return results

            driver.switch_to.default_content()

        except Exception as e:
            _safe_print(f"[파싱] iframe #{i} 오류: {type(e).__name__}: {str(e)[:80]}")
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            continue

    if progress_callback:
        progress_callback("[파싱] 메인 DOM + iframe 모두에서 데이터 테이블 없음")

    # 디버그: 발견된 모든 테이블 헤더 요약 저장
    _log_all_table_headers(driver, progress_callback)

    return results


def _extract_rows_from_table(table, progress_callback=None):
    """
    타겟 테이블에서 <tr> → <td> 순회하며 날짜+금액 데이터를 추출합니다.
    """
    results = []

    # 헤더(컬럼) 정보 파악
    headers = []
    th_els = table.find_elements(By.TAG_NAME, "th")
    for th in th_els:
        headers.append(th.text.strip())

    if progress_callback and headers:
        progress_callback(f"[파싱] 컬럼: {headers[:10]}")

    # 데이터 행 추출
    tbody_els = table.find_elements(By.TAG_NAME, "tbody")
    if tbody_els:
        rows = tbody_els[0].find_elements(By.TAG_NAME, "tr")
    else:
        rows = table.find_elements(By.TAG_NAME, "tr")

    if progress_callback:
        progress_callback(f"[파싱] 데이터 행: {len(rows)}개")

    # 디버그: 처음 5행의 셀 텍스트를 로그로 저장
    debug_lines = [f"=== 타겟 테이블 셀 데이터 (총 {len(rows)}행) ==="]
    for ridx, row in enumerate(rows[:5]):
        cells_dbg = row.find_elements(By.TAG_NAME, "td")
        if cells_dbg:
            texts = [c.text.strip()[:50] for c in cells_dbg]
            debug_lines.append(f"  행 #{ridx}: {texts}")
    save_debug("\n".join(debug_lines), "target_table_cells", "txt")

    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells or len(cells) < 2:
            continue

        cell_texts = [cell.text.strip() for cell in cells]
        parsed = _parse_trade_row(cell_texts)
        if parsed:
            results.append(parsed)

    if progress_callback:
        progress_callback(f"[파싱] 유효 데이터: {len(results)}건")

    return results


def _log_all_table_headers(driver, progress_callback=None):
    """디버그용: 페이지 내 모든 테이블의 헤더 요약을 로그로 저장"""
    try:
        tables = driver.find_elements(By.TAG_NAME, "table")
        lines = [f"=== 전체 테이블 헤더 요약 ({len(tables)}개) ==="]
        for idx, table in enumerate(tables):
            try:
                ths = table.find_elements(By.TAG_NAME, "th")
                th_texts = [th.text.strip()[:30] for th in ths[:10]]
                row_count = len(table.find_elements(By.TAG_NAME, "tr"))
                lines.append(f"  테이블 #{idx}: rows={row_count}, th={th_texts}")
            except Exception:
                lines.append(f"  테이블 #{idx}: (읽기 실패)")
        save_debug("\n".join(lines), "all_table_headers", "txt")
    except Exception:
        pass


def _parse_trade_row(cells):
    """
    tradedata.go.kr 수출입 실적 테이블의 행을 파싱합니다.

    실제 데이터 구조:
      cells[0] = 체크박스/번호 (빈 값)
      cells[1] = 년도 (예: '2026')
      cells[2] = 월 (예: '01')
      cells[3] = 품목명 (예: '살아 있는 동물')
      cells[4] = 수출중량 (톤, 예: '1.7')
      cells[5] = 수출금액 (천 달러, 예: '405')
      cells[6] = 수입중량 (톤)
      cells[7] = 수입금액 (천 달러)
      cells[8] = 무역수지 (천 달러)

    또는 총계 행:
      cells[0] = '총계'
      cells[1:] = 합산 수치
    """
    try:
        if len(cells) < 4:
            return None

        # ── 총계 행 건너뛰기 ──
        if any("총계" in c or "합계" in c or "소계" in c for c in cells[:2]):
            return None

        # ── 방법 1: 구조화된 포맷 (년/월 별도 셀) ──
        #    cells[1]=년도, cells[2]=월
        year_str = cells[1].strip() if len(cells) > 1 else ""
        month_str = cells[2].strip() if len(cells) > 2 else ""

        if re.match(r"^20\d{2}$", year_str) and re.match(r"^\d{1,2}$", month_str):
            year = int(year_str)
            month = int(month_str)
            if 2020 <= year <= 2030 and 1 <= month <= 12:
                date_str = f"{year}-{month:02d}"

                # 수출금액 추출 (cells[5] = 천 달러)
                export_amt = _parse_number(cells[5]) if len(cells) > 5 else None
                # 수입금액 (cells[7] = 천 달러)
                import_amt = _parse_number(cells[7]) if len(cells) > 7 else None
                # 무역수지 (cells[8] = 천 달러)
                trade_balance = _parse_number(cells[8]) if len(cells) > 8 else None
                # 품목명 (cells[3])
                item_name = cells[3].strip() if len(cells) > 3 else ""
                # 수출중량 (cells[4] = 톤)
                export_weight = _parse_number(cells[4]) if len(cells) > 4 else None

                if export_amt is not None:
                    result = {
                        "date": date_str,
                        "export_usd": export_amt,  # 천 달러
                        "item_name": item_name,
                    }
                    if import_amt is not None:
                        result["import_usd"] = import_amt
                    if trade_balance is not None:
                        result["trade_balance"] = trade_balance
                    if export_weight is not None:
                        result["export_weight_ton"] = export_weight
                    return result

        # ── 방법 2: 날짜가 한 셀에 있는 폴백 (2024.01 / 2024-01 등) ──
        for i, cell in enumerate(cells):
            match = re.search(r"(20\d{2})[.\-/\s]?(\d{2})", cell)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                if 2020 <= year <= 2030 and 1 <= month <= 12:
                    date_str = f"{year}-{month:02d}"

                    # 나머지 셀에서 가장 큰 양수 = 수출금액
                    numbers = []
                    for j, c in enumerate(cells):
                        if j == i:
                            continue
                        val = _parse_number(c)
                        if val is not None and val > 0:
                            numbers.append(val)

                    if numbers:
                        return {
                            "date": date_str,
                            "export_usd": max(numbers),
                        }

    except Exception:
        pass
    return None


def _parse_number(text):
    """
    숫자 텍스트를 float로 변환합니다.
    '65,783,872' → 65783872.0
    '-9,200' → -9200.0
    빈 문자열이나 비숫자 → None
    """
    try:
        clean = text.strip().replace(",", "").replace(" ", "").replace("$", "")
        if not clean or clean == "-":
            return None
        return float(clean)
    except (ValueError, AttributeError):
        return None


# ═══════════════════════════════════════════════════
#  3차: kita.net 크롤링 (Fallback)
# ═══════════════════════════════════════════════════

def scrape_kita(hs_code, start_year=2024, start_month=1, progress_callback=None):
    """kita.net 무역통계 크롤링 (Selenium fallback)"""
    if not SELENIUM_AVAILABLE:
        if progress_callback:
            progress_callback("Selenium 미설치")
        return []

    driver = None
    results = []

    try:
        if progress_callback:
            progress_callback("kita.net 접속 중...")
        driver = create_driver(headless=True)

        driver.get("https://stat.kita.net/stat/kts/pum/ItemImpExpList.screen")
        WebDriverWait(driver, MAX_WAIT).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        if progress_callback:
            progress_callback(f"kita.net 로드: {driver.title}")

        save_screenshot(driver, "kita_main")
        save_debug(driver.page_source, "kita_main", "html")

        # 모든 입력 필드 로깅
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        input_info = []
        for inp in all_inputs[:30]:
            try:
                iid = inp.get_attribute("id") or ""
                iname = inp.get_attribute("name") or ""
                itype = inp.get_attribute("type") or ""
                ival = inp.get_attribute("value") or ""
                input_info.append(f"id={iid}, name={iname}, type={itype}, val={ival}")
            except Exception:
                continue
        save_debug("\n".join(input_info), "kita_inputs", "txt")

        # 기간/HS Code 입력 시도
        hs_selectors = [
            "input[id*='hsCd']", "input[name*='hsCd']",
            "input[id*='hsCode']", "input[name*='hsCode']",
            "input[id*='searchHsCd']", "input[name*='searchHsCd']",
        ]

        for selector in hs_selectors:
            try:
                el = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if el:
                    el.clear()
                    el.send_keys(hs_code)
                    if progress_callback:
                        progress_callback(f"HS Code 입력 ({selector})")
                    break
            except (TimeoutException, NoSuchElementException):
                continue

        # 조회 버튼
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'조회') or contains(text(),'검색')]"))
            )
            btn.click()
            if progress_callback:
                progress_callback("조회 버튼 클릭")
        except (TimeoutException, NoSuchElementException):
            if progress_callback:
                progress_callback("조회 버튼 못 찾음")

        time.sleep(3)

        # 결과 대기
        try:
            WebDriverWait(driver, MAX_WAIT).until(
                EC.presence_of_element_located((By.XPATH, "//table//tbody//tr[td]"))
            )
        except TimeoutException:
            pass

        save_screenshot(driver, "kita_result")

        # 테이블 파싱
        tables = driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            rows = table.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if cells and len(cells) >= 2:
                    cell_texts = [cell.text.strip() for cell in cells]
                    parsed = _parse_trade_row(cell_texts)
                    if parsed:
                        results.append(parsed)

        if progress_callback:
            progress_callback(f"kita.net 결과: {len(results)}건")

    except Exception as e:
        msg = f"[kita] {type(e).__name__}: {str(e)[:150]}"
        _safe_print(msg)
        if driver:
            try:
                save_screenshot(driver, "kita_error")
                save_debug(driver.page_source, "kita_error", "html")
            except Exception:
                pass
        if progress_callback:
            progress_callback(msg)

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return results


# ═══════════════════════════════════════════════════
#  통합 인터페이스
# ═══════════════════════════════════════════════════

def get_trade_data(hs_code, category_name, start_year=2024, start_month=1, progress_callback=None):
    """
    수출 데이터를 수집합니다.
    1차: tradedata.go.kr 메인 페이지 인라인 데이터 (빠름, 연도별 전체 수출)
    2차: Selenium으로 상세 조회 (품목별 월별)
    3차: kita.net fallback

    Returns: list of dict {날짜, 품목, 수출액(억달러), 구분}
    """
    now = datetime.now()
    current_ym = f"{now.year}-{now.month:02d}"
    results = []

    # ── 1차: 메인 페이지 인라인 데이터 ──
    if progress_callback:
        progress_callback(f"[{category_name}] 1차: 메인 페이지 인라인 데이터 시도...")

    main_data = scrape_tradedata_main(progress_callback)
    if main_data and main_data.get("yearly_export"):
        for year, val_million in sorted(main_data["yearly_export"].items()):
            if year >= start_year:
                # 백만 달러 → 억 달러 (÷100)
                export_billion = round(val_million / 100, 1)
                results.append({
                    "날짜": f"{year}-12",
                    "품목": "전체(총합)",  # 메인 데이터는 전체 수출
                    "수출액(억달러)": export_billion,
                    "구분": "실적"
                })

        if progress_callback:
            progress_callback(f"[{category_name}] 메인 데이터 {len(results)}건 추출")

    # ── 2차: Selenium 상세 조회 ──
    if progress_callback:
        progress_callback(f"[{category_name}] 2차: Selenium 상세 조회 시도...")

    detail_data = scrape_tradedata_detail(hs_code, start_year, start_month, progress_callback)
    if detail_data:
        for item in detail_data:
            export_usd = item.get("export_usd", 0)
            # 단위 판별 및 변환
            if export_usd > 1_000_000_000:
                export_billion = round(export_usd / 100_000_000, 1)
            elif export_usd > 1_000_000:
                export_billion = round(export_usd / 100_000_000, 1)
            elif export_usd > 10_000:
                export_billion = round(export_usd / 100, 1)  # 백만 달러
            else:
                export_billion = round(export_usd, 1)

            is_current = (item["date"] == current_ym)
            results.append({
                "날짜": item["date"],
                "품목": category_name,
                "수출액(억달러)": export_billion if export_billion > 0 else 0,
                "구분": "실적"
            })

        if progress_callback:
            progress_callback(f"[{category_name}] Selenium 상세 {len(detail_data)}건 추가")

    # ── 3차: kita.net fallback ──
    if not detail_data:
        if progress_callback:
            progress_callback(f"[{category_name}] 3차: kita.net fallback...")

        kita_data = scrape_kita(hs_code, start_year, start_month, progress_callback)
        if kita_data:
            for item in kita_data:
                export_usd = item.get("export_usd", 0)
                if export_usd > 1_000_000_000:
                    export_billion = round(export_usd / 100_000_000, 1)
                elif export_usd > 10_000:
                    export_billion = round(export_usd / 100, 1)
                else:
                    export_billion = round(export_usd, 1)

                is_current = (item["date"] == current_ym)
                results.append({
                    "날짜": item["date"],
                    "품목": category_name,
                    "수출액(억달러)": export_billion if export_billion > 0 else 0,
                    "구분": "실적"
                })

            if progress_callback:
                progress_callback(f"[{category_name}] kita.net {len(kita_data)}건 추가")

    # ── 날짜 필터링: 전월(Previous Month)까지만 '실적' 인정 ──
    # 이번 달은 아직 집계 중이므로 제외
    filtered_results = []
    now = datetime.now()
    # 전월 계산: 1월이면 작년 12월
    if now.month == 1:
        prev_year = now.year - 1
        prev_month = 12
    else:
        prev_year = now.year
        prev_month = now.month - 1
    cutoff_ym = f"{prev_year}-{prev_month:02d}"

    for item in results:
        date_val = item.get("날짜")
        if date_val is None:
            continue

        # Ensure string
        if not isinstance(date_val, str):
            date_val = str(date_val)

        if date_val <= cutoff_ym:
            filtered_results.append(item)
        else:
            if progress_callback:
                progress_callback(f"[필터] 제외 (전월 기준): {date_val} (기준: {cutoff_ym})")

    return filtered_results


# ═══════════════════════════════════════════════════
#  테스트
# ═══════════════════════════════════════════════════

def test_scraper():
    """크롤러 테스트"""
    _safe_print("=" * 60)
    _safe_print("  크롤러 테스트")
    _safe_print(f"  디버그 경로: {SCREENSHOT_DIR}")
    _safe_print("=" * 60)

    def progress(msg):
        _safe_print(f"  > {msg}")

    # 1차: 메인 페이지 인라인 데이터
    _safe_print("\n[1] tradedata.go.kr 메인 인라인 데이터")
    main_data = scrape_tradedata_main(progress)
    if main_data:
        _safe_print(f"  연도별 수출: {main_data.get('yearly_export', {})}")
        _safe_print(f"  최신 수출: {main_data.get('latest_export_usd')} (백만달러)")
        _safe_print(f"  국가별: {main_data.get('country_export', {})}")
    else:
        _safe_print("  실패")

    # 2차: Selenium 상세
    _safe_print("\n[2] Selenium 상세 조회 (반도체 HS:85)")
    detail = scrape_tradedata_detail("85", 2024, 1, progress)
    _safe_print(f"  결과: {len(detail)}건")
    for r in detail[:3]:
        _safe_print(f"    {r}")

    # 통합 테스트
    _safe_print("\n[3] 통합 인터페이스 테스트")
    all_data = get_trade_data("85", "반도체", 2024, 1, progress)
    _safe_print(f"  통합 결과: {len(all_data)}건")
    for r in all_data[:5]:
        _safe_print(f"    {r}")

    _safe_print(f"\n  디버그 파일: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    test_scraper()
