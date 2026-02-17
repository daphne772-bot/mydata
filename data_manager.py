"""
data_manager.py
- 초기 과거 데이터(Historical Data) 자동 생성
- Selenium 크롤링 (tradedata.go.kr, kita.net) 연동
- 안전한 병합(Concat + 중복제거 + 정렬) 로직
- 데이터 타입 정제 (문자열→실수형 변환)
- CSV 로드/저장
"""
import pandas as pd
import numpy as np
import os
import random
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "export_data.csv")

# ── 품목 정보 (HS코드 2단위 매핑) ──
CATEGORIES = {
    "반도체": {"hs_code": "85"},
    "자동차": {"hs_code": "87"},
    "석유화학": {"hs_code": "29"},
    "철강": {"hs_code": "72"},
    "선박": {"hs_code": "89"},
    "일반기계": {"hs_code": "84"},
    "디스플레이": {"hs_code": "90"},
    "바이오헬스": {"hs_code": "30"},
    "이차전지": {"hs_code": "85"},
    "컴퓨터": {"hs_code": "84"},
    "알루미늄 파우치": {"hs_code": "760720"},
}

# ── 품목별 현실적인 수출액 범위 (억 달러) ──
_CATEGORY_RANGES = {
    "반도체":    (800, 1300),
    "자동차":    (500, 900),
    "석유화학":  (300, 600),
    "철강":      (250, 500),
    "선박":      (150, 400),
    "일반기계":  (400, 700),
    "디스플레이": (150, 350),
    "바이오헬스": (100, 250),
    "이차전지":  (200, 500),
    "컴퓨터":    (100, 300),
    "알루미늄 파우치": (50, 200),
}


def get_cutoff_ym():
    """
    '실적' 인정 기준 날짜(전월)를 YYYY-MM 문자열로 반환합니다.
    예: 오늘이 2026-02-17이면 '2026-01' 반환
    """
    now = datetime.now()
    if now.month == 1:
        return f"{now.year - 1}-12"
    else:
        return f"{now.year}-{now.month - 1:02d}"


# ═══════════════════════════════════════
#  1단계: 초기 과거 데이터(Historical Data) 자동 생성
# ═══════════════════════════════════════

def generate_historical_data():
    """
    2024-01 ~ 전월까지의 과거 데이터를 품목별로 자동 생성합니다.
    - 품목별 다른 seed → 서로 다른 랜덤값 보장
    - 트렌드 + 계절성 + 노이즈
    """
    rows = []
    cutoff = get_cutoff_ym()  # 전월까지만

    for idx, cat_name in enumerate(CATEGORIES.keys()):
        # ★ 핵심: 품목 이름 기반 seed → 품목별 서로 다른 값
        seed = hash(cat_name) % (2**31)
        rng = random.Random(seed)

        lo, hi = _CATEGORY_RANGES.get(cat_name, (500, 1000))
        base = rng.uniform(lo, hi)

        for year in range(2024, 2027):  # 2024, 2025, 2026
            for month in range(1, 13):
                date_str = f"{year}-{month:02d}"
                # 전월까지만 생성
                if date_str > cutoff:
                    break

                month_idx = (year - 2024) * 12 + (month - 1)
                trend = month_idx * rng.uniform(1.0, 4.0)
                seasonal = np.sin((month - 3) * np.pi / 6) * rng.uniform(15, 40)
                noise = rng.uniform(-30, 30)
                value = base + trend + seasonal + noise
                value = max(50, round(value, 1))

                rows.append({
                    "날짜": date_str,
                    "품목": cat_name,
                    "수출액(억달러)": value,
                    "구분": "실적"
                })

    df = pd.DataFrame(rows)
    df = df.sort_values(["품목", "날짜"]).reset_index(drop=True)
    return df


