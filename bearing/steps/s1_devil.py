"""① 반대심문 — Devil's Advocate 【깊게】"""

from __future__ import annotations

import json

import streamlit as st

import llm
import state

MAX_ROUNDS = 3

VERDICT_STYLE = {
    "PASS": ("green", "승인"),
    "CONDITIONAL": ("orange", "조건부 승인"),
    "REJECT": ("red", "반려"),
}

SEVERITY_BADGE = {
    "HIGH": ":red-badge[HIGH]",
    "MID": ":orange-badge[MID]",
    "LOW": ":gray-badge[LOW]",
}

# ③에서 아무것도 고르지 않아도 심문이 열려야 한다 — 데모 각본의 화물을 기본값으로 둔다.
DEFAULT_BL = "GLVS2608-0417"


def render(incident: dict) -> None:
    st.subheader("검증 · 반대심문")
    st.caption("승인하는 위원회가 아닙니다. 결정이 무너질 지점을 찾아내는 것이 임무입니다.")

    selected = st.session_state.get("s1_selected") or _default_selection()
    if not selected:
        st.info("감지 탭에서 화물과 대체안을 선택하면 심문이 시작됩니다.")
        return

    _summary_card(selected)
    st.divider()

    # 심문 대화
    transcript = st.session_state.get("s1_transcript") or []
    round_no = st.session_state.get("s1_round", 0)

    controls = st.container(horizontal=True)
    with controls:
        if round_no == 0 and not transcript:
            if st.button("심문 시작", type="primary", key="w_s1_start"):
                _ask_next(selected)
                st.rerun()
        if st.button("심문 건너뛰고 판정 보기", key="w_s1_skip"):
            _make_verdict(selected, skipped=True)
            st.rerun()
        st.caption(f"라운드 {min(round_no, MAX_ROUNDS)}/{MAX_ROUNDS}")

    for message in transcript:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    verdict = st.session_state.get("s1_verdict")

    if not verdict and transcript and round_no <= MAX_ROUNDS:
        answer = st.chat_input("담당자 답변을 입력하세요", key="w_s1_input")
        if answer:
            st.session_state["s1_transcript"].append({"role": "user", "content": answer})
            if round_no >= MAX_ROUNDS:
                _make_verdict(selected)
            else:
                _ask_next(selected)
            st.rerun()

    if verdict:
        st.divider()
        _verdict_card(verdict)


# ---------------------------------------------------------------- 선택 복원


def _default_selection() -> dict | None:
    """③을 거치지 않고 ① 탭을 먼저 눌러도 열리도록 기본 선택을 만든다.

    세션에 실제 스캔 결과가 있으면(라이브든 캐시든 ③을 이미 돌렸다면) 그 결과 안에서
    고른다 — GLVS2608-0417이 있으면 그걸 우선하고, 없으면(라이브 뉴스가 로테르담을
    안 다뤄서 다른 화물이 잡힌 경우 등) 첫 번째 영향 화물을 쓴다.
    ③을 아예 안 돌려서 세션에 스캔 결과가 없을 때만 폴백에서 GLVS2608-0417을 쓴다
    (데모 각본 안전장치).
    """
    scanned = st.session_state.get("s3_match")
    data = scanned or llm.load_fallback("s3_match.json")
    affected = data.get("affected") or []
    if not affected:
        return None

    item = next((a for a in affected if a.get("bl_no") == DEFAULT_BL), None)
    if item is None:
        item = affected[0]  # 스캔 결과 안이면 뭐가 됐든 첫 번째로 대체

    options = item.get("options") or []
    option = next((o for o in options if o.get("label") == "A"), options[0] if options else None)
    if not option:
        return None
    return {
        "bl_no": item["bl_no"],
        "shipment": state.shipment_by_bl(item["bl_no"]),
        "option": option,
        "impact_item": item,
    }


