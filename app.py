"""
한국 수출 데이터 분석 대시보드
- Streamlit 기반
- Selenium 크롤링 (tradedata.go.kr / kita.net)
- 품목별 수출 실적 시각화
- CSV 데이터 누적 저장
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_manager import (
    load_data, update_data_with_scraping,
    add_forecast, save_data, CATEGORIES,
    ensure_historical_data, sanitize_dataframe,
    get_cutoff_ym
)
from datetime import datetime
import os

# ── 페이지 설정 ──
st.set_page_config(
    page_title="한국 수출 데이터 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── 커스텀 CSS ──
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #1a4a72 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 8px 32px rgba(30, 58, 95, 0.3);
    }
    .main-header h1 {
        font-size: 1.8rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header p {
        font-size: 0.95rem;
        opacity: 0.85;
        margin: 0.3rem 0 0 0;
    }

    .kpi-card {
        background: white;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        border-left: 4px solid;
        transition: transform 0.2s;
    }
    .kpi-card:hover { transform: translateY(-2px); }
    .kpi-label {
        font-size: 0.8rem; color: #6b7280;
        font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .kpi-value { font-size: 1.6rem; font-weight: 800; margin: 0.2rem 0; }
    .kpi-change { font-size: 0.85rem; font-weight: 600; }
    .kpi-up { color: #10b981; }
    .kpi-down { color: #ef4444; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    }

    .stButton>button { width: 100%; }

    hr { border: none; border-top: 1px solid #e5e7eb; margin: 1rem 0; }

    .source-badge {
        padding: 0.4rem 0.8rem;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        margin-top: 0.3rem;
    }
    .source-live {
        background: #d1fae5; color: #065f46;
    }
    .source-dummy {
        background: #fef3c7; color: #92400e;
    }
</style>
""", unsafe_allow_html=True)


# ── 데이터 로드 (CSV 캐시 → 빠른 재접속) ──
@st.cache_data(ttl=3600)
def get_data():
    df = load_data()
    # 과거 데이터 보장 (부족하면 자동 생성)
    df, _ = ensure_historical_data(df)
    # 타입 정제 (문자열 → float)
    df = sanitize_dataframe(df)
    if len(df) > 0:
        df = add_forecast(df, months_ahead=3)
    return df