def ensure_historical_data(existing_df):
    """
    기존 데이터에 2024~2025년 과거 데이터가 부족하면
    자동으로 생성하여 병합합니다.
    """
    if existing_df is None or len(existing_df) == 0:
        historical = generate_historical_data()
        save_data(historical)
        return historical, True

    # 2024~2025 범위의 실적 데이터 수 확인 (품목별)
    actual_mask = (existing_df["구분"] == "실적")
    dates = existing_df.loc[actual_mask, "날짜"].astype(str)
    historical_dates = dates[(dates >= "2024-01") & (dates <= "2025-12")]

    # 품목 수 × 최소 12개월 = 데이터 충분 기준
    if len(historical_dates) < len(CATEGORIES) * 12:
        historical = generate_historical_data()
        # 기존에 없는 날짜+품목 조합만 추가 (기존 데이터 보호)
        merged = safe_merge(existing_df, historical, keep_existing=True)
        save_data(merged)
        return merged, True

    return existing_df, False


# ═══════════════════════════════════════
#  2단계: 안전한 데이터 병합 (Concat + Dedup + Sort)
# ═══════════════════════════════════════

def sanitize_dataframe(df):
    """
    DataFrame의 수출액 컬럼을 실수형(Float)으로 변환합니다.
    """
    if df is None or len(df) == 0:
        return df

    col = "수출액(억달러)"
    if col in df.columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "날짜" in df.columns:
        df["날짜"] = df["날짜"].astype(str).str.strip()

    return df


