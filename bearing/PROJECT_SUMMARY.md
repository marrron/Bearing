# BEAR·ING — 프로젝트 전체 정리

> 이 문서는 코드베이스 전체를 훑어서 정리한 참고 자료입니다. 빠른 실행 방법은 [README.md](README.md)를 보세요.

## 한 줄 요약

**글로벌 물류 위기 사건 하나가 "감지 → 검증 → 합의 → 실행 → 통보 → 학습" 6단계를 통과하는 과정을 AI가 자동화해서 보여주는 Streamlit 데모 앱.** 현대글로비스의 완성차 해상운송 업무를 배경으로, 로테르담 항만파업 같은 사건이 터졌을 때 AI가 어떻게 감지·검증·의사결정·고객대응까지 이어가는지 시연한다.

## 이름의 의미

**BEAR·ING** — 항해 용어 "bearing"(방위, 방향 감각)이면서 "bear"(짐을 지다·견디다) + "-ing"(계속 진행 중)의 중의어. 위기 속에서도 화물을 나르고 판단 기준을 잃지 않는다는 뜻. 로고는 나침반 아이콘.

## 기술 스택

| 구성 | 선택 |
|---|---|
| 프레임워크 | Streamlit (`>=1.57`) |
| LLM | Google Gemini (`google-genai`), 기본 모델 `gemini-3.5-flash-lite` |
| 데이터 처리 | pandas |
| 실시간 뉴스 | feedparser (RSS) |
| 폰트 | SUIT Variable (눈누, 무료 상업이용) — jsDelivr CDN |
| 색상 테마 | 현대(Hyundai) 브랜드 팔레트 기반 커스텀 (`.streamlit/config.toml`) |

## 실행 방법

```bash
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY 입력 (없어도 실행됨)
streamlit run app.py
```

API 키가 없거나 LLM 호출이 실패해도 `fallback/`의 캐시된 결과로 모든 탭이 렌더된다. `llm.call_json`은 코드펜스 제거 → JSON 파싱 → 1회 재시도 → 폴백 순으로 동작하며 **예외를 밖으로 절대 던지지 않는다**(모듈 docstring에 명시된 설계 원칙).

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` (또는 `GOOGLE_API_KEY`) | 없음 | 없으면 폴백으로 동작. [aistudio.google.com](https://aistudio.google.com)에서 무료 발급 |
| `MODEL_NAME` | `gemini-3.5-flash-lite` | 사용할 Gemini 모델 |

## 6단계 파이프라인

탭 순서(왼쪽부터)와 실제 로직 순서가 다르다 — 탭은 "감지"가 먼저 오지만 내부적으로는 ①~⑥ 번호로 관리된다.

| 탭 순서 | 내부 번호 | 파일 | 내용 |
|---|---|---|---|
| 감지 · 리스크 레이더 | ③ | `steps/s3_radar.py` | 뉴스(실시간 RSS 또는 캐시 20건) 스캔 → 리스크 이벤트 추출 → 화물 50건 대조 → A/B/C 대체안 설계 |
| 검증 · 반대심문 | ① | `steps/s1_devil.py` | "반대심문관" 페르소나가 3라운드 질문 → PASS/CONDITIONAL/REJECT 판정 |
| 합의 · 원탁회의 | ② | `steps/s2_council.py` | 해상운영·항공물류·원가관리·고객대응 4개 팀이 순차 발언(for 루프, 프레임워크 미사용) → 조정자가 합의안 도출 |
| 플레이북 | ⑤ | `steps/s5_playbook.py` | 파라미터 3개(지속기간/물동량/추가비용) 조정 → 실행 플레이북 마크다운 생성·다운로드 |
| 고객통보 | ⑥ | `steps/s6_comms.py` | 톤이 다른 화주 메일 3종(사실중심/관계중심/보상제시) + 예상 반응 |
| 사후분석 | ④ | `steps/s4_rca.py` | 누적 사건 13건(하드코딩 12건 + 이번 사건) 원인 분류 → 반복 패턴·개선 제안 |

탭은 순서와 무관하게 아무거나 먼저 눌러도 열린다. ③을 안 거치고 ①을 먼저 눌러도 `s1_devil._default_selection()`이 데모 화물(`GLVS2608-0417`)을 기본 선택한다.

## 파일 구조

```
app.py              Streamlit 진입점 — 레이아웃, 사이드바, 탭 라우팅만 담당
llm.py               LLM 호출 래퍼 + JSON 파서 + 폴백 로더 + 안전 형변환(safe_int/safe_float)
state.py             session_state 스키마, 시드 사건, 누적 사건 로그, 데이터 로더
live_news.py          RSS 실시간 뉴스 크롤러 (해운 전문지 4곳)
steps/                 6개 단계별 렌더 함수
  s1_devil.py            검증 · 반대심문
  s2_council.py           합의 · 원탁회의
  s3_radar.py             감지 · 리스크 레이더
  s4_rca.py                사후분석
  s5_playbook.py           플레이북
  s6_comms.py               고객통보
