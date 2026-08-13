"""RSS 실시간 뉴스 크롤러.

해운·물류 전문 매체의 공개 RSS 피드에서 최신 기사를 가져온다.
news_cache.json과 동일한 스키마([{id, date, source, title, body, lang}])로 변환해
기존 s3_extract.txt 프롬프트에 그대로 흘려보낼 수 있게 한다.

실패해도 예외를 던지지 않는다 — 실패 시 빈 리스트를 돌려주고, 호출부가 캐시로 폴백한다.
"""

from __future__ import annotations

import html
import re
import urllib.request
from datetime import datetime, timezone

import streamlit as st

# 해운/물류 전문지 공개 RSS. 유료 매체(로이즈리스트, 트레이드윈즈 등)는 RSS가
# 막혀있거나 요약만 제공해 제외했다.
FEEDS = [
    {"url": "https://gcaptain.com/feed/", "source": "gCaptain"},
    {"url": "https://splash247.com/feed/", "source": "Splash 247"},
    {"url": "https://theloadstar.com/feed/", "source": "The Loadstar"},
    {"url": "https://www.freightwaves.com/feed", "source": "FreightWaves"},
]

MAX_PER_FEED = 6
MAX_TOTAL = 20

# 피드 서버가 응답을 안 주면 무한 대기하지 않도록 상한을 둔다.
# (원래 스펙이 "실시간 크롤링 금지"였던 이유가 이 상황을 막기 위해서였다.)
FEED_TIMEOUT_SECONDS = 6


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_feed_bytes(url: str) -> bytes | None:
    """RSS XML을 제한 시간 안에 가져온다. 실패/타임아웃이면 None."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (GlovisWarRoom RSS bot)"})
    try:
        with urllib.request.urlopen(req, timeout=FEED_TIMEOUT_SECONDS) as resp:
            return resp.read()
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=300)  # 5분 캐시: 같은 데모 세션 내 중복 크롤링 방지
def fetch_live_news(max_total: int = MAX_TOTAL) -> list:
    """RSS 피드에서 최신 기사를 모아 news_cache.json과 같은 스키마로 반환한다.

    전 피드가 실패하면 빈 리스트를 돌려준다 (호출부가 캐시 폴백 처리).
    """
    import feedparser

    items = []
    for feed in FEEDS:
        raw = _fetch_feed_bytes(feed["url"])
        if raw is None:
            continue
        try:
            # bytes를 직접 넘기면 feedparser가 네트워크 요청을 하지 않는다 —
            # 타임아웃은 위 _fetch_feed_bytes에서 이미 확보했다.
            parsed = feedparser.parse(raw)
        except Exception:
            continue
        for entry in (parsed.entries or [])[:MAX_PER_FEED]:
            title = _strip_html(entry.get("title", ""))
            summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
            if not title:
                continue
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                date_str = datetime(*published[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d")
            else:
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            items.append(
                {
                    "id": f"LIVE{len(items) + 1:03d}",
                    "date": date_str,
                    "source": feed["source"],
                    "title": title,
                    "body": summary or title,
                    "lang": "en",
                    "url": entry.get("link", ""),
                }
            )

    # 최신순 정렬 후 상한 적용
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:max_total]
