import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# ──────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="용접불량률 현황 대시보드",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# 커스텀 CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
    /* 메트릭 카드 스타일링 */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="stMetric"] label {
        color: #8ec8f8 !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    /* 헤더 */
    .main-header {
        background: linear-gradient(135deg, #0d1b2a 0%, #1b2838 50%, #1e3a5f 100%);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 24px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .main-header h1 {
        color: #ffffff;
        font-size: 1.8rem;
        margin: 0;
    }
    .main-header p {
        color: #8ec8f8;
        font-size: 0.95rem;
        margin: 4px 0 0 0;
    }
    /* 섹션 리본 */
    .section-label {
        background: linear-gradient(90deg, #1e3a5f, transparent);
        color: #8ec8f8;
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        margin-bottom: 12px;
        display: inline-block;
    }
    /* 데이터프레임 스타일 */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        overflow: hidden;
    }
    /* 사이드바 */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1b2a 0%, #1b2838 100%);
    }
    /* 사이드바 새로고침 버튼 */
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
        background: linear-gradient(135deg, #2d8cf0 0%, #1e6fd0 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 14px 20px !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 15px rgba(45, 140, 240, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
        background: linear-gradient(135deg, #3d9cff 0%, #2d8cf0 100%) !important;
        box-shadow: 0 6px 20px rgba(45, 140, 240, 0.5) !important;
        transform: translateY(-1px);
    }
    /* 사이드바 카드 */
    .sidebar-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .sidebar-card h4 {
        color: #8ec8f8;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0 0 10px 0;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    /* 사이드바 요약 수치 */
    .sidebar-stat {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .sidebar-stat:last-child { border-bottom: none; }
    .sidebar-stat .label { color: #8ec8f8; font-size: 0.85rem; }
    .sidebar-stat .value { color: #ffffff; font-weight: 700; font-size: 1rem; }
    /* 멀티셀렉트 태그 색상 */
    span[data-baseweb="tag"] {
        background-color: rgba(100, 180, 255, 0.25) !important;
        border-color: rgba(100, 180, 255, 0.4) !important;
        color: #8ec8f8 !important;
    }
    span[data-baseweb="tag"] span { color: #8ec8f8 !important; }
    span[data-baseweb="tag"] svg { fill: #8ec8f8 !important; }
    /* 파일 수정 시간 배지 */
    .update-badge {
        background: rgba(46, 204, 113, 0.15);
        border: 1px solid rgba(46, 204, 113, 0.3);
        border-radius: 8px;
        padding: 8px 12px;
        margin-top: 8px;
        text-align: center;
        font-size: 0.8rem;
        color: #2ecc71;
    }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 데이터 로드 및 전처리
# ──────────────────────────────────────────────
@st.cache_data(ttl=300)  # 5분마다 캐시 자동 만료
def load_data(_file_mtime=None):
    """Excel 데이터를 로드하고 전처리. _file_mtime은 캐시 무효화용 파라미터."""
    file_path = os.path.join(os.path.dirname(__file__), "welding data.xlsx")
    
    # 상단 3행 건너뛰기 → 4번째 행을 헤더로
    df = pd.read_excel(file_path, header=None, skiprows=3)
    
    # 불필요한 빈 컬럼 제거 (열 0, 1, 17, 18)
    cols_to_drop = [c for c in [0, 1, 17, 18] if c in df.columns]
    df = df.drop(columns=cols_to_drop)
    df = df.reset_index(drop=True)
    
    # 컬럼명 재설정 (구분/소속, 목표, 당일×4, 당월×4, 누계×4)
    new_columns = [
        "소속", "구분_sub", "목표",
        "당일_검사", "당일_불량", "당일_불량률", "당일_달성률",
        "당월_검사", "당월_불량", "당월_불량률", "당월_달성률",
        "누계_검사", "누계_불량", "누계_불량률", "누계_달성률",
    ]
    
    # 실제 컬럼 수에 맞게 처리
    if len(df.columns) == 15:
        df.columns = new_columns
    else:
        # 컬럼 수가 다를 경우 안전하게 처리
        actual_cols = list(df.columns)
        mapping = {}
        # 첫 번째 행(헤더 행) 확인
        header_row = df.iloc[0]
        
        # 기본 매핑: 열 인덱스 기반
        col_names = [
            "소속", "목표",
            "당일_검사", "당일_불량", "당일_불량률", "당일_달성률",
            "당월_검사", "당월_불량", "당월_불량률", "당월_달성률",
            "누계_검사", "누계_불량", "누계_불량률", "누계_달성률",
        ]
        for i, name in enumerate(col_names):
            if i < len(actual_cols):
                mapping[actual_cols[i]] = name
        df = df.rename(columns=mapping)
    
    # 첫 번째 행은 헤더(소속, 목표, 검사...) 이므로 제거
    df = df.iloc[1:]
    
    # 구분_sub 열이 있으면 소속 열과 병합 후 제거
    if "구분_sub" in df.columns:
        df["소속"] = df["소속"].fillna(df["구분_sub"])
        df = df.drop(columns=["구분_sub"])
    
    # 소속이 NaN인 행 제거
    df = df.dropna(subset=["소속"])
    
    # 소속이 비어있거나 메타 텍스트가 포함된 행 제거
    exclude_keywords = ["■", "○", "구분", "월별", "소속", "목표"]
    df = df[~df["소속"].astype(str).str.contains("|".join(exclude_keywords), na=False)]
    
    # 목표 열이 NaN인 행 제거 (하단 월별 추이 데이터 등)
    df = df.dropna(subset=["목표"])
    
    # 숫자 컬럼 변환
    numeric_cols = [c for c in df.columns if c not in ["소속"]]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # 인덱스 리셋
    df = df.reset_index(drop=True)
    
    return df


# ──────────────────────────────────────────────
# 메인 앱
# ──────────────────────────────────────────────
def main():
    # 데이터 로드 (파일 수정 시간을 캐시 키로 사용하여 변경 시 자동 갱신)
    file_path = os.path.join(os.path.dirname(__file__), "welding data.xlsx")
    try:
        file_mtime = os.path.getmtime(file_path)
        df = load_data(_file_mtime=file_mtime)
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()
    
    # ── 사이드바 ──
    with st.sidebar:
        st.markdown("")
        
        # 새로고침 버튼 (큰 사이즈)
        if st.button("🔄  데이터 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        last_updated = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d %H:%M:%S")
        st.markdown(
            f'<div class="update-badge">📅 마지막 업데이트: {last_updated}</div>',
            unsafe_allow_html=True,
        )
        
        st.markdown("")
        
        # 기간 선택
        st.markdown(
            '<div class="sidebar-card"><h4>📅 기간 선택</h4></div>',
            unsafe_allow_html=True,
        )
        period_option = st.radio(
            "기간",
            ["당일", "당월", "누계"],
            index=1,
            horizontal=True,
            label_visibility="collapsed",
        )
        
        st.markdown("")
        
        # 소속 필터
        st.markdown(
            '<div class="sidebar-card"><h4>📋 소속 필터</h4></div>',
            unsafe_allow_html=True,
        )
        all_departments = sorted(df["소속"].unique().tolist())
        selected = st.multiselect(
            "소속 선택",
            options=all_departments,
            default=all_departments,
            label_visibility="collapsed",
        )
        
        st.markdown("")
        
        # 데이터 요약 카드
        st.markdown(f'''
        <div class="sidebar-card">
            <h4>📊 데이터 요약</h4>
            <div class="sidebar-stat">
                <span class="label">전체 소속</span>
                <span class="value">{len(all_departments)}개</span>
            </div>
            <div class="sidebar-stat">
                <span class="label">선택 소속</span>
                <span class="value">{len(selected)}개</span>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    
    # 필터 적용
    if selected:
        filtered_df = df[df["소속"].isin(selected)].copy()
    else:
        filtered_df = df.copy()
    
    # ── 헤더 ──
    st.markdown("""
    <div class="main-header">
        <h1>🔧 용접불량률 현황 대시보드</h1>
        <p>실시간 용접 품질 모니터링 · 소속별 불량률 & 달성률 현황</p>
    </div>
    """, unsafe_allow_html=True)
    
    # ── KPI 카드 ──
    prefix = period_option  # 당일 / 당월 / 누계
    
    col_defect = f"{prefix}_불량률"
    col_achieve = f"{prefix}_달성률"
    col_inspect = f"{prefix}_검사"
    col_defect_cnt = f"{prefix}_불량"
    
    # 전략팀 행 찾기 (전략팀 또는 전계장)
    summary_row = filtered_df[filtered_df["소속"].str.contains("전략|전계", na=False)]
    
    # 주요 소속 식별
    kpi_sources = {}
    for dept in ["가공", "건조", "의장"]:
        match = filtered_df[filtered_df["소속"] == dept]
        if not match.empty:
            kpi_sources[dept] = match.iloc[0]
    
    # KPI 행
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    # 전체 평균 불량률
    total_inspect = filtered_df[col_inspect].sum()
    total_defect = filtered_df[col_defect_cnt].sum()
    avg_defect_rate = (total_defect / total_inspect * 100) if total_inspect > 0 else 0
    
    with kpi1:
        st.metric(
            label=f"📊 전체 {prefix} 불량률",
            value=f"{avg_defect_rate:.2f}%",
        )
    
    with kpi2:
        if "가공" in kpi_sources:
            val = kpi_sources["가공"][col_defect]
            achieve = kpi_sources["가공"][col_achieve]
            st.metric(
                label=f"🏭 가공 {prefix} 불량률",
                value=f"{val:.2f}%",
                delta=f"달성률 {achieve:.1f}%",
                delta_color="inverse",
            )
        else:
            st.metric(label=f"🏭 가공 {prefix} 불량률", value="N/A")
    
    with kpi3:
        if "건조" in kpi_sources:
            val = kpi_sources["건조"][col_defect]
            achieve = kpi_sources["건조"][col_achieve]
            st.metric(
                label=f"🏗️ 건조 {prefix} 불량률",
                value=f"{val:.2f}%",
                delta=f"달성률 {achieve:.1f}%",
                delta_color="inverse",
            )
        else:
            st.metric(label=f"🏗️ 건조 {prefix} 불량률", value="N/A")
    
    with kpi4:
        if not summary_row.empty:
            val = summary_row.iloc[0][col_defect]
            achieve = summary_row.iloc[0][col_achieve]
            st.metric(
                label=f"📋 전략팀 {prefix} 불량률",
                value=f"{val:.2f}%",
                delta=f"달성률 {achieve:.1f}%",
                delta_color="inverse",
            )
        else:
            avg_achieve = filtered_df[col_achieve].mean()
            st.metric(
                label=f"📋 전체 {prefix} 달성률",
                value=f"{avg_achieve:.1f}%",
            )
    
    st.markdown("")
    
    # ── 차트 영역 ──
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown('<div class="section-label">📊 소속별 불량률 비교</div>', unsafe_allow_html=True)
        
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=filtered_df["소속"],
            y=filtered_df[col_defect],
            name="불량률 (%)",
            marker=dict(
                color=filtered_df[col_defect],
                colorscale=[[0, "#2d8cf0"], [0.5, "#f5a623"], [1, "#e74c3c"]],
                line=dict(width=0),
                cornerradius=4,
            ),
            text=filtered_df[col_defect].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else ""),
            textposition="outside",
            textfont=dict(size=11, color="#ffffff"),
        ))
        
        # 목표선
        target_val = filtered_df["목표"].mean() if not filtered_df.empty else 0.6
        fig1.add_hline(
            y=target_val, line_dash="dash", line_color="#e74c3c", line_width=2,
            annotation_text=f"목표: {target_val:.1f}%",
            annotation_position="top right",
            annotation_font=dict(color="#e74c3c", size=12),
        )
        
        fig1.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=420,
            margin=dict(l=40, r=20, t=40, b=60),
            xaxis=dict(title="소속", tickangle=-30),
            yaxis=dict(title="불량률 (%)"),
            showlegend=False,
        )
        st.plotly_chart(fig1, width="stretch")
    
    with chart_col2:
        st.markdown('<div class="section-label">🎯 소속별 달성률 비교</div>', unsafe_allow_html=True)
        
        fig2 = go.Figure()
        
        # 달성률 100% 기준 색상
        colors = []
        for val in filtered_df[col_achieve]:
            if pd.isna(val):
                colors.append("#555555")
            elif val >= 100:
                colors.append("#2ecc71")
            elif val >= 50:
                colors.append("#f5a623")
            else:
                colors.append("#e74c3c")
        
        fig2.add_trace(go.Bar(
            x=filtered_df["소속"],
            y=filtered_df[col_achieve],
            name="달성률 (%)",
            marker=dict(color=colors, line=dict(width=0), cornerradius=4),
            text=filtered_df[col_achieve].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else ""),
            textposition="outside",
            textfont=dict(size=11, color="#ffffff"),
        ))
        
        # 100% 기준선
        fig2.add_hline(
            y=100, line_dash="dash", line_color="#2ecc71", line_width=2,
            annotation_text="목표 달성 (100%)",
            annotation_position="top right",
            annotation_font=dict(color="#2ecc71", size=12),
        )
        
        fig2.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=420,
            margin=dict(l=40, r=20, t=40, b=60),
            xaxis=dict(title="소속", tickangle=-30),
            yaxis=dict(title="달성률 (%)"),
            showlegend=False,
        )
        st.plotly_chart(fig2, width="stretch")
    
    # ── 소속별 불량률 & 달성률 그룹 막대 ──
    st.markdown('<div class="section-label">📈 소속별 불량률 vs 달성률 비교</div>', unsafe_allow_html=True)
    
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        x=filtered_df["소속"],
        y=filtered_df[col_defect],
        name=f"{prefix} 불량률",
        marker_color="#e74c3c",
        text=filtered_df[col_defect].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else ""),
        textposition="outside",
        textfont=dict(size=10),
    ))
    fig3.add_trace(go.Bar(
        x=filtered_df["소속"],
        y=filtered_df[col_achieve],
        name=f"{prefix} 달성률",
        marker_color="#2d8cf0",
        text=filtered_df[col_achieve].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else ""),
        textposition="outside",
        textfont=dict(size=10),
    ))
    fig3.update_layout(
        barmode="group",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(l=40, r=20, t=40, b=60),
        xaxis=dict(title="소속", tickangle=-30),
        yaxis=dict(title="비율 (%)"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )
    st.plotly_chart(fig3, width="stretch")
    
    # ── 데이터 테이블 ──
    st.markdown('<div class="section-label">📋 전체 데이터 테이블</div>', unsafe_allow_html=True)
    
    # 표시용 데이터프레임 포맷
    display_df = filtered_df.copy()
    
    # 퍼센트 컬럼 포맷
    pct_cols = [c for c in display_df.columns if "불량률" in c or "달성률" in c]
    
    st.dataframe(
        display_df.style
        .format({col: "{:.2f}%" for col in pct_cols})
        .format({"목표": "{:.2f}"})
        .background_gradient(
            subset=[c for c in pct_cols if "불량률" in c],
            cmap="YlOrRd",
            vmin=0,
        )
        .background_gradient(
            subset=[c for c in pct_cols if "달성률" in c],
            cmap="RdYlGn",
            vmin=0,
        ),
        width="stretch",
        height=400,
    )
    
    # 푸터
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; font-size: 0.8rem;'>"
        "📊 용접불량률 현황 대시보드 · 데이터 출처: welding data.xlsx"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