def _summary_card(selected: dict) -> None:
    ship = selected.get("shipment") or {}
    option = selected.get("option") or {}
    item = selected.get("impact_item") or {}

    with st.container(border=True):
        head = st.container(horizontal=True, vertical_alignment="center")
        with head:
            st.markdown(f"### {selected.get('bl_no')}")
            if ship.get("특수화물코드"):
                st.markdown(f":violet-badge[{ship['특수화물코드']}]")
            st.markdown(f":blue-badge[{ship.get('인코텀즈', '-')}]")
            if item.get("sla_breach"):
                st.markdown(":red-badge[SLA 위반 예상]")

        info = st.container(horizontal=True)
        with info:
            st.metric("화주", ship.get("화주명", "-"))
            st.metric("화물", f"{ship.get('화물유형', '-')} {ship.get('컨테이너수', '-')}FEU")
            st.metric("구간", f"{ship.get('POL', '-')}→{ship.get('POD', '-')}")
            st.metric("납기일", ship.get("납기일", "-"))
            st.metric("화물가액", f"${int(ship.get('화물가액_USD', 0) or 0):,}")

        st.markdown(f"**심의 대상: {option.get('label', '?')}안 — {option.get('route', '-')}**")
        opt = st.container(horizontal=True)
        with opt:
            st.metric("운송모드", option.get("mode", "-"))
            st.metric("리드타임", f"{option.get('lead_time_days', 0)}일")
            st.metric("비용지수", option.get("cost_index", 0))
            st.metric("CO2지수", option.get("co2_index", 0))
            st.metric("리스크", option.get("risk", "-"))


# ---------------------------------------------------------------- LLM 호출


def _context(selected: dict) -> tuple[str, str]:
    ship = json.dumps(selected.get("shipment") or {}, ensure_ascii=False, default=str)
    option = json.dumps(selected.get("option") or {}, ensure_ascii=False, default=str)
    return ship, option


def _ask_next(selected: dict) -> None:
    """다음 라운드 질문을 생성해 대화에 붙인다."""
    ship_json, option_json = _context(selected)
    round_no = st.session_state.get("s1_round", 0) + 1

    system = (
        llm.load_prompt("s1_devil.txt")
        .replace("{shipment_json}", ship_json)
        .replace("{option_json}", option_json)
        .replace("{round_no}", str(round_no))
    )

    messages = list(st.session_state.get("s1_transcript") or [])
    if not messages:
        messages = [{"role": "user", "content": f"라운드 {round_no} 심문을 시작하십시오."}]
    else:
        messages = messages + [{"role": "user", "content": f"(라운드 {round_no} 질문을 하십시오)"}]

    with st.spinner("심문관이 질문을 준비하는 중..."):
        text = llm.call(system=system, messages=messages, max_tokens=1000)

    if not text:
        text = _canned_question(round_no, selected)

    st.session_state["s1_transcript"].append({"role": "assistant", "content": text})
    st.session_state["s1_round"] = round_no


