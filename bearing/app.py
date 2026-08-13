"""BEAR·ING — Streamlit 진입점. 레이아웃 + 탭 라우팅만 담당한다."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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

# 폰트는 SUIT(눈누, 무료 상업이용 가능)으로 통일해 깔끔하고 정돈된 느낌을 준다.
st.html(
    """<style>
    @import url('https://cdn.jsdelivr.net/gh/sun-typeface/SUIT@2/fonts/variable/woff2/SUIT-Variable.css');

    html, body, [class*="css"] {
        font-family: 'SUIT Variable', -apple-system, BlinkMacSystemFont,
            'Malgun Gothic', 'Apple SD Gothic Neo', system-ui, sans-serif !important;
    }
    h1, h2, h3, h4 { letter-spacing: -0.02em; font-weight: 700; }

    /* st.metric 기본 폰트가 카드형 요약 정보엔 지나치게 커서 전체적으로 줄인다 */
    [data-testid="stMetricValue"] { font-size: 1.15rem; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; }

    /* st.info/warning 등 안내 문구가 버튼 텍스트보다 커 보이지 않게 맞춘다 */
    [data-testid="stAlert"] p { font-size: 0.875rem; }

    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
        margin-bottom: 0.4rem;
    }
    [data-testid="stSidebar"] hr { margin: 0.75rem 0; }

    /* 감지된 사건 카드 중 선택된 카드(비활성화된 "선택됨" 버튼을 담은 카드)를 강조한다 */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] button:disabled) {
        border: 2px solid #C9A24B !important;
        background: rgba(201, 162, 75, 0.14);
        border-radius: 8px;
    }
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

    if not st.session_state["incidents"]:
        st.caption("아직 감지된 사건이 없습니다. 감지 탭에서 뉴스 스캔을 실행하세요.")

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

# ---------------------------------------------------------------- 본문: 순차 진행 스테퍼
#
# STEP_KEYS와 같은 순서(감지→검증→합의→플레이북→고객통보→사후분석)로 단계를 강제한다.
# 이전 단계를 완료해야(session_state에 결과가 저장돼야) 다음 단계가 열린다.

STEPS = [
    {"key": "s3_match", "label": "감지 · 리스크 레이더", "render": s3_radar.render},
    {"key": "s1_verdict", "label": "검증 · 반대심문", "render": s1_devil.render},
    {"key": "s2_council", "label": "합의 · 원탁회의", "render": s2_council.render},
    {"key": "s5_playbook", "label": "플레이북", "render": s5_playbook.render},
    {"key": "s6_comms", "label": "고객통보", "render": s6_comms.render},
    {"key": "s4_rca", "label": "사후분석", "render": s4_rca.render},
]

# 앞에서부터 연속으로 완료된 단계 수 = 열려 있는 마지막 단계의 인덱스
unlocked = 0
for step in STEPS:
    if st.session_state.get(step["key"]):
        unlocked += 1
    else:
        break
max_step = min(unlocked, len(STEPS) - 1)

current_step = min(st.session_state.get("current_step", 0), max_step)
st.session_state["current_step"] = current_step

nav = st.container(horizontal=True)
with nav:
    for i, step in enumerate(STEPS):
        if st.button(
            f"{i + 1}. {step['label']}",
            key=f"w_step_{i}",
            disabled=i > max_step,
            type="primary" if i == current_step else "secondary",
        ):
            st.session_state["current_step"] = i
            st.rerun()

st.divider()

current = STEPS[current_step]
current["render"](incident)

if st.session_state.get(current["key"]) and current_step < len(STEPS) - 1:
    st.divider()
    next_step = STEPS[current_step + 1]
    if st.button(f"다음 단계로 — {next_step['label']}", type="primary", key="w_next_step"):
        st.session_state["current_step"] = current_step + 1
        st.session_state["scroll_to_top"] = True
        st.rerun()

# "다음 단계로" 버튼을 누른 직후 한정으로 스크롤을 맨 위로 올린다.
# st.html은 보안상 <script>를 실행하지 않으므로(innerHTML로 삽입되면 브라우저가
# 무시한다), 실제로 JS를 실행하는 components.v1.html(iframe 기반)을 써야 한다.
# 페이지의 모든 컨텐츠가 그려진 뒤(스크립트 맨 끝)에 실행해야 이후 콘텐츠 때문에
# 스크롤 위치가 다시 밀리지 않는다.
if st.session_state.pop("scroll_to_top", False):
    components.html(
        """<script>
        function scrollTopIn(doc) {
            const el = doc.querySelector('[data-testid="stMain"]') || doc.scrollingElement;
            if (el) { el.scrollTo({top: 0, behavior: 'instant'}); return true; }
            return false;
        }
        function run() {
            try {
                if (!scrollTopIn(window.parent.document)) scrollTopIn(document);
            } catch (e) {
                scrollTopIn(document);
            }
        }
        // 콘텐츠가 계속 새로 그려지는 동안 브라우저가 스크롤 위치를 다시 밀어낼 수
        // 있어서, 짧은 시간 동안 반복적으로 0으로 되돌린다.
        let tries = 0;
        const timer = setInterval(function () {
            run();
            tries += 1;
            if (tries > 15) clearInterval(timer);
        }, 50);
        </script>""",
        height=0,
    )
