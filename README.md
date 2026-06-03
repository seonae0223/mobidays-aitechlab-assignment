# 회의록 자동 정리 및 액션아이템 추출 시스템

회의 음성 또는 transcript JSON을 입력받아, 액션아이템을 자동으로 추출하고 분석 대시보드로 시각화하는 데이터, AI 시스템입니다.

---

## 한 줄 실행

```bash
make run
```

---

## 파일명 포맷 규칙

이 파이프라인은 파일명에서 회의 메타데이터를 자동으로 읽습니다. **파일을 제출하기 전에 반드시 아래 포맷을 맞춰주세요.**

```
{advertiser}_{YYYYMMDD}_{title}.mp3
{advertiser}_{YYYYMMDD}_{title}.json
```

| 항목 | 설명 | 예시 |
|---|---|---|
| `advertiser` | 광고주명 | `노바드림` |
| `YYYYMMDD` | 회의 날짜 8자리 | `20260601` |
| `title` | 회의 제목 | `캠페인사전정렬회의` |

**올바른 예시:**
```
노바드림_20260601_캠페인사전정렬회의.json
노바드림_20260601_캠페인사전정렬회의.mp3
```

**규칙:**
- `advertiser`와 `title`에 언더스코어(`_`) 사용 금지 — 구분자로 예약됨
- 날짜는 반드시 `YYYYMMDD` 8자리 숫자
- 포맷 불일치 시 파이프라인이 즉시 오류 메시지와 함께 종료됨

**실행 환경:**
- macOS / Linux 권장
- Windows 사용 시 터미널에서 `chcp 65001` 실행 후 사용 (UTF-8 설정 필요)

---

## 실행 환경

- Python 3.10 이상
- 로컬 환경 (서버 불필요)

```bash
# 1. 패키지 설치
pip3 install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에 아래 두 값 입력:
#   GEMINI_API_KEY  → https://aistudio.google.com 에서 무료 발급 (Get API Key)
#   SLACK_WEBHOOK_URL → 선택사항. 없으면 samples/slack_payload.json 파일만 저장됨

# 3. 전체 파이프라인 실행 (STT → 정제 → 적재 → 추출 → Slack 알림)
make run

# 4. 대시보드 실행 (두 가지 방법 중 택1)
make dashboard
# 또는
python3 -m streamlit run dashboard/app.py
```

### 입력 방식 선택

```bash
# mp3 파일로 실행 (Whisper STT 사용)
python3 main.py --input mp3 --file "data/노바드림_20260601_캠페인사전정렬회의.mp3"

# transcript JSON으로 실행 (STT 생략)
python3 main.py --input json --file "data/노바드림_20260601_캠페인사전정렬회의.json"
```

---

## 아키텍처 및 데이터 흐름

<img width="1693" height="873" alt="아키텍처" src="https://github.com/user-attachments/assets/83f4553d-5d9a-4d2e-b8db-209c59677d87" />


### 모듈 분리 기준

각 파일이 단일 책임을 가지도록 설계했습니다. STT 모듈을 교체하거나 DB를 변경할 때 다른 모듈에 영향이 없습니다.

---

## 기술 스택 선택 근거

### DuckDB (SQLite / Postgres 대비)

| | SQLite | **DuckDB** | Postgres |
|---|---|---|---|
| 설치 | 불필요 | **불필요** | 서버 필요 |
| 집계 쿼리 | 느림 (행 기반) | **빠름 (컬럼 기반)** | 빠름 |
| make run 단순함 | 좋음 | **좋음** | 복잡 |

대시보드 위젯 5개가 전부 집계 쿼리입니다. SQLite는 행 기반이라 집계가 느리고, Postgres는 서버가 필요해 로컬 재현성이 낮습니다. DuckDB는 파일 하나로 관리되며 컬럼형 집계에 최적화되어 있어 선택했습니다.

### Gemini API (Google) (LLM)

무료 티어 제공, 한국어 성능, 구조화 출력(JSON) 지원이 이유입니다. 모델: `gemini-3.1-flash-lite-preview`.

### Whisper (STT)

회의 내용에 광고주 정보가 포함되어 외부 SaaS·공개 API로 원천 데이터 전송이 금지된 제약 조건 때문에 로컬 처리 방식인 Whisper를 선택했습니다.

### Python 스크립트 (Airflow/n8n 대비)

PoC 규모(샘플 1건, 로컬 실행)에서 Airflow는 오버엔지니어링입니다. 빌트온에서 Airflow 파이프라인을 설계한 경험이 있어 멱등성·단계별 모듈 분리·실패 처리 개념을 Python 스크립트에 동일하게 적용했습니다.

---

## 프롬프트 설계 근거

### 도메인 컨텍스트

