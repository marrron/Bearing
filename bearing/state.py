"""session_state 스키마 정의 및 초기화."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

DEFAULT_STATE = {
    "incidents": [],        # 감지된 사건 목록
    "active_incident": None,
    "s3_events": None,      # 구조화된 이벤트
    "s3_match": None,       # 영향 화물 + 대체안
    "s1_selected": None,    # 담당자가 고른 대체안 (A/B/C)
    "s1_transcript": [],    # 심문 대화 기록
    "s1_round": 0,
    "s1_verdict": None,
    "s2_council": None,
    "s5_playbook": None,
    "s6_comms": None,
    "s4_rca": None,
    "last_llm_error": None,
}

# 사이드바에 항상 떠 있는 사건 3건. 앱 실행 즉시 감지된 상태로 보인다.
SEED_INCIDENTS = [
    {
        "id": "2026-0811-01",
        "title": "로테르담 항만파업",
        "port": "NLRTM",
        "severity": "HIGH",
        "badge": "🔴",
        "period": "2026-08-14 ~ 08-22",
        "affected": 7,
        "source_ids": ["N001", "N002", "N003"],
    },
    {
        "id": "2026-0809-02",
        "title": "수에즈 체선 심화",
        "port": "EGSUZ",
        "severity": "MID",
        "badge": "🟡",
        "period": "2026-08-09 ~",
        "affected": 0,
        "source_ids": ["N004", "N005"],
    },
    {
        "id": "2026-0808-03",
        "title": "상하이 기상경보",
        "port": "CNSHA",
        "severity": "LOW",
        "badge": "⚪",
        "period": "2026-08-12 ~ 08-17",
        "affected": 0,
        "source_ids": ["N006", "N007"],
    },
]

# 누적 사건 로그 (④ 사후분석 입력). 하드코딩 12건 + 이번 사건.
INCIDENT_LOG = [
    {"date": "2025-09-14", "port": "NLRTM", "cause": "항만 노무 (파업·태업)", "delay_days": 9, "affected": 5, "response_started": "출항 후"},
    {"date": "2025-11-02", "port": "DEHAM", "cause": "항만 노무 (파업·태업)", "delay_days": 6, "affected": 3, "response_started": "출항 후"},
    {"date": "2025-12-19", "port": "CNSHA", "cause": "기상 (태풍·폭풍)", "delay_days": 4, "affected": 6, "response_started": "출항 후"},
    {"date": "2026-01-23", "port": "NLRTM", "cause": "항만 적체", "delay_days": 7, "affected": 4, "response_started": "출항 후"},
    {"date": "2026-02-11", "port": "EGSUZ", "cause": "지정학 리스크", "delay_days": 12, "affected": 8, "response_started": "출항 후"},
    {"date": "2026-03-08", "port": "USLAX", "cause": "항만 적체", "delay_days": 5, "affected": 4, "response_started": "출항 전"},
    {"date": "2026-04-02", "port": "DEHAM", "cause": "항만 노무 (파업·태업)", "delay_days": 8, "affected": 2, "response_started": "출항 후"},
    {"date": "2026-04-27", "port": "CNSHA", "cause": "기상 (태풍·폭풍)", "delay_days": 3, "affected": 7, "response_started": "출항 후"},
    {"date": "2026-05-15", "port": "SGSIN", "cause": "선복 부족", "delay_days": 6, "affected": 3, "response_started": "출항 전"},
    {"date": "2026-06-09", "port": "EGSUZ", "cause": "지정학 리스크", "delay_days": 10, "affected": 5, "response_started": "출항 후"},
    {"date": "2026-06-30", "port": "AEJEA", "cause": "규제·통관", "delay_days": 4, "affected": 2, "response_started": "출항 후"},
    {"date": "2026-07-21", "port": "CNSHA", "cause": "기상 (태풍·폭풍)", "delay_days": 5, "affected": 6, "response_started": "출항 후"},
    {"date": "2026-08-14", "port": "NLRTM", "cause": "항만 노무 (파업·태업)", "delay_days": 12, "affected": 7, "response_started": "출항 후"},
]

STEP_KEYS = ["s3_match", "s1_verdict", "s2_council", "s5_playbook", "s6_comms", "s4_rca"]


def init_state() -> None:
    """없는 키만 채운다. 이미 있는 값은 건드리지 않는다."""
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            # 리스트/딕셔너리는 복사해서 넣는다 (전역 공유 방지)
            st.session_state[key] = list(value) if isinstance(value, list) else value
    if not st.session_state["incidents"]:
        st.session_state["incidents"] = [dict(i) for i in SEED_INCIDENTS]
    if st.session_state["active_incident"] is None:
        st.session_state["active_incident"] = SEED_INCIDENTS[0]["id"]


def reset_state() -> None:
    """데모 리셋. 세션을 초기 상태로 되돌린다."""
    for key in list(DEFAULT_STATE.keys()):
        st.session_state.pop(key, None)
    # 위젯 상태도 함께 비운다
    for key in [k for k in st.session_state.keys() if str(k).startswith("w_")]:
        st.session_state.pop(key, None)
    init_state()


def progress_done() -> int:
    """완료된 단계 수 (0~6)."""
    return sum(1 for key in STEP_KEYS if st.session_state.get(key))


def active_incident() -> dict:
    incident_id = st.session_state.get("active_incident")
    for incident in st.session_state.get("incidents", []):
        if incident["id"] == incident_id:
            return incident
    return SEED_INCIDENTS[0]


# ---------------------------------------------------------------- 데이터 로더


@st.cache_data(show_spinner=False)
def load_shipments() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "shipments.csv", encoding="utf-8", keep_default_na=False)


@st.cache_data(show_spinner=False)
def load_routes() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "routes.csv", encoding="utf-8", keep_default_na=False)


@st.cache_data(show_spinner=False)
def load_news() -> list:
    return json.loads((DATA_DIR / "news_cache.json").read_text(encoding="utf-8"))


def shipment_by_bl(bl_no: str) -> dict:
    """BL 번호로 화물 1건을 찾는다. 없으면 빈 dict."""
    df = load_shipments()
    rows = df[df["BL_NO"] == bl_no]
    return rows.iloc[0].to_dict() if len(rows) else {}
