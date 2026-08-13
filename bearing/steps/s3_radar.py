"""③ 감지 — 리스크 레이더 【깊게】"""

from __future__ import annotations

import json
import time

import pandas as pd
import streamlit as st

import live_news
import llm
import state

SEVERITY_LABEL = {1: "경미", 2: "주의", 3: "경계", 4: "심각", 5: "전면중단"}
RISK_BADGE = {"LOW": ":green-badge[LOW]", "MID": ":orange-badge[MID]", "HIGH": ":red-badge[HIGH]"}

# 화물 매칭은 이 심각도 이상인 이벤트로만 한정한다. 항만 코드를 하드코딩하지 않고
# "진짜 심각한 사건"만 화물에 반영하게 해서, 라이브 뉴스 모드에서 수에즈 체선 같은
# 경미한 이벤트가 무관한 화물을 끌어들이는 일을 막는다. (캐시 데모 데이터 기준
# 로테르담 파업만 4이고 나머지는 2라서, 캐시 모드 결과는 기존과 동일하게 유지된다.)
SEVERITY_MATCH_THRESHOLD = 4


def render(incident: dict) -> None:
    st.subheader("리스크 레이더")
    st.caption("뉴스를 스캔해 물류 영향 이벤트만 추출하고, 진행중 화물 50건과 대조한다.")

    # 1) 결과 확보: 세션 → 없으면 폴백
    data = st.session_state.get("s3_match")
    from_cache = False
    if not data:
        data = llm.load_fallback("s3_match.json")
        from_cache = True

    top = st.container(horizontal=True, vertical_alignment="center")
    with top:
        run = st.button("뉴스 스캔 실행", type="primary", key="w_s3_run")
        live_mode = st.toggle(
            "실시간 RSS 뉴스",
            value=True,
            key="w_s3_live",
            help="켜면 gCaptain·Splash 247 등 해운 전문지 RSS를 실시간으로 가져온다. "
            "실제 뉴스라 로테르담 파업 등 데모 이벤트가 없을 수 있다. "
            "끄면 데모용으로 미리 준비된 뉴스 20건을 쓴다.",
        )
        st.caption(
            "실시간 RSS에서 가져온 최신 기사를 스캔합니다."
            if live_mode
            else "캐시된 뉴스 20건 중 물류 영향 기사만 필터링합니다."
        )

    if run:
        data = _run_scan(live_mode)
        from_cache = False

    if from_cache:
        st.caption("📦 캐시된 결과 표시 중")

    events = data.get("events") or []
    affected = data.get("affected") or []
    not_affected = data.get("not_affected_count", 0)

    # 2) 이벤트 카드
    st.markdown("#### 추출된 리스크 이벤트")
    if not events:
        st.info("추출된 이벤트가 없습니다. `뉴스 스캔 실행`을 눌러주세요.")
    else:
        cols = st.columns(len(events))
        for col, event in zip(cols, events):
            with col:
                _event_card(event)

    st.divider()

    # 3) 영향 화물
    total = len(state.load_shipments())
    st.markdown("#### 영향받는 화물")
    metrics = st.container(horizontal=True)
    with metrics:
        st.metric("영향 화물", f"{len(affected)}건", delta=f"전체 {total}건 중")
        st.metric("직접영향", f"{sum(1 for a in affected if a.get('impact') == 'DIRECT')}건")
        st.metric("간접영향", f"{sum(1 for a in affected if a.get('impact') == 'INDIRECT')}건")
        st.metric("영향 없음", f"{not_affected}건")

    if not affected:
        st.info("영향 화물이 아직 식별되지 않았습니다.")
        return

    _affected_table(affected)

    st.divider()
    st.markdown("#### 화물 상세 · 대체안 비교")
    st.caption("행을 펼쳐 A/B/C 대체안을 비교하고, 심의에 올릴 안을 선택하면 검증 탭으로 넘어갑니다.")

    for item in affected:
        _shipment_expander(item)


# ---------------------------------------------------------------- LLM 실행


