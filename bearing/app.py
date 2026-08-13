"""BEAR·ING — Streamlit 진입점. 레이아웃 + 탭 라우팅만 담당한다."""

from __future__ import annotations

import streamlit as st

import llm
import state
from steps import s1_devil, s2_council, s3_radar, s4_rca, s5_playbook, s6_comms

st.set_page_config(
    page_title="BEAR·ING",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

state.init_state()

# 탭 간 간격이 좁아 가독성이 떨어져서 사용자 요청으로 여백만 넓힌다.
st.html(
    """<style>
    [data-testid="stTabs"] [role="tablist"] { gap: 2.5rem; }
    [data-testid="stTab"] p { font-size: 1rem; }
    </style>"""
)

incident = state.active_incident()

# ---------------------------------------------------------------- 헤더

header_left, header_right = st.columns([3, 1], vertical_alignment="center")
with header_left:
    st.title("🧭 BEAR·ING")
    st.caption("글로벌 물류 리스크 감지 → 검증 → 합의 → 실행 → 통보 → 학습, 하나의 사건을 끝까지 따라가는 AI 위기대응 관제실")
with header_right:
    st.metric("사건번호", f"#{incident['id']}", delta="진행중", delta_color="off")

st.divider()

# ---------------------------------------------------------------- 사이드바

with st.sidebar:
    st.subheader("감지된 사건")

    labels = {}
    for item in st.session_state["incidents"]:
        label = f"{item['badge']} {item['title']}"
        labels[label] = item["id"]

    current_label = next(
        (label for label, iid in labels.items() if iid == st.session_state["active_incident"]),
        list(labels)[0],
    )
    picked = st.radio(
        "사건 선택",
        list(labels),
        index=list(labels).index(current_label),
        label_visibility="collapsed",
        key="w_incident_pick",
    )
    st.session_state["active_incident"] = labels[picked]
    incident = state.active_incident()

    st.caption(f"{incident['period']} · 영향 {incident['affected']}건")

    st.divider()

    done = state.progress_done()
    st.subheader("진행도")
    st.progress(done / 6, text=f"{'●' * done}{'○' * (6 - done)}  {done}/6 단계")

    st.divider()

    if llm.is_live():
        st.caption(f"🟢 LLM 연결됨 · `{llm.model_name()}`")
    else:
        st.caption("⚪ API 키 없음 · 캐시된 결과로 동작")

    if st.session_state.get("last_llm_error"):
        with st.expander("최근 LLM 오류", expanded=False):
            st.code(st.session_state["last_llm_error"], language="text")

    if st.button("데모 리셋", width="stretch", key="w_reset"):
        state.reset_state()
        st.rerun()

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
