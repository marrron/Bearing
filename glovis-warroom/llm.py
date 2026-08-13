"""LLM 호출 래퍼 + JSON 파서 + 폴백 로더.

이 모듈의 모든 공개 함수는 예외를 밖으로 던지지 않는다.
API 키가 없거나 네트워크가 끊겨도 앱은 폴백 데이터로 계속 동작해야 한다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterator

import streamlit as st

BASE_DIR = Path(__file__).parent
PROMPT_DIR = BASE_DIR / "prompts"
FALLBACK_DIR = BASE_DIR / "fallback"
DATA_DIR = BASE_DIR / "data"

# 스펙 지시대로 Sonnet 계열 최신 모델을 기본값으로 둔다.
DEFAULT_MODEL = "claude-sonnet-5"

# 데모 응답 속도를 위해 thinking은 끄고 effort는 medium으로 고정한다.
# (Sonnet 5는 thinking이 기본 ON이라 max_tokens를 thinking이 잠식할 수 있다)
THINKING = {"type": "disabled"}
OUTPUT_CONFIG = {"effort": "medium"}


# ---------------------------------------------------------------- 환경 / 클라이언트


def _load_dotenv() -> None:
    """python-dotenv 없이 .env를 읽는다. 이미 설정된 환경변수는 덮어쓰지 않는다."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


_load_dotenv()


def model_name() -> str:
    return os.environ.get("MODEL_NAME") or DEFAULT_MODEL


@st.cache_resource(show_spinner=False)
def _client():
    """Anthropic 클라이언트. 키가 없거나 SDK가 없으면 None을 반환한다."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic

        return Anthropic(api_key=api_key)
    except Exception:
        return None


def is_live() -> bool:
    """실제 LLM 호출이 가능한 상태인지."""
    return _client() is not None


# ---------------------------------------------------------------- 파일 로더


@st.cache_data(show_spinner=False)
def load_prompt(name: str) -> str:
    """prompts/ 아래 텍스트 파일을 읽는다."""
    try:
        return (PROMPT_DIR / name).read_text(encoding="utf-8")
    except Exception:
        return ""


def load_fallback(path: str):
    """fallback/ 아래 JSON 또는 텍스트를 읽는다. 실패해도 예외를 던지지 않는다."""
    target = FALLBACK_DIR / path
    try:
        text = target.read_text(encoding="utf-8")
    except Exception:
        return {} if path.endswith(".json") else ""
    if path.endswith(".json"):
        try:
            return json.loads(text)
        except Exception:
            return {}
    return text


# ---------------------------------------------------------------- LLM 호출


def call(system: str, messages: list, max_tokens: int = 2000, stream: bool = False):
    """LLM 1회 호출. stream=True면 텍스트 조각 제너레이터를 돌려준다.

    호출 불가 상태거나 오류가 나면 stream 여부에 따라 빈 문자열 / 빈 제너레이터를 반환한다.
    """
    client = _client()
    if client is None:
        return _empty_stream() if stream else ""

    try:
        if stream:
            return _stream_text(client, system, messages, max_tokens)
        resp = client.messages.create(
            model=model_name(),
            max_tokens=max_tokens,
            thinking=THINKING,
            output_config=OUTPUT_CONFIG,
            system=system,
            messages=messages,
        )
        return "".join(block.text for block in resp.content if block.type == "text")
    except Exception as exc:  # 네트워크·인증·쿼터 등 모든 실패를 흡수한다
        _remember_error(exc)
        return _empty_stream() if stream else ""


def _empty_stream() -> Iterator[str]:
    return iter(())


def _stream_text(client, system: str, messages: list, max_tokens: int) -> Iterator[str]:
    try:
        with client.messages.stream(
            model=model_name(),
            max_tokens=max_tokens,
            thinking=THINKING,
            output_config=OUTPUT_CONFIG,
            system=system,
            messages=messages,
        ) as s:
            for chunk in s.text_stream:
                yield chunk
    except Exception as exc:
        _remember_error(exc)
        return


def _remember_error(exc: Exception) -> None:
    """마지막 오류를 세션에 남긴다. 사이드바 진단용."""
    try:
        st.session_state["last_llm_error"] = f"{type(exc).__name__}: {exc}"
    except Exception:
        pass


# ---------------------------------------------------------------- JSON 호출


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def strip_fence(text: str) -> str:
    """마크다운 코드펜스를 제거한다."""
    text = _FENCE_RE.sub("", text.strip())
    # 앞뒤에 설명이 붙은 경우 첫 { 부터 마지막 } 까지만 취한다
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    return text.strip()


def call_json(system: str, messages: list, fallback_path: str, max_tokens: int = 4000) -> dict:
    """JSON 응답을 강제하는 호출. 어떤 경우에도 dict를 돌려준다.

    1) 호출 → 2) 코드펜스 제거 → 3) json.loads → 4) 실패 시 1회 재시도 → 5) 폴백
    """
    raw = call(system, messages, max_tokens=max_tokens)
    parsed = _try_parse(raw)
    if parsed is not None:
        return parsed

    if raw:  # 응답은 왔는데 JSON이 아닌 경우에만 재시도할 가치가 있다
        retry_messages = list(messages) + [
            {"role": "assistant", "content": raw[:2000] or "(빈 응답)"},
            {"role": "user", "content": "형식이 잘못됐다. 설명 없이 유효한 JSON 객체만 출력하라."},
        ]
        parsed = _try_parse(call(system, retry_messages, max_tokens=max_tokens))
        if parsed is not None:
            return parsed

    fb = load_fallback(fallback_path)
    return fb if isinstance(fb, dict) else {}


def _try_parse(raw: str):
    if not raw:
        return None
    try:
        value = json.loads(strip_fence(raw))
    except Exception:
        return None
    return value if isinstance(value, dict) else None