def _run_scan(live_mode: bool = False) -> dict:
    """뉴스 → 이벤트 추출 → 화물 매칭. 실패해도 폴백을 돌려준다."""
    shipments = state.load_shipments()
    routes = state.load_routes()

    with st.status("리스크 스캔 진행 중", expanded=True) as status:
        news = []
        if live_mode:
            st.write("📡 RSS 실시간 뉴스 수집 중 (gCaptain · Splash 247 · The Loadstar · FreightWaves)...")
            news = live_news.fetch_live_news()
            if news:
                sources = sorted({n["source"] for n in news})
                st.write(f"✅ 실시간 기사 {len(news)}건 수집 · 출처: {', '.join(sources)}")
            else:
                st.write("⚠️ 실시간 수집 실패 — 캐시된 뉴스로 대체합니다")

        if not news:
            news = state.load_news()
            st.write(f"📰 캐시된 뉴스 {len(news)}건 로드")
        time.sleep(0.2)

        st.write("🔍 물류 영향 이벤트 추출 중...")
        news_text = "\n\n".join(
            f"[{n['id']}] ({n['date']} / {n['source']}) {n['title']}\n{n['body']}" for n in news
        )
        extract_prompt = llm.load_prompt("s3_extract.txt").replace("{news_text}", news_text)
        extracted = llm.call_json(
            system="당신은 글로벌 물류 리스크 애널리스트다. JSON만 출력한다.",
            messages=[{"role": "user", "content": extract_prompt}],
            fallback_path="s3_match.json",
            max_tokens=4000,
        )
        events = extracted.get("events") or []
        st.write(f"✅ 이벤트 {len(events)}건 추출 · 무관 기사 {max(len(news) - _cited(events), 0)}건 제외")
        time.sleep(0.2)

        # 이벤트 카드는 추출된 전부를 보여주되, 화물 매칭은 진짜 심각한 이벤트로만
        # 한정한다. 경미한 이벤트(수에즈 체선 등)가 무관한 화물을 끌어들이지 않게 한다.
        matching_events = [
            e for e in events if llm.safe_int(e.get("severity")) >= SEVERITY_MATCH_THRESHOLD
        ]

        if matching_events:
            st.write("🚢 진행중 화물 50건 대조 및 대체안 설계 중...")
            match_prompt = (
                llm.load_prompt("s3_match.txt")
                .replace("{event_json}", json.dumps(matching_events, ensure_ascii=False))
                .replace("{shipments_csv}", shipments.to_csv(index=False))
                .replace("{routes_csv}", routes.to_csv(index=False))
            )
            matched = llm.call_json(
                system="당신은 글로비스 운영 컨트롤타워다. JSON만 출력한다.",
                messages=[{"role": "user", "content": match_prompt}],
                fallback_path="s3_match.json",
                max_tokens=16000,
            )
            affected = matched.get("affected") or []
        else:
            # 심각도 4 이상인 이벤트가 없으면 화물 매칭 자체를 생략한다.
            # (오늘은 화물에 영향 줄 만큼 심각한 리스크가 없다는 것도 정직한 결과다.)
            st.write("ℹ️ 심각도 4 이상 이벤트가 없어 화물 매칭을 생략합니다")
            affected = []

        result = {
            "events": events or (llm.load_fallback("s3_match.json").get("events") or []),
            "affected": affected,
            # LLM이 계산한 값은 종종 산수가 틀리므로(특히 가벼운 모델) 신뢰하지 않고
            # 전체 화물 수에서 실제로 뽑힌 영향 화물 수를 빼서 결정론적으로 구한다.
            "not_affected_count": max(len(shipments) - len(affected), 0),
        }
        st.write(f"✅ 영향 화물 {len(result['affected'])}건 식별")
        status.update(label="스캔 완료", state="complete", expanded=False)

    st.session_state["s3_match"] = result
    st.session_state["s3_events"] = result["events"]
    _sync_active_incident_count(len(affected))
    # 사이드바는 본문보다 먼저 그려지므로, 이번 실행 주기 안에는 방금 갱신한
    # 영향 건수가 반영되지 않는다. 한 번 더 그리게 해서 사이드바까지 맞춘다.
    st.rerun()


def _sync_active_incident_count(affected_count: int) -> None:
    """사이드바의 '영향 N건'을 시드값 대신 실제 스캔 결과로 갱신한다."""
    active_id = st.session_state.get("active_incident")
    for incident in st.session_state.get("incidents", []):
        if incident["id"] == active_id:
            incident["affected"] = affected_count
            break


def _cited(events: list) -> int:
    ids = set()
    for event in events:
        ids.update(event.get("source_ids") or [])
    return len(ids)


# ---------------------------------------------------------------- 렌더 조각


def _event_card(event: dict) -> None:
    loc = event.get("location") or {}
    period = event.get("period") or {}
    impact = event.get("impact") or {}
    severity = llm.safe_int(event.get("severity"), default=1)
    confidence = llm.safe_float(event.get("confidence"))

    with st.container(border=True):
        st.markdown(f"**{loc.get('name') or '미상'}** `{loc.get('port_code') or '-'}`")
        st.caption(f"{event.get('type', '-')} · {period.get('start') or '?'} ~ {period.get('end') or '진행중'}")
        st.progress(severity / 5, text=f"심각도 {severity}/5 · {SEVERITY_LABEL.get(severity, '-')}")
        st.progress(confidence, text=f"신뢰도 {confidence:.0%}")
        st.markdown(event.get("summary") or "")
        delay = f"{impact.get('delay_days_min', 0)}~{impact.get('delay_days_max', 0)}일"
        st.caption(f"예상 지연 {delay} · 영향 모드 {', '.join(impact.get('affects_modes') or ['-'])}")
        with st.expander("판단 근거"):
            st.write(event.get("evidence") or "-")
            if event.get("source_ids"):
                st.caption("출처: " + ", ".join(event["source_ids"]))


