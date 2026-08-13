"""⑥ 고객통보 【얕게】 — ①②⑤ 결과를 컨텍스트로 메일 3종을 한 번의 호출로 생성."""

from __future__ import annotations

import json

import streamlit as st

import llm
from steps import s1_devil

TONE_ICON = {"사실중심": "📋", "관계중심": "🤝", "보상제시": "💰"}


def render(incident: dict) -> None:
    st.subheader("고객 통보 문안")
    st.caption("반대심문 판정과 합의안을 반영해 톤이 다른 메일 3종을 생성한다. 각 안에는 예상 고객 반응이 붙는다.")

    data = st.session_state.get("s6_comms")
    from_cache = False
    if not data:
        data = llm.load_fallback("s6_comms.json")
        from_cache = True

    if st.button("메일 3종 생성", type="primary", key="w_s6_run"):
        data = _generate()
        from_cache = False

    if from_cache:
        st.caption("📦 캐시된 결과 표시 중")

    drafts = data.get("drafts") or []
    if not drafts:
        st.info("생성된 문안이 없습니다.")
        return

    tabs = st.tabs([f"{TONE_ICON.get(d.get('tone', ''), '✉️')} {d.get('tone', '안')}" for d in drafts])
    for tab, draft in zip(tabs, drafts):
        with tab:
            # st.text_input은 key가 고정이면 value= 인자를 무시하고 최초 렌더링 값을 계속
            # 보여주는 위젯 상태 함정이 있다. 여기는 순수 표시용이라 마크다운으로 대체한다.
            st.markdown(f"**제목** {draft.get('subject', '-')}")
            st.code(draft.get("body", ""), language="text", wrap_lines=True)
            st.info(f"**예상 고객 반응** — {draft.get('expected_reaction', '-')}")


def _generate() -> dict:
    selected = st.session_state.get("s1_selected") or s1_devil._default_selection() or {}
    verdict = st.session_state.get("s1_verdict") or llm.load_fallback("s1_verdict.json")
    consensus = (st.session_state.get("s2_council") or llm.load_fallback("s2_council.json")).get("consensus") or {}
    playbook = st.session_state.get("s5_playbook") or llm.load_fallback("s5_playbook.md")

    prompt = (
        llm.load_prompt("s6_comms.txt")
        .replace("{shipment_json}", json.dumps(selected.get("shipment") or {}, ensure_ascii=False, default=str))
        .replace("{verdict_json}", json.dumps(verdict, ensure_ascii=False))
        .replace("{consensus_json}", json.dumps(consensus, ensure_ascii=False))
        .replace("{playbook_summary}", playbook[:1500])
    )

    with st.spinner("메일 3종 작성 중..."):
        data = llm.call_json(
            system="당신은 글로비스 고객대응팀 커뮤니케이션 담당자다. JSON만 출력한다.",
            messages=[{"role": "user", "content": prompt}],
            fallback_path="s6_comms.json",
            max_tokens=6000,
        )

    st.session_state["s6_comms"] = data
    return data
