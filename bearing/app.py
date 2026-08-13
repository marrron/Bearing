"""BEAR·ING — Streamlit 진입점. 레이아웃 + 탭 라우팅만 담당한다."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import state
from steps import s1_devil, s2_council, s3_radar, s4_rca, s5_playbook, s6_comms

LOGO_PATH = Path(__file__).parent / "assets" / "bearing_logo.png"

st.set_page_config(
    page_title="BEAR·ING",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)

state.init_state()

# 탭 간 간격이 좁아 가독성이 떨어져서 사용자 요청으로 여백만 넓힌다.
# 폰트는 SUIT(눈누, 무료 상업이용 가능)으로 통일해 깔끔하고 정돈된 느낌을 준다.
st.html(
    """<style>
    @import url('https://cdn.jsdelivr.net/gh/sun-typeface/SUIT@2/fonts/variable/woff2/SUIT-Variable.css');

    html, body, [class*="css"] {
        font-family: 'SUIT Variable', -apple-system, BlinkMacSystemFont,
            'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif !important;
    }
    h1, h2, h3, h4 { letter-spacing: -0.02em; font-weight: 700; }

    [data-testid="stTabs"] [role="tablist"] { gap: 2.5rem; }
    [data-testid="stTab"] p { font-size: 1rem; }

    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
        margin-bottom: 0.4rem;
    }
    [data-testid="stSidebar"] hr { margin: 0.75rem 0; }
    </style>"""
)

incident = state.active_incident()

# ---------------------------------------------------------------- 헤더

header_row = st.container(horizontal=True, vertical_alignment="center", gap="small")
with header_row:
    st.image(str(LOGO_PATH), width=44)
    st.title("BEAR·ING")
st.caption("글로벌 물류 리스크 감지 → 검증 → 합의 → 실행 → 통보 → 학습, 하나의 사건을 끝까지 따라가는 AI 위기대응 관제실")

st.divider()

# ---------------------------------------------------------------- 사이드바

SEVERITY_BADGE = {"HIGH": ":red-badge[HIGH]", "MID": ":orange-badge[MID]", "LOW": ":gray-badge[LOW]"}

STEP_LABELS = {
    "s3_match": "감지",
    "s1_verdict": "검증",
    "s2_council": "합의",
    "s5_playbook": "플레이북",
    "s6_comms": "고객통보",
    "s4_rca": "사후분석",
}

with st.sidebar:
    st.subheader(f"감지된 사건 · {len(st.session_state['incidents'])}건")

    for item in st.session_state["incidents"]:
        is_active = item["id"] == st.session_state["active_incident"]
        with st.container(border=True):
            st.markdown(f"**{item['title']}**　{SEVERITY_BADGE.get(item['severity'], '')}")
            st.caption(f"{item['period']} · 영향 {item['affected']}건")
            if st.button(
                "선택됨" if is_active else "이 사건 보기",
                key=f"w_incident_{item['id']}",
                width="stretch",
                type="primary" if is_active else "secondary",
                disabled=is_active,
            ):
                st.session_state["active_incident"] = item["id"]
                st.rerun()

    incident = state.active_incident()

    st.divider()

    st.subheader("진행도")
    done = state.progress_done()
    st.progress(done / 6, text=f"{done}/6 단계 완료")
    step_col_a, step_col_b = st.columns(2)
    for i, key in enumerate(state.STEP_KEYS):
        label = STEP_LABELS[key]
        status = "완료" if st.session_state.get(key) else "대기"
        with (step_col_a if i % 2 == 0 else step_col_b):
            st.markdown(
                f'<span style="color:#fff;font-size:0.85rem">{label} · {status}</span>',
                unsafe_allow_html=True,
            )

    st.divider()

    if st.session_state.get("last_llm_error"):
        with st.expander("최근 LLM 오류", expanded=False):
            st.code(st.session_state["last_llm_error"], language="text")

# ---------------------------------------------------------------- 본문 6탭

tab3, tab1, tab2, tab5, tab6, tab4 = st.tabs(
    [
        "감지 · 리스크 레이더",
        "검증 · 반대심문",
        "합의 · 원탁회의",
        "플레이북",
        "고객통보",
        "사후분석",
    ]
)

# 탭은 순서와 무관하게 아무거나 눌러도 열려야 한다.
# 각 렌더 함수는 결과가 없으면 fallback/ 에서 로드해 그린다.
with tab3:
    s3_radar.render(incident)
with tab1:
    s1_devil.render(incident)
with tab2:
    s2_council.render(incident)
with tab5:
    s5_playbook.render(incident)
with tab6:
    s6_comms.render(incident)
with tab4:
    s4_rca.render(incident)