prompts/               LLM 프롬프트 전량 (.txt/.json) — 코드 수정 없이 튜닝 가능
fallback/               API 키 없이도 렌더되는 캐시된 결과 (JSON/MD)
data/                   더미 데이터 (아래 참고)
assets/                 로고 이미지
.streamlit/config.toml   테마(색상) 설정
```

## 핵심 설계: 세션 → 폴백 순으로 렌더

모든 단계가 동일한 패턴을 따른다:

```python
data = st.session_state.get("s3_match")
if not data:
    data = llm.load_fallback("s3_match.json")   # 캐시된 결과
if st.button("실행"):
    data = _run(...)                              # 실제 LLM 호출, 성공 시 세션에 저장
```

즉 **"뉴스 스캔 실행" 같은 버튼을 눌러야만 실제 LLM이 호출되고**, 누르기 전까지는 `fallback/`의 미리 준비된 결과가 조용히 표시된다(자동 스캔 기능은 사용자 요청으로 제거됨 — 현재는 수동 실행만 지원).

## 더미 데이터 상세

| 파일 | 내용 | 규모 |
|---|---|---|
| `data/shipments.csv` | 화물 목록 (BL번호, 화주명, 화물유형, POL/POD, 인코텀즈, 화물가액 등) | 50건 |
| `data/routes.csv` | 노선 마스터 (구간별 리드타임/비용지수/CO2지수) | 30건 |
| `data/news_cache.json` | 캐시 모드용 해운 뉴스 기사(id/date/source/title/body/lang) | 20건 |
| `state.py` `SEED_INCIDENTS` | 앱 최초 진입 시 사이드바에 보이는 사건 3건(로테르담/수에즈/상하이) — 실제 스캔 전까지의 플레이스홀더 | 3건 |
| `state.py` `INCIDENT_LOG` | 사후분석 탭이 분석하는 과거 사건 누적 로그 | 13건(하드코딩 12 + 이번 사건) |
| `fallback/s1_verdict.json` | ① 검증 탭 폴백 판정문 | 1건 |
| `fallback/s2_council.json` | ② 합의 탭 폴백 발언/합의안 | 1건 |
| `fallback/s3_match.json` | ③ 감지 탭 폴백 이벤트+화물매칭 결과 | 1건 |
| `fallback/s4_rca.json` | ④ 사후분석 탭 폴백 패턴/제안 | 1건 |
| `fallback/s5_playbook.md` | ⑤ 플레이북 탭 폴백 마크다운 문서 | 1건 |
| `fallback/s6_comms.json` | ⑥ 고객통보 탭 폴백 메일 3종 | 1건 |

### 데이터에 심어둔 "함정" (시연 포인트)

- **`GLVS2608-0417`** — 현대차 유럽법인 완성차, 특수화물코드 `UN3480`(리튬이온 배터리), 인코텀즈 DDP, ETA가 파업 기간과 정면 충돌. 반대심문 단계가 잡아내야 하는 핵심 케이스.
- 납기 촉박 화물 — ETA와 납기일 차이 1~2일, SLA 위반 판정용.
- 간접영향 화물 — POD는 다른 항구지만 T/S(환적항)가 사고 항만, 직접/간접 영향 구분 시연용.
- 무관 뉴스 기사 — 물류와 상관없는 노이즈 기사들, "영향 없음" 필터링 능력 시연용.

## 감지 탭(③)의 동작 원리 — 가장 복잡한 단계

1. **뉴스 수집**: 실시간 RSS(gCaptain·Splash 247·The Loadstar·FreightWaves, 6초 타임아웃) 또는 캐시된 20건 중 선택(토글).
2. **이벤트 추출**: `prompts/s3_extract.txt`로 LLM이 뉴스에서 물류 영향 이벤트만 구조화 추출 (심각도 1~5, 신뢰도, 예상 지연일 등).
3. **화물 매칭**: 심각도 `SEVERITY_MATCH_THRESHOLD = 4` 이상인 이벤트만 골라서 `prompts/s3_match.txt`로 50건 화물과 대조, A/B/C 대체안 설계. (경미한 이벤트가 무관한 화물을 끌어들이는 걸 방지)
4. **사이드바 동기화**: 스캔이 끝나면 `_sync_incidents()`가 사이드바 "감지된 사건" 목록을 이번에 추출된 이벤트로 **통째로 교체**한다(더 이상 하드코딩된 3건이 아님). 재스캔 시 이전 선택과 제목이 같은 사건이 있으면 선택을 유지하려고 시도한다.

## 디자인 시스템

### 색상 (`.streamlit/config.toml`)

현대(Hyundai) 브랜드 팔레트 기반. 본문은 화이트 배경 + 남색 포인트, 사이드바만 남색 배경으로 관제실 느낌을 유지.

| 역할 | 색상 | 비고 |
|---|---|---|
| Primary / Blue | `#001E62` | Hyundai Blue (PANTONE 288C 근사치) |
| 배경 | `#FFFFFF` | |
| 보조 배경 | `#EDEDED` | Hyundai Light Gray |
| 텍스트 | `#28282B` | |
| Violet 대체 | `#8A6D2F` | Hyundai Gold — 특수화물 뱃지 등에 사용 |
| Gray | `#58595B` | Hyundai Dark-Gray |
| 사이드바 배경 | `#001E62` (진한 남색 `#0B2C7A` 보조) | 텍스트는 흰색 고정 |
| 사이드바 Primary | `#8A6D2F` | 버튼 등 포인트 |

