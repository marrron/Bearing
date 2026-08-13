"""⑤ 플레이북 【얕게】 — 슬라이더 3개 + LLM 1회 호출 + 마크다운 다운로드."""

from __future__ import annotations

import json

import streamlit as st

import llm


def render(incident: dict) -> None:
    st.subheader("대응 플레이북 발행")
    st.caption("사건 파라미터를 조정하고 실행 플레이북을 생성한다. 그대로 배포 가능한 마크다운 문서로 내려받는다.")

    with st.form("w_s5_form"):
        cols = st.columns(3)
        with cols[0]:
            duration = st.slider("사건 지속기간 (일)", 1, 30, 9)
        with cols[1]:
            volume = st.slider("물동량 변화율 (%)", -60, 60, -30)
        with cols[2]:
            budget = st.slider("허용 추가비용 (%)", 0, 300, 80)
        submitted = st.form_submit_button("플레이북 생성", type="primary")

    doc = st.session_state.get("s5_playbook")
    from_cache = False
    if not doc:
        doc = llm.load_fallback("s5_playbook.md")
        from_cache = True

    if submitted:
        doc = _generate(duration, volume, budget)
        from_cache = False

    if from_cache:
        st.caption("📦 캐시된 결과 표시 중")

    st.download_button(
        "플레이북 .md 다운로드",
        data=doc,
        file_name=f"playbook_{incident['id']}.md",
        mime="text/markdown",
        type="secondary",
        key="w_s5_dl",
    )

    st.divider()
    with st.container(border=True):
        st.markdown(doc)


def _generate(duration: int, volume: int, budget: int) -> str:
    events = st.session_state.get("s3_events") or llm.load_fallback("s3_match.json").get("events") or []
    consensus = (st.session_state.get("s2_council") or llm.load_fallback("s2_council.json")).get("consensus") or {}

    prompt = (
        llm.load_prompt("s5_playbook.txt")
        .replace("{event_json}", json.dumps(events[:1], ensure_ascii=False))
        .replace("{consensus_json}", json.dumps(consensus, ensure_ascii=False))
        .replace("{duration}", str(duration))
        .replace("{volume}", str(volume))
        .replace("{budget}", str(budget))
    )

    with st.spinner("플레이북 작성 중..."):
        text = llm.call(
            system="당신은 글로비스 위기대응 플레이북 작성자다. 마크다운 문서만 출력한다.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )

    if not text.strip():
        text = llm.load_fallback("s5_playbook.md")

    st.session_state["s5_playbook"] = text
    return text
