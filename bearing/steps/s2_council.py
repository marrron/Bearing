"""② 합의 — 원탁회의 【중간】

멀티 에이전트는 for 루프 순차 호출로 구현한다. 프레임워크를 쓰지 않는다.
"""

from __future__ import annotations

import json
import time

import streamlit as st

import llm
from steps import s1_devil

COLOR = {"blue": "blue", "orange": "orange", "green": "green", "violet": "violet"}


def render(incident: dict) -> None:
    st.subheader("합의 · 원탁회의")
    st.caption("해상운영 · 항공물류 · 원가관리 · 고객대응 4개 팀이 순차로 발언하고, 조정자가 최종 합의안을 도출합니다.")

    agents = _agents()
    roster = st.container(horizontal=True)
    with roster:
        for agent in agents:
            with st.container(border=True):
                st.markdown(f"**{agent['name']}**")
                st.caption(agent["goal"])

    council = st.session_state.get("s2_council")
    has_run = council is not None

    if st.button("원탁회의 소집", type="primary", key="w_s2_run"):
        _run_council(agents)
        st.rerun()

    if not has_run:
        st.info("아직 회의를 소집하지 않았습니다. `원탁회의 소집`을 눌러주세요.")
        return

    st.divider()

    for statement in council.get("statements") or []:
        _statement(statement, agents)

    consensus = council.get("consensus")
    if consensus:
        st.divider()
        _consensus_card(consensus)


# ---------------------------------------------------------------- 실행


@st.cache_data(show_spinner=False)
def _agents() -> list:
    raw = (llm.PROMPT_DIR / "s2_agents.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _selection() -> dict:
    return st.session_state.get("s1_selected") or s1_devil._default_selection() or {}


def _run_council(agents: list) -> dict:
    """4개 에이전트를 for 루프로 순차 호출하고, 마지막에 조정자를 부른다."""
    selected = _selection()
    ship_json = json.dumps(selected.get("shipment") or {}, ensure_ascii=False, default=str)
    option_json = json.dumps(selected.get("option") or {}, ensure_ascii=False, default=str)
    verdict = st.session_state.get("s1_verdict") or llm.load_fallback("s1_verdict.json")
    verdict_json = json.dumps(verdict, ensure_ascii=False)

    base_context = (
        f"<화물>{ship_json}</화물>\n"
        f"<심의대상안>{option_json}</심의대상안>\n"
        f"<반대심문판정>{verdict_json}</반대심문판정>"
    )

    statements: list[dict] = []
    fallback = llm.load_fallback("s2_council.json")
    fallback_statements = {s["agent"]: s for s in fallback.get("statements") or []}

    for agent in agents:
        prior = "\n\n".join(f"[{s['agent']}] {s['text']}" for s in statements) or "(첫 발언자입니다)"
        user_prompt = (
            f"{base_context}\n\n<앞선발언>\n{prior}\n</앞선발언>\n\n"
            "위 맥락을 근거로 당신 팀의 입장을 3~4문장으로 말하십시오."
        )

        with st.container(border=True):
            st.markdown(f"**{agent['name']}**")
            stream = llm.call(
                system=agent["system"],
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=900,
                stream=True,
            )
            text = st.write_stream(stream)
            if not text:
                # LLM 불가 시 캐시된 발언을 한 글자씩 흘려 데모 임팩트를 유지한다
                cached = fallback_statements.get(agent["name"], {}).get("text", "")
                text = st.write_stream(_fake_stream(cached))

        statements.append({"agent": agent["name"], "text": text})
        time.sleep(0.3)  # 발언 사이 호흡

    with st.spinner("조정자가 합의안을 정리하는 중..."):
        moderator_prompt = (
            llm.load_prompt("s2_moderator.txt")
            .replace("{shipment_json}", ship_json)
            .replace("{option_json}", option_json)
            .replace("{verdict_json}", verdict_json)
            .replace("{statements}", json.dumps(statements, ensure_ascii=False))
        )
        moderated = llm.call_json(
            system="당신은 글로비스 운영심의위원회 조정자다. JSON만 출력한다.",
            messages=[{"role": "user", "content": moderator_prompt}],
            fallback_path="s2_council.json",
            max_tokens=3000,
        )

    consensus = moderated.get("consensus") or fallback.get("consensus") or {}
    council = {"statements": statements, "consensus": consensus}
    st.session_state["s2_council"] = council
    return council


def _fake_stream(text: str):
    """캐시된 발언을 스트리밍처럼 흘린다."""
    for chunk in text.split(" "):
        yield chunk + " "
        time.sleep(0.02)


# ---------------------------------------------------------------- 렌더


def _statement(statement: dict, agents: list) -> None:
    meta = next((a for a in agents if a["name"] == statement.get("agent")), None)
    color = COLOR.get((meta or {}).get("color", "blue"), "blue")

    with st.container(border=True):
        st.markdown(f"**:{color}[{statement.get('agent', '-')}]**")
        st.markdown(statement.get("text", ""))


def _consensus_card(consensus: dict) -> None:
    with st.container(border=True):
        st.markdown(f"## 합의안 — {consensus.get('decision', '-')}안")
        st.markdown(f"### {consensus.get('title', '-')}")
        st.write(consensus.get("rationale", ""))

        left, right = st.columns(2)
        with left:
            st.markdown("**실행 전제조건**")
            for entry in consensus.get("conditions") or ["-"]:
                st.markdown(f"- {entry}")
        with right:
            st.markdown("**소수의견**")
            st.info(consensus.get("dissent") or "기록된 소수의견 없음")

        actions = consensus.get("next_actions") or []
        if actions:
            st.markdown("**후속 액션**")
            st.dataframe(
                [
                    {"담당": a.get("owner", "-"), "액션": a.get("action", "-"), "기한": a.get("due", "-")}
                    for a in actions
                ],
                hide_index=True,
                width="stretch",
            )