빨강/주황/초록 등 상태색(HIGH/MID/LOW, PASS/REJECT)은 의미 전달을 위해 기능은 유지하되 톤만 차분하게 조정.

### 폰트

**SUIT Variable** (jsDelivr CDN, `app.py`의 `st.html()` 블록에서 전역 적용). 한글 UI에서 깔끔하고 정돈된 느낌을 주는 무료 폰트.

### 로고 / 파비콘

`assets/bearing_logo.png` (나침반 아이콘) — 파비콘, 헤더, 두 곳에 사용. 사이드바 로고는 가독성 문제로 제거됨.

## 세션 상태(`state.py`) 스키마

```python
DEFAULT_STATE = {
    "incidents": [],          # 사이드바 사건 목록 (스캔 후 실제 결과로 교체됨)
    "active_incident": None,  # 현재 선택된 사건 id
    "s3_events": None,        # 구조화된 이벤트 (감지)
    "s3_match": None,         # 영향 화물 + 대체안 (감지)
    "s1_selected": None,      # 심의 대상 화물+대체안 선택
    "s1_transcript": [],      # 심문 대화 기록
    "s1_round": 0,
    "s1_verdict": None,       # 검증 판정
    "s2_council": None,       # 합의 결과
    "s5_playbook": None,      # 플레이북 문서
    "s6_comms": None,         # 고객 메일 3종
    "s4_rca": None,           # 사후분석 결과
    "last_llm_error": None,   # 사이드바 진단용 최근 오류
}
```