def _canned_question(round_no: int, selected: dict) -> str:
    """LLM을 쓸 수 없을 때의 대본. 데모가 절대 끊기지 않게 한다."""
    ship = selected.get("shipment") or {}
    option = selected.get("option") or {}
    special = ship.get("특수화물코드", "")
    incoterms = ship.get("인코텀즈", "-")

    if round_no == 1:
        return (
            "【축】 데이터 근거\n\n"
            f"【질문】 {option.get('label', '?')}안의 리드타임 {option.get('lead_time_days', 0)}일은 "
            "어느 시점의 어떤 자료를 기준으로 산출한 수치입니까?\n\n"
            "【이 질문을 하는 이유】 파업 기간 중에는 평시 기준 리드타임이 성립하지 않으므로, "
            "기준일이 파업 발표 이전이라면 이 결정의 전제 자체가 무너집니다."
        )
    if round_no == 2 and special in ("UN3480", "UN3481") and option.get("mode") == "AIR":
        return (
            "【축】 실행 가능성\n\n"
            f"【질문】 {special} 리튬이온 배터리 항공운송 시 요구되는 위험물 신고(DGD)와 "
            "SOC 30% 이하 충전상태 규정 대응이 준비되어 있습니까?\n\n"
            "【이 질문을 하는 이유】 이 요건은 준비에 최소 3영업일이 걸리며, 충족하지 못하면 "
            "항공 전환안 자체가 실행 불가능해져 리드타임 이점이 소멸합니다."
        )
    if round_no == 2:
        return (
            "【축】 최악 시나리오\n\n"
            "【질문】 파업이 예고된 8일을 넘겨 연장되고 적체가 2주로 늘어난다면, "
            "이 안은 어느 시점에 실패로 판정되며 그때 남는 대안은 무엇입니까?\n\n"
            "【이 질문을 하는 이유】 되돌릴 수 없는 지점을 미리 정해두지 않으면 "
            "실패를 인지한 시점에 이미 대안이 사라져 있습니다."
        )
    return (
        "【축】 계약/책임\n\n"
        f"【질문】 인코텀즈 {incoterms} 조건에서 이번 지연으로 발생하는 지체료와 보관료의 "
        "부담 주체는 누구이며, 그 해석에 대해 화주와 사전 합의된 문서가 있습니까?\n\n"
        "【이 질문을 하는 이유】 부담 주체가 확정되지 않은 상태의 결정은 "
        "사후에 클레임으로 전환되어 비용 판단 자체를 무효화합니다."
    )


def _make_verdict(selected: dict, skipped: bool = False) -> None:
    ship_json, option_json = _context(selected)
    transcript = st.session_state.get("s1_transcript") or []

    if skipped and not transcript:
        st.session_state["s1_round"] = MAX_ROUNDS

    transcript_text = "\n".join(f"{m['role']}: {m['content']}" for m in transcript) or "(심문 생략)"

    system = "당신은 글로비스 운영심의위원회의 반대심문관이다. JSON만 출력한다."
    prompt = (
        llm.load_prompt("s1_verdict.txt")
        .replace("{shipment_json}", ship_json)
        .replace("{option_json}", option_json)
        .replace("{transcript}", transcript_text)
    )

    with st.spinner("판정문 작성 중..."):
        verdict = llm.call_json(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            fallback_path="s1_verdict.json",
            max_tokens=3000,
        )

    st.session_state["s1_verdict"] = verdict


# ---------------------------------------------------------------- 판정문


def _verdict_card(verdict: dict) -> None:
    key = (verdict.get("verdict") or "CONDITIONAL").upper()
    color, label = VERDICT_STYLE.get(key, VERDICT_STYLE["CONDITIONAL"])

    with st.container(border=True):
        st.markdown(f"## :{color}[{key}] — {label}")
        st.markdown(f"**{verdict.get('one_line', '')}**")

        st.divider()
        scores = verdict.get("score") or {}
        cols = st.columns(max(len(scores), 1))
        for col, (name, value) in zip(cols, scores.items()):
            with col:
                score = llm.safe_int(value, default=0)
                st.progress(min(max(score, 0), 5) / 5, text=f"{name} {value}/5")

        left, right = st.columns(2)
        with left:
            st.markdown("**소명된 항목**")
            for entry in verdict.get("validated") or ["-"]:
                st.markdown(f"- {entry}")
        with right:
            st.markdown("**승인 조건**")
            for entry in verdict.get("conditions") or ["-"]:
                st.markdown(f"- {entry}")

        unresolved = verdict.get("unresolved") or []
        if unresolved:
            st.markdown("**미해결 항목**")
            st.dataframe(
                [
                    {
                        "심각도": SEVERITY_BADGE.get(u.get("severity", ""), u.get("severity", "-")),
                        "미해결 이슈": u.get("issue", "-"),
                        "확인 담당": u.get("owner", "-"),
                        "기한": u.get("due", "-"),
                    }
                    for u in unresolved
                ],
                hide_index=True,
                width="stretch",
                column_config={"심각도": st.column_config.TextColumn("심각도", width="small")},
            )
