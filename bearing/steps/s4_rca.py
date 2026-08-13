"""④ 사후분석 RCA 【얕게】 — 누적 사건 로그 원인 분류 + 차트 1개 + 패턴/제안 3줄씩."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import llm
import state


def render(incident: dict) -> None:
    st.subheader("사후분석")
    st.caption(f"누적 사건 {len(state.INCIDENT_LOG)}건(이번 사건 포함)을 원인 유형별로 분류하고 반복 패턴을 찾습니다.")

    data = st.session_state.get("s4_rca")
    from_cache = False
    if not data:
        data = llm.load_fallback("s4_rca.json")
        from_cache = True

    if st.button("패턴 분석 실행", type="primary", key="w_s4_run"):
        _analyze()
        st.rerun()

    if from_cache:
        st.caption("캐시된 결과 표시 중")

    counts = [
        {"cause": c["cause"], "count": llm.safe_int(c.get("count"))}
        for c in (data.get("cause_counts") or [])
        if c.get("cause")
    ]
    if counts:
        chart_df = pd.DataFrame(counts).set_index("cause")
        st.bar_chart(chart_df, y="count", horizontal=True, height=280)

    st.divider()

    left, right = st.columns(2)
    with left:
        st.markdown("#### 반복 패턴")
        for entry in data.get("patterns") or ["-"]:
            with st.container(border=True):
                st.markdown(entry)
    with right:
        st.markdown("#### 개선 제안")
        for entry in data.get("improvements") or ["-"]:
            with st.container(border=True):
                st.markdown(entry)

    if data.get("one_line"):
        st.divider()
        st.success(f"**{data['one_line']}**")

    with st.expander("누적 사건 로그 원본"):
        st.dataframe(pd.DataFrame(state.INCIDENT_LOG), hide_index=True, width="stretch")


def _analyze() -> dict:
    prompt = llm.load_prompt("s4_rca.txt").replace(
        "{incident_log}", json.dumps(state.INCIDENT_LOG, ensure_ascii=False)
    )
    with st.spinner("누적 패턴 분석 중..."):
        data = llm.call_json(
            system="당신은 글로비스 운영개선팀 RCA 애널리스트다. JSON만 출력한다.",
            messages=[{"role": "user", "content": prompt}],
            fallback_path="s4_rca.json",
            max_tokens=3000,
        )
    st.session_state["s4_rca"] = data
    return data
