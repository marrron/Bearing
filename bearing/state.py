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
    "current_step": 0,      # 현재 열려 있는 파이프라인 단계 인덱스 (STEP_KEYS 순서)
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

# 아직 스캔 전이라 감지된 사건이 하나도 없을 때 쓰는 자리표시자.
# active_incident()가 이걸 반환해도 s5_playbook 등이 incident['id']를 그대로 써도 죽지 않는다.
_EMPTY_INCIDENT = {
    "id": "PENDING",
    "title": "-",
    "port": "-",
    "severity": "LOW",
    "period": "-",
    "affected": 0,
    "source_ids": [],
}

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
    """없는 키만 채운다. 이미 있는 값은 건드리지 않는다.

    incidents는 일부러 비워둔다 — "뉴스 스캔 실행"을 눌러야 감지된 사건이
    사이드바에 나타나야 자연스럽다. 하드코딩된 시드 사건을 미리 보여주지 않는다.
    """
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            # 리스트/딕셔너리는 복사해서 넣는다 (전역 공유 방지)
            st.session_state[key] = list(value) if isinstance(value, list) else value


def progress_done() -> int:
    """완료된 단계 수 (0~6)."""
    return sum(1 for key in STEP_KEYS if st.session_state.get(key))


def active_incident() -> dict:
    incident_id = st.session_state.get("active_incident")
    for incident in st.session_state.get("incidents", []):
        if incident["id"] == incident_id:
            return incident
    return _EMPTY_INCIDENT


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