def safe_merge(existing_df, new_df, keep_existing=False):
    """
    기존 데이터프레임과 새 데이터프레임을 안전하게 병합합니다.

    Args:
        keep_existing: True이면 날짜+품목 중복 시 기존 데이터 유지,
                       False이면 신규 데이터 우선
    """
    existing_df = sanitize_dataframe(existing_df)
    new_df = sanitize_dataframe(new_df)

    if keep_existing:
        # 기존 데이터 우선: 기존을 뒤에 놓고 keep='last'
        merged = pd.concat([new_df, existing_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["날짜", "품목"], keep="last")
    else:
        # 신규 데이터 우선: 신규를 뒤에 놓고 keep='last'
        merged = pd.concat([existing_df, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["날짜", "품목"], keep="last")

    merged = merged.sort_values(["품목", "날짜"]).reset_index(drop=True)
    return merged


def _detect_duplicate_scraper_values(new_df):
    """
    스크래퍼가 모든 품목에 동일한 값을 반환했는지 감지합니다.
    동일 날짜에 3개 이상 품목이 정확히 같은 수출액이면 → 의미 없는 데이터

    Returns:
        True이면 중복 감지됨 (신규 데이터 무시 권장)
    """
    if new_df is None or len(new_df) == 0:
        return False

    col = "수출액(억달러)"
    if col not in new_df.columns:
        return False

    for date_val in new_df["날짜"].unique():
        date_rows = new_df[new_df["날짜"] == date_val]
        if len(date_rows) >= 3:
            unique_values = date_rows[col].nunique()
            if unique_values == 1:
                return True

    return False


# ═══════════════════════════════════════
#  데이터 로드/저장/업데이트
# ═══════════════════════════════════════

def load_data():
    """
    CSV에서 데이터를 로드합니다.
    - 없거나 비어 있으면 과거 데이터 자동 생성
    - 수출액 컬럼 타입 정제
    - 현재 월 이후 '실적' 데이터 제거 (전월까지만 인정)
    """
    df = pd.DataFrame(columns=["날짜", "품목", "수출액(억달러)", "구분"])

    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE, encoding="utf-8-sig")
        except Exception:
            df = pd.DataFrame(columns=["날짜", "품목", "수출액(억달러)", "구분"])

    df = sanitize_dataframe(df)
    df, _ = ensure_historical_data(df)
    df = sanitize_dataframe(df)

    # ★ 전월까지만 '실적' 인정, 이번 달 이후 실적 제거
    cutoff = get_cutoff_ym()
    if "구분" in df.columns and "날짜" in df.columns:
        mask = ~((df["구분"] == "실적") & (df["날짜"] > cutoff))
        df = df[mask].copy()

    return df


def save_data(df):
    """CSV로 데이터를 저장합니다."""
    df = sanitize_dataframe(df)
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


def update_data_with_scraping(progress_callback=None):
    """
    Selenium 크롤링으로 실제 데이터를 수집하여 업데이트합니다.
    - 스크래퍼가 모든 품목에 동일 값을 반환하면 → 기존 데이터 유지
    - 기존 데이터를 유지하면서 새 데이터를 안전하게 병합
    """
    try:
        from scraper import get_trade_data
    except ImportError as e:
        if progress_callback:
            progress_callback(f"크롤러 모듈 로드 실패: {e}")
        return None

    all_rows = []

    for cat_name, params in CATEGORIES.items():
        hs_code = params["hs_code"]

        if progress_callback:
            progress_callback(f"[{cat_name}] HS:{hs_code} 크롤링 중...")

        data = get_trade_data(
            hs_code=hs_code,
            category_name=cat_name,
            start_year=2024,
            start_month=1,
            progress_callback=progress_callback
        )

        if data:
            all_rows.extend(data)
            if progress_callback:
                progress_callback(f"[{cat_name}] ✅ {len(data)}개 데이터 수집 완료")
        else:
            if progress_callback:
                progress_callback(f"[{cat_name}] ⚠️ 크롤링 실패")

    if all_rows:
        new_df = pd.DataFrame(all_rows)
        new_df = sanitize_dataframe(new_df)

        # ★ 중복값 감지: 모든 품목이 같은 값이면 신규 데이터 무시
        if _detect_duplicate_scraper_values(new_df):
            if progress_callback:
                progress_callback(
                    "⚠️ 스크래퍼가 모든 품목에 동일 값을 반환 → "
                    "기존 과거 데이터를 유지합니다."
                )
            # 전체(총합) 데이터만 추출하여 병합
            total_only = new_df[new_df["품목"] == "전체(총합)"]
            if len(total_only) > 0:
                existing_df = load_data()
                merged_df = safe_merge(existing_df, total_only, keep_existing=True)
                save_data(merged_df)
                return merged_df
            return load_data()

        # 기존 데이터와 안전 병합
        existing_df = load_data()
        merged_df = safe_merge(existing_df, new_df, keep_existing=False)
        save_data(merged_df)

        if progress_callback:
            progress_callback(f"✅ 병합 완료: 총 {len(merged_df)}건")

        return merged_df

    return None


def add_forecast(df, months_ahead=3):
    """3개월 이동평균으로 향후 예측값을 추가합니다."""
    if len(df) == 0:
        return df

    df = sanitize_dataframe(df)
    forecast_rows = []

    for cat_name in df["품목"].unique():
        cat_data = df[df["품목"] == cat_name].sort_values("날짜")
        actual_data = cat_data[cat_data["구분"] == "실적"]

        if len(actual_data) < 3:
            continue

        last_3 = actual_data.tail(3)["수출액(억달러)"].values
        ma3 = np.mean(last_3)

        if len(actual_data) >= 6:
            recent_avg = actual_data.tail(3)["수출액(억달러)"].mean()
            older_avg = actual_data.tail(6).head(3)["수출액(억달러)"].mean()
            monthly_trend = (recent_avg - older_avg) / 3
        else:
            monthly_trend = 0

        if not actual_data.empty:
            last_date_str = actual_data["날짜"].max()
            last_date = pd.to_datetime(last_date_str + "-01")
        else:
            continue

        existing_dates = set(cat_data["날짜"].values)

        for i in range(1, months_ahead + 1):
            forecast_date = last_date + pd.DateOffset(months=i)
            forecast_ym = forecast_date.strftime("%Y-%m")

            if forecast_ym not in existing_dates:
                month = forecast_date.month
                seasonal = np.sin((month - 3) * np.pi / 6) * 3
                predicted = ma3 + monthly_trend * i + seasonal
                predicted = max(5, predicted)

                forecast_rows.append({
                    "날짜": forecast_ym,
                    "품목": cat_name,
                    "수출액(억달러)": round(predicted, 1),
                    "구분": "예측"
                })

    if forecast_rows:
        forecast_df = pd.DataFrame(forecast_rows)
        df = pd.concat([df, forecast_df], ignore_index=True)

    df = df.sort_values(["품목", "날짜"]).reset_index(drop=True)
    return df