`STEP_KEYS`(진행도 계산용): `s3_match → s1_verdict → s2_council → s5_playbook → s6_comms → s4_rca` 순서로, 사이드바 진행도 체크리스트가 이 값들의 존재 여부로 완료/대기를 표시한다.

## 이번 세션에서 이뤄진 주요 변경 이력

1. **프로젝트명 변경**: `GLOVIS WAR ROOM` / 폴더명 `glovis-warroom` → **BEAR·ING** / `bearing`.
2. **버그 수정**: LLM이 반환하는 값(severity, score 등)에 대한 무방비 `int()`/`float()` 캐스팅을 `llm.safe_int`/`llm.safe_float`로 교체 (형식이 어긋난 응답에도 탭이 죽지 않도록).
3. **로고/파비콘 교체**: 나침반 로고 이미지 적용.
4. **디자인 리뉴얼**: Hyundai 브랜드 컬러 테마 + SUIT 폰트 적용.
5. **사이드바 "감지된 사건" 실데이터화**: 하드코딩 3건 고정 표시 → 실제 뉴스 스캔 결과로 동적 교체(`_sync_incidents`). 자동 스캔은 추가했다가 사용자 요청으로 다시 제거 — 현재는 버튼을 눌러야만 스캔됨.
6. **UI 정리**: "사건번호" 메트릭 삭제, "데모 리셋" 버튼 및 관련 함수 삭제, 모든 이모지 제거(상태 텍스트로 대체), 항만 코드(UN/LOCODE) 뱃지 삭제, 진행도 라벨 원문자 번호 삭제.
7. **어투 통일**: 탭 캡션들을 서술체(~한다)에서 존댓말체(~합니다)로, 6개 탭 모두 탭 이름과 본문 subheader 일치.
8. **사이드바 사건 카드**: 라디오 버튼 → 카드형 UI(테두리, 심각도 뱃지, 선택 강조 스타일)로 교체, 선택 유지 로직 추가.
9. **반대심문 포맷 개선**: `【축】` 라벨 삭제, `【질문】`/`【이 질문을 하는 이유】` → 굵은 글씨 + 빈 줄로 문단 분리(프롬프트와 폴백 캔 질문 양쪽 다 수정), 채팅 아바타 아이콘 제거.
10. **고객통보 안정성**: 메일 본문의 `\n` 리터럴 방어 처리, 예상 고객 반응 어투 프롬프트 규칙 추가.

## 알려진 특성 / 주의할 점

- **RSS 실시간 모드**: 매번 스캔할 때마다 그 시점의 실제 기사를 가져오므로, 감지되는 사건 개수와 내용이 실행마다 달라진다(고정 아님). 발표용 안정성이 필요하면 캐시 모드(토글 끄기) 권장.
- **실시간 뉴스와 더미 화물의 불일치**: 라이브 RSS로 잡히는 실제 사건(예: 리비아 자위아 정유시설 공격)은 `data/shipments.csv`의 50건 화물(로테르담 파업 시나리오로 설계됨)과 지리적으로 안 겹칠 수 있어 "영향 화물 0건"이 자주 나온다 — 버그 아님, 데이터셋이 원래 별개 시나리오.
- **무료 Gemini 티어 한도**: RPM 15 / RPD 500. 트래픽이 많으면 빨리 소진될 수 있음.
- **`fallback/` 데이터의 신뢰도**: LLM이 계산한 숫자(특히 합계·건수)는 신뢰하지 않고, 가능한 경우 코드에서 결정론적으로 재계산한다(`not_affected_count` 등).