def _affected_table(affected: list) -> None:
    rows = []
    for item in affected:
        ship = state.shipment_by_bl(item.get("bl_no", ""))
        rows.append(
            {
                "영향": "🔴 직접" if item.get("impact") == "DIRECT" else "🟡 간접",
                "BL_NO": item.get("bl_no"),
                "화주명": ship.get("화주명", "-"),
                "화물유형": ship.get("화물유형", "-"),
                "구간": f"{ship.get('POL', '-')}→{ship.get('POD', '-')}",
                "ETA": ship.get("ETA", "-"),
                "납기일": ship.get("납기일", "-"),
                "인코텀즈": ship.get("인코텀즈", "-"),
                "예상지연": item.get("delay_est_days", 0),
                "SLA위반": "⚠️ 예상" if item.get("sla_breach") else "정상",
                "특수화물": ship.get("특수화물코드", "") or "-",
                "추천안": item.get("recommend", "-"),
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "예상지연": st.column_config.NumberColumn("예상지연", format="%d일"),
        },
    )


def _shipment_expander(item: dict) -> None:
    bl_no = item.get("bl_no", "")
    ship = state.shipment_by_bl(bl_no)
    impact_tag = ":red-badge[직접영향]" if item.get("impact") == "DIRECT" else ":orange-badge[간접영향]"
    special = ship.get("특수화물코드", "")
    title = f"{bl_no} · {ship.get('화주명', '-')} · {ship.get('화물유형', '-')}"

    with st.expander(title, expanded=(bl_no == "GLVS2608-0417")):
        st.markdown(f"{impact_tag}　{'　:violet-badge[' + special + ']' if special else ''}")
        st.write(item.get("reason") or "")

        info = st.container(horizontal=True)
        with info:
            st.metric("예상 지연", f"{item.get('delay_est_days', 0)}일")
            st.metric("ETA", ship.get("ETA", "-"))
            st.metric("납기일", ship.get("납기일", "-"))
            st.metric("인코텀즈", ship.get("인코텀즈", "-"))
            st.metric("SLA", "위반 예상" if item.get("sla_breach") else "정상")

        options = item.get("options") or []
        if not options:
            st.info("대체안이 없습니다.")
            return

        st.markdown("**대체안 비교**")
        cols = st.columns(len(options))
        for col, option in zip(cols, options):
            with col:
                _option_card(item, ship, option)

        st.info(f"**추천 {item.get('recommend', '-')}안** — {item.get('why', '')}")


def _option_card(item: dict, ship: dict, option: dict) -> None:
    label = option.get("label", "?")
    is_recommended = label == item.get("recommend")

    with st.container(border=True):
        head = f"### {label}안"
        if is_recommended:
            head += " :green-badge[추천]"
        st.markdown(head)
        st.caption(option.get("route", "-"))
        st.markdown(f"`{option.get('mode', '-')}`　리스크 {RISK_BADGE.get(option.get('risk', ''), '-')}")

        st.metric("리드타임", f"{option.get('lead_time_days', 0)}일")
        st.progress(min(option.get("cost_index", 0) / 800, 1.0), text=f"비용지수 {option.get('cost_index', 0)}")
        st.progress(min(option.get("co2_index", 0) / 1500, 1.0), text=f"CO2지수 {option.get('co2_index', 0)}")

        st.caption(f"**트레이드오프** {option.get('tradeoff', '-')}")
        st.caption(f"**선택 조건** {option.get('trigger', '-')}")

        if st.button(
            f"{label}안으로 심의 요청",
            key=f"w_pick_{item.get('bl_no')}_{label}",
            width="stretch",
            type="primary" if is_recommended else "secondary",
        ):
            st.session_state["s1_selected"] = {
                "bl_no": item.get("bl_no"),
                "shipment": ship,
                "option": option,
                "impact_item": item,
            }
            # 새 심의이므로 이전 심문 기록은 비운다
            st.session_state["s1_transcript"] = []
            st.session_state["s1_round"] = 0
            st.session_state["s1_verdict"] = None
            st.toast(f"{item.get('bl_no')} {label}안을 심의에 올렸습니다. 검증 탭으로 이동하세요.", icon="⚖️")