LLM에게 광고·마케팅 회의라는 도메인 컨텍스트를 명시했습니다. CTA, ROAS, A/B 등 약어가 등장하는 환경임을 system prompt에 포함합니다.

### few-shot (6개)

6가지 케이스를 포함합니다.

```
예시 1 (익일 마감):   "오늘 안에 보정하고 내일 오전엔 공유드릴게요"
→ assignee: "수아", deadline: "2026-06-02 오전 (내일 오전)"

예시 2 (요일 마감):   "캠페인 세트 분리는 수요일 오전까지 해놓을게요"
→ assignee: "수아", deadline: "2026-06-03 오전 (수요일 오전까지)"

예시 3 (수행 중 행동): "오전에 담당자에게 요청했는데 아직 답이 없어요"
→ assignee: "수아" (발화자가 담당자), deadline: null

예시 4 (담당자 불명확): "그거 컨펌은 누가 받기로 했죠"
→ assignee: null, deadline: null

예시 5 (아젠다 나열):  "채널별 성과랑 예산 배분 좀 보고, 봐야 할 것 같아요"
→ [] (아젠다 발화, 액션아이템 아님)

예시 6 (재확인 확정): "제안서는 어쨌든 목요일 오후 그대로 가는 거니까"
→ action: "제안서 제출", deadline: "2026-06-04 오후 (목요일 오후)"
```

### deadline 날짜 추론

회의 날짜를 기준으로 자연어 마감 표현을 실제 날짜로 추론합니다.

```
"내일 오전"          → "2026-06-02 오전 (내일 오전)"
"수요일 오전까지"    → "2026-06-03 오전 (수요일 오전까지)"
"다음 주 목요일 오후" → "2026-06-11 오후 (다음 주 목요일 오후)"
"결과 나오는 대로"   → null (추론 불가)
```

### 추출 기준 및 담당자 추론 규칙

확정 약속 발화만 추출하고 아젠다·예측 발화는 제외합니다.

```
추출 O: "~할게요", "~해주세요", "~그대로 가는 거" (재확인 확정)
추출 X: "~봐야 할 것 같아요" (아젠다), "~할 것 같아요" (단순 예측)

담당자 규칙:
"제가 챙길게요" → 발화자가 담당자
"오전에 요청했는데" → 발화자가 담당자 (이미 수행 중)
"누가 하기로 했죠" → null (불명확)
```

청크 간 컨텍스트 전달로 중복 추출을 방지합니다.(직전 청크 추출 결과를 다음 청크 프롬프트에 포함)

### 스키마 강제

JSON 형식을 명시하고, 형식 위반 시 최대 3회 재시도합니다.

### 검증/재시도 전략

3회 재시도 후에도 실패하면 해당 청크는 confidence 0.0으로 저장하고 플래그 처리합니다.

---

## Confidence 룰

LLM 자체 confidence는 모델의 종류, temperature에 따라 기준이 달라지는 블랙박스 영역이므로, 룰 기반으로 계산하며, 지속적인 수정과 정교화가 가능합니다.

| 조건 | 가중치 | 근거 |
| --- | --- | --- |
| 마감 구체적 명시 | +0.35 | 마감 없는 액션아이템은 실행되지 않을 가능성 높음 |
| 담당자 명시 | +0.30 | 담당자 없으면 아무도 안 할 수 있음 |
| 근거 발화 존재 | +0.20 | source_utterance가 있으면 hallucination이 아닐 가능성 높음 |
| 흐릿한 표현 없음 | +0.15 | "잠정적으로", "일단", "아마" 등 불확실 표현 감지 |

---

## 가정 사항

- `deadline`은 `"YYYY-MM-DD (원문 표현)"` 형식으로 저장 (TEXT 타입, DATE 파싱 없음)
- 샘플 데이터 1건 기준으로 confidence 룰을 설계했으며, 실제 운영 시 추가 데이터로 조정 필요
- 외부 API 전송 금지 제약으로 Whisper 로컬 처리, Gemini API는 원천 데이터가 아닌 정제된 텍스트만 전달
- 과제 마감 시간 제약 상, 음성파일 -> Whisper 활용하여 STT 변환 -> input data로 활용 로직을 구현하였으나, 실운영 과정을 실험해보지 못했다는 한계점 발생

---

## 프로젝트 구조

```
mobidays-ai-techlab/
├── data/
│   ├── 노바드림_20260601_캠페인사전정렬회의.mp3
│   └── 노바드림_20260601_캠페인사전정렬회의.json
├── pipeline/
│   ├── __init__.py
│   ├── stt.py
│   ├── cleaner.py
│   ├── loader.py
│   ├── extractor.py
│   └── notifier.py
├── dashboard/
│   └── app.py
├── samples/
│   └── slack_payload.json
├── db/
│   └── .gitkeep
├── main.py
├── Makefile
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── AI_USAGE.md
```