def main():
    # ── 사이드바 ──
    with st.sidebar:
        st.markdown("### 📊 대시보드 설정")
        st.divider()

        # 품목 선택
        categories = list(CATEGORIES.keys())
        selected_category = st.selectbox(
            "🏭 수출 품목 선택",
            categories,
            index=0,
            help="분석할 수출 품목을 선택하세요"
        )

        st.divider()

        # 기간 필터
        st.markdown("##### 📅 기간 설정")
        year_range = st.slider(
            "연도 범위",
            min_value=2024,
            max_value=2027,
            value=(2024, 2027)
        )

        st.divider()

        # ── 데이터 관리 ──
        st.markdown("##### 🔄 데이터 관리")
        st.caption("tradedata.go.kr / kita.net 크롤링")

        if st.button("🔄 데이터 업데이트", type="primary"):
            status_area = st.empty()
            progress_bar = st.progress(0)
            log_area = st.empty()
            logs = []

            def progress_callback(msg):
                logs.append(msg)
                status_area.markdown(f"**{msg}**")
                progress = min(len(logs) / 30, 0.95)
                progress_bar.progress(progress)
                log_area.text("\n".join(logs[-5:]))

            progress_callback("크롤링 시작...")
            result = update_data_with_scraping(progress_callback)
            progress_bar.progress(1.0)

            if result is not None:
                st.cache_data.clear()
                status_area.success("✅ 크롤링 데이터 업데이트 완료!")
            else:
                status_area.error("❌ 크롤링 실패. 사이트 접속을 확인하세요.")

            st.rerun()

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🗑️ 초기화", help="모든 데이터 삭제 후 새로 시작"):
                data_file = os.path.join(os.path.dirname(__file__), "export_data.csv")
                if os.path.exists(data_file):
                    os.remove(data_file)
                st.cache_data.clear()
                st.success("✅ 초기화 완료!")
                st.rerun()

        with col_btn2:
            df_all = get_data()
            csv = df_all.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "📥 CSV",
                csv,
                "export_data.csv",
                "text/csv",
                "text/csv"
            )

        st.divider()
        st.markdown(
            f"<small>마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}</small>",
            unsafe_allow_html=True
        )

    # ── 메인 영역 ──
    st.markdown(f"""
    <div class="main-header">
        <h1>🇰🇷 한국 수출 데이터 분석 및 예측 대시보드</h1>
        <p>품목별 월간 수출 실적 및 향후 예측 분석 | 데이터 기준: 2024년 1월 ~ | 🌐 tradedata.go.kr 크롤링</p>
    </div>
    """, unsafe_allow_html=True)

    # 데이터 로드
    df = get_data()

    # 데이터 없으면 안내 메시지
    if len(df) == 0:
        st.info("📭 저장된 데이터가 없습니다. 사이드바의 **🔄 데이터 업데이트** 버튼을 눌러 크롤링을 시작하세요.")
        st.stop()

    # 선택 품목 필터링
    cat_df = df[df["품목"] == selected_category].copy()
    cat_df["날짜_dt"] = pd.to_datetime(cat_df["날짜"] + "-01")

    # 연도 필터 적용
    cat_df = cat_df[
        (cat_df["날짜_dt"].dt.year >= year_range[0]) &
        (cat_df["날짜_dt"].dt.year <= year_range[1])
    ]

    # 전월 기준 cutoff (이번 달은 집계 중이므로 제외)
    cutoff_ym = get_cutoff_ym()
    
    # 실적: 전월까지만
    actual_df = cat_df[
        (cat_df["구분"] == "실적") & 
        (cat_df["날짜"] <= cutoff_ym)
    ].sort_values("날짜")
    
    # 예측: 전월 이후 날짜 또는 구분='예측'
    forecast_df = cat_df[
        (cat_df["구분"] == "예측") | 
        (cat_df["날짜"] > cutoff_ym)
    ].sort_values("날짜")

    # ── KPI 카드 ──
    if len(actual_df) >= 2:
        latest_value = actual_df.iloc[-1]["수출액(억달러)"]
        prev_value = actual_df.iloc[-2]["수출액(억달러)"]
        change_pct = ((latest_value - prev_value) / prev_value) * 100 if prev_value != 0 else 0
        yoy_value = None

        latest_date = actual_df.iloc[-1]["날짜"]
        latest_dt = pd.to_datetime(latest_date + "-01")
        yoy_date = (latest_dt - pd.DateOffset(years=1)).strftime("%Y-%m")
        yoy_row = actual_df[actual_df["날짜"] == yoy_date]
        if len(yoy_row) > 0 and yoy_row.iloc[0]["수출액(억달러)"] != 0:
            yoy_value = ((latest_value - yoy_row.iloc[0]["수출액(억달러)"]) / yoy_row.iloc[0]["수출액(억달러)"]) * 100

        latest_year = latest_dt.year
        ytd = actual_df[actual_df["날짜_dt"].dt.year == latest_year]["수출액(억달러)"].sum()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            ch_cls = "kpi-up" if change_pct >= 0 else "kpi-down"
            ch_arr = "▲" if change_pct >= 0 else "▼"
            st.markdown(f"""
            <div class="kpi-card" style="border-color: #3b82f6;">
                <div class="kpi-label">최신 실적 ({latest_date})</div>
                <div class="kpi-value" style="color: #1e3a5f;">{latest_value}억$</div>
                <div class="kpi-change {ch_cls}">{ch_arr} 전월 대비 {abs(change_pct):.1f}%</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            if yoy_value is not None:
                y_cls = "kpi-up" if yoy_value >= 0 else "kpi-down"
                y_arr = "▲" if yoy_value >= 0 else "▼"
                st.markdown(f"""
                <div class="kpi-card" style="border-color: #8b5cf6;">
                    <div class="kpi-label">전년 동월 대비</div>
                    <div class="kpi-value" style="color: #6d28d9;">{y_arr} {abs(yoy_value):.1f}%</div>
                    <div class="kpi-change" style="color: #6b7280;">YoY 변화율</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="kpi-card" style="border-color: #8b5cf6;">
                    <div class="kpi-label">전년 동월 대비</div>
                    <div class="kpi-value" style="color: #6d28d9;">-</div>
                    <div class="kpi-change" style="color: #6b7280;">데이터 부족</div>
                </div>
                """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
            <div class="kpi-card" style="border-color: #10b981;">
                <div class="kpi-label">{latest_year}년 누적 수출</div>
                <div class="kpi-value" style="color: #047857;">{ytd:,.1f}억$</div>
                <div class="kpi-change" style="color: #6b7280;">YTD 합계</div>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            if len(forecast_df) > 0:
                nf = forecast_df.iloc[0]["수출액(억달러)"]
                st.markdown(f"""
                <div class="kpi-card" style="border-color: #f59e0b;">
                    <div class="kpi-label">다음 월 예측</div>
                    <div class="kpi-value" style="color: #d97706;">{nf}억$</div>
                    <div class="kpi-change" style="color: #6b7280;">3개월 이동평균 기반</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="kpi-card" style="border-color: #f59e0b;">
                    <div class="kpi-label">다음 월 예측</div>
                    <div class="kpi-value" style="color: #d97706;">-</div>
                    <div class="kpi-change" style="color: #6b7280;">예측 없음</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 메인 차트 ──
    st.markdown(f"### 📈 {selected_category} 월별 수출 추이")

    fig = go.Figure()

    if len(actual_df) > 0:
        fig.add_trace(go.Scatter(
            x=actual_df["날짜"], y=actual_df["수출액(억달러)"],
            mode="lines+markers", name="실적 (Actual)",
            line=dict(color="#3b82f6", width=3),
            marker=dict(size=7, color="#3b82f6"),
            hovertemplate="<b>%{x}</b><br>수출액: %{y}억$<extra>실적</extra>"
        ))

    if len(actual_df) > 0 and len(forecast_df) > 0:
        bridge_df = pd.concat([actual_df.tail(1), forecast_df.head(1)])
        fig.add_trace(go.Scatter(
            x=bridge_df["날짜"], y=bridge_df["수출액(억달러)"],
            mode="lines", name="_bridge",
            line=dict(color="#ef4444", width=2, dash="dot"),
            showlegend=False, hoverinfo="skip"
        ))

    if len(forecast_df) > 0:
        fig.add_trace(go.Scatter(
            x=forecast_df["날짜"], y=forecast_df["수출액(억달러)"],
            mode="lines+markers", name="예측 (Forecast)",
            line=dict(color="#ef4444", width=2, dash="dot"),
            marker=dict(size=7, color="#ef4444", symbol="diamond"),
            hovertemplate="<b>%{x}</b><br>예측: %{y}억$<extra>예측</extra>"
        ))



    fig.update_layout(
        height=500, plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Noto Sans KR, sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=13)),
        xaxis=dict(title="", gridcolor="#f3f4f6", tickformat="%Y-%m", dtick="M1", tickangle=-45),
        yaxis=dict(title="수출액 (억 달러)", gridcolor="#f3f4f6", zeroline=False, autorange=True),
        margin=dict(l=60, r=20, t=40, b=60),
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── 상세 테이블 ──
    st.markdown(f"### 📋 {selected_category} 월별 상세 데이터")

    display_df = cat_df[["날짜", "수출액(억달러)", "구분"]].copy()
    display_df = display_df.sort_values("날짜", ascending=False).reset_index(drop=True)

    st.dataframe(
        display_df,
        height=400,
        hide_index=True,
        column_config={
            "날짜": st.column_config.TextColumn("📅 날짜"),
            "수출액(억달러)": st.column_config.NumberColumn("💰 수출액 (억 달러)", format="%.1f"),
            "구분": st.column_config.TextColumn("📌 구분"),
        }
    )

    # ── 전체 품목 비교 ──
    st.markdown("### 🏭 품목별 최신 실적 비교")

    comparison_rows = []
    for cat in CATEGORIES.keys():
        cat_actual = df[(df["품목"] == cat) & (df["구분"] == "실적")].sort_values("날짜")
        if len(cat_actual) >= 2:
            latest = cat_actual.iloc[-1]
            prev = cat_actual.iloc[-2]
            pv = prev["수출액(억달러)"]
            change = ((latest["수출액(억달러)"] - pv) / pv) * 100 if pv != 0 else 0
            comparison_rows.append({
                "품목": cat,
                "최신 실적(억$)": latest["수출액(억달러)"],
                "기준 월": latest["날짜"],
                "전월 대비(%)": round(change, 1)
            })

    if comparison_rows:
        comp_df = pd.DataFrame(comparison_rows).sort_values("최신 실적(억$)", ascending=False)

        fig2 = go.Figure()
        colors = ["#3b82f6" if v >= 0 else "#ef4444" for v in comp_df["전월 대비(%)"]]

        fig2.add_trace(go.Bar(
            x=comp_df["품목"], y=comp_df["최신 실적(억$)"],
            marker_color=colors,
            text=comp_df["최신 실적(억$)"].apply(lambda x: f"{x}억$"),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>수출액: %{y}억$<extra></extra>"
        ))

        fig2.update_layout(
            height=400, plot_bgcolor="white", paper_bgcolor="white",
            font=dict(family="Noto Sans KR, sans-serif"),
            xaxis=dict(title=""), yaxis=dict(title="수출액 (억 달러)", gridcolor="#f3f4f6"),
            margin=dict(l=60, r=20, t=20, b=60), showlegend=False
        )

        st.plotly_chart(fig2, use_container_width=True)

    # ── 푸터 ──
    st.divider()
    source_name = "tradedata.go.kr / kita.net 크롤링"
    st.markdown(f"""
    <div style="text-align:center; color:#9ca3af; font-size:0.8rem; padding:1rem 0;">
        📊 한국 수출 데이터 대시보드 | 데이터 출처: {source_name}<br>
        예측: 3개월 이동평균 + 트렌드 보정 | 크롤링: Selenium (Chrome)
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
