# 회의록 자동 정리 및 액션아이템 추출 시스템 기획안

> 제출자: 선애  
> 포지션: AI Tech Lab 인턴십 (34기)  
> 제출일: 2026년 6월 3일

---

## 1. 문제 재정의

### 현재 상황
모비데이즈는 매주 광고주별 캠페인 회의를 운영한다. 회의가 끝나면 담당자가 수기로 회의록을 정리하고, 액션아이템을 사내 트래킹 시스템에 옮기는 흐름이다.

이 과정에서 두 가지 문제가 반복된다.

- **시간 비용**: 회의록 정리 + 액션아이템 수기 정리에 회의 후 약 30~60분 소요
- **품질 문제**: 한국어 회의 특성상 결정이 흐릿하게 끝나거나 R&R이 암묵적으로 처리되어 액션아이템 누락이 잦음

### 어떤 페인포인트를 먼저 해결할 것인가

두 문제 중 **품질 문제를 우선 해결 대상으로 정의**했다.

이유는 다음과 같다. 시간 비용은 자동화만 되면 해결되는 문제지만, 액션아이템 누락은 자동화만으로 해결되지 않는다. "누가, 언제, 무엇을" 하기로 했는지가 불명확한 채로 회의가 끝나는 구조적 문제이기 때문이다. 따라서 이 시스템의 핵심 목표는 단순 텍스트 변환이 아니라, **불명확한 발화에서 신뢰 가능한 액션아이템을 구조화하는 것**으로 정의했다.

### 해결 범위
```
회의 음성/transcript 입력
→ 텍스트 정제 (잡음 제거, 약어 정규화)
→ LLM 기반 액션아이템 추출 (담당자/마감/신뢰도)
→ DuckDB 적재
→ Streamlit 대시보드 시각화
→ Slack 자동 알림
```

---

## 2. 시스템 아키텍처

### End-to-end 흐름

```
[입력]
  mp3 파일 → Whisper STT → transcript
  또는
  transcript JSON (직접 입력)
        ↓
[pipeline/cleaner.py] 정제
  - 머뭇거림 제거 ("어…", "음…", "아 그게")
  - 광고·마케팅 약어 사전 적용 (CTA, ROAS, CPM, A/B 등 23개)
  - 흐릿한 표현 플래그 처리 ("잠정적으로", "일단", "아마" 등 21개)
  - 5~8개 발화 단위 청크 분리
        ↓
[pipeline/extractor.py] LLM 추출
  - Gemini API 호출 (few-shot 3개 + 구조화 출력)
  - 회의 날짜 기반 deadline 날짜 추론 ("내일 오전" → "2026-06-02 오전 (내일 오전)")
  - 액션아이템 JSON 추출 (action, assignee, deadline, confidence)
  - 룰 기반 confidence 계산
  - 스키마 위반 시 재시도 로직 (최대 3회)
        ↓
[pipeline/loader.py] DuckDB 적재
  - 멱등성 보장 (meeting_id PK 중복 방지)
  - meetings / speech_segments / action_items 3개 테이블
        ↓
[pipeline/notifier.py] Slack 알림 전송
  - Block Kit 형식 메시지 자동 생성
  - 담당자별 액션 목록 / 담당자 미정 / 신뢰도 낮은 항목 경고 포함
  - samples/slack_payload.json 파일 저장
        ↓
[dashboard/app.py] Streamlit 대시보드
  - 위젯 5개 (KPI 카드 / 전체 액션 테이블 / 담당자별 바차트 / 주차별 추이 / confidence 분포)
```

### 단계별 도구 선택 trade-off

| 단계 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| STT | Whisper (로컬) | 외부 STT API | 회의 내용에 광고주 정보 포함 → 외부 전송 금지 제약 |
| DB | DuckDB | SQLite / Postgres | 컬럼형 집계 쿼리 최적화 + 설치 없이 파일 하나로 관리 + make run 단순화 |
| LLM | Gemini API (`gemini-flash-latest`) | Claude API / OpenAI | 무료 티어 제공 + 한국어 성능 + 구조화 출력(JSON) 지원 |
| 파이프라인 | Python 스크립트 | Airflow / n8n | PoC 규모에서 오케스트레이션 툴은 오버엔지니어링 |
| 대시보드 | Streamlit | Metabase | Python 친화적, 빠른 구현 |
| 알림 | Slack Webhook | 이메일 / 노션 | 사내 주 커뮤니케이션 채널, 별도 설치 없음 |

---

## 3. 데이터 스키마 설계 근거

### 3개 테이블 구조

```
meetings (1)
  └── speech_segments (N)
  └── action_items (N)
```

### meetings

| 컬럼 | 타입 | 제약 | 설계 근거 |
|---|---|---|---|
| meeting_id | TEXT | PK | 파일명 기반 고정 ID → 멱등성 키. 같은 파일을 두 번 돌려도 항상 같은 ID가 생성되어 PK 중복으로 재적재를 막음 |
| title | TEXT | NOT NULL | 회의 제목 없는 회의록은 의미 없음 |
| advertiser | TEXT | NOT NULL | 위젯 3번(광고주별 이슈 키워드) 필터링을 위해 별도 컬럼으로 분리 |
| meeting_date | DATE | NOT NULL | 위젯 1번(주차별 추이) 계산을 위해 DATE 타입 필수 |
| participants | TEXT | NOT NULL | JSON 문자열로 저장. PoC 규모에서 JOIN 비용 대비 실익 없음 → 의도적 비정규화 |
| source_file | TEXT | NOT NULL | 원본 파일 추적 및 디버깅용 |
| created_at | TIMESTAMP | DEFAULT now() | 적재 시각 자동 기록 |

### speech_segments

| 컬럼 | 타입 | 제약 | 설계 근거 |
|---|---|---|---|
| segment_id | TEXT | PK | meeting_id + 발화 순서 조합 → 멱등성 보장 |
| meeting_id | TEXT | FK | meetings와 연결 |
| speaker | TEXT | NOT NULL | 담당자 추출의 기반 |
| role | TEXT | NOT NULL | 발화자 역할로 LLM 프롬프트에서 지시사항 우선순위 구분 가능 |
| original_text | TEXT | NOT NULL | 원본 보존 원칙. 정제 로직 오류 시 복구 기준 |
| cleaned_text | TEXT | NULL 허용 | 정제 후 빈 발화는 NULL 처리 후 스킵 |
| chunk_index | INTEGER | NULL 허용 | 어떤 발화들이 같은 컨텍스트로 LLM에 전달됐는지 추적 |
| created_at | TIMESTAMP | DEFAULT now() | 적재 시각 |

### action_items

| 컬럼 | 타입 | 제약 | 설계 근거 |
|---|---|---|---|
| action_id | TEXT | PK | meeting_id + action 순서 조합 → 멱등성 |
| meeting_id | TEXT | FK | meetings와 연결 |
| action | TEXT | NOT NULL | 핵심 내용 |
| assignee | TEXT | NULL 허용 | 담당자 불명확한 발화 존재. 억지로 채우면 오히려 오염 |
| deadline | TEXT | NULL 허용 | DATE가 아닌 TEXT 이유: LLM이 회의 날짜 기준으로 실제 날짜를 추론하여 `"2026-06-02 오전 (내일 오전)"` 형식으로 저장. "결과 나오는 대로"처럼 추론 불가 표현은 null. DATE 타입 변환 시 파싱 오류 위험 원천 차단 |
| status | TEXT | DEFAULT 'todo' | 위젯 2번(미완료 Top N) 구현용. 향후 'in_progress' 등 상태 확장 고려 |
| confidence | FLOAT | NOT NULL | 룰 기반 신뢰도 점수 (0.0~1.0) |
| source_utterance | TEXT | NULL 허용 | LLM 추출 근거 발화 원문. hallucination 감지 및 드릴다운에 사용 |
| created_at | TIMESTAMP | DEFAULT now() | 적재 시각 |

### Confidence 룰 설계 근거

LLM이 자체적으로 반환하는 confidence는 모델·temperature에 따라 기준이 달라지는 블랙박스 영역이다. 룰 기반으로 직접 계산하면 (1) 왜 이 점수가 나왔는지 설명 가능하고 (2) 룰 수정으로 정교화 가능하다.

```
마감 구체적 명시      +0.35   마감 없는 액션아이템은 실행되지 않을 가능성 높음
담당자 명시           +0.30   담당자 없으면 아무도 안 할 수 있음
근거 발화 존재        +0.20   source_utterance가 있으면 hallucination이 아닐 가능성 높음
흐릿한 표현 없음      +0.15   "잠정적으로", "일단", "아마" 등 불확실 표현 감지
```

---

## 4. Before / After 임팩트 추정 (100명 기준)

### Before (현재)

| 항목 | 수치 | 근거 |
|---|---|---|
| 회의 후 정리 시간 | 30~60분/회의 | 과제 명시 수치 |
| 주간 회의 수 (추정) | 팀당 2~3건 | 광고주별 캠페인 회의 기준 |
| 월간 총 정리 시간 (100명) | 약 400~600시간 | 100명 × 주 2회 × 1시간 × 4주 |
| 액션아이템 누락률 | 정량 불가 (현재 수기) | 과제 명시: "누락이 잦음" |
| 담당자·마감 누락 | 빈번 | 한국어 회의 특성상 암묵적 R&R 처리 |
| 회의 후 Slack 공유 시간 | 10~20분/회의 추가 소요 | 액션아이템 별도 요약 후 수동 공유 |

### After (시스템 도입 후)

| 항목 | 예상 수치 | 근거 |
|---|---|---|
| 회의 후 정리 시간 | 5분 이내 | 자동 추출 후 검토만 |
| 절감 시간 | 월 350~550시간 | 정리 시간 90% 절감 가정 |
| Slack 공유 시간 | 0분 | 파이프라인 완료 시 자동 전송 |
| 액션아이템 누락률 | confidence < 0.5 항목 별도 검토 | 낮은 신뢰도 항목을 시스템이 플래그 |
| 마감 명확도 | "내일 오전" → "2026-06-02 오전 (내일 오전)" | LLM이 실제 날짜 자동 추론 |
| 품질 개선 | 담당자/마감 명시율 향상 | 구조화 출력으로 누락 방지 |

### 한계 및 가정
- 100명 전원이 동일한 회의 패턴이라고 가정
- Whisper STT 인식률에 따라 품질 편차 존재
- confidence 룰은 샘플 1건 기반으로 설계되어 실제 운영 시 조정 필요
- Gemini API 무료 쿼터(일 20회) 초과 시 유료 전환 또는 대안 모델 적용 필요

---

## 5. 실패 시나리오 및 대응

### 실패 시나리오 1. LLM이 스키마를 지키지 않는 경우

**상황**: Gemini API가 지정한 JSON 형식 대신 자연어로 응답하거나, 필드를 누락하거나, deadline 날짜 추론을 잘못 반환하는 경우

**대응**:
```python
for attempt in range(3):
    result = call_llm(prompt, meeting_date)
    if validate_schema(result):
        break
    else:
        prompt = add_retry_instruction(prompt)
        # "⚠️ 이전 응답이 올바른 JSON 형식이 아니었습니다..."
# 3회 실패 시 해당 청크 confidence = 0.0으로 저장 후 플래그
```

deadline 날짜 추론 오류 시 — confidence < 0.5 항목으로 자동 분류되어 대시보드 검수 테이블에 포함, 사람이 직접 확인

### 실패 시나리오 2. 동일 파일 중복 실행 (멱등성 위반 시도)

**상황**: 파이프라인을 실수로 두 번 실행하여 데이터가 중복 적재되는 경우

**대응**:
```python
existing = db.execute(
    "SELECT 1 FROM meetings WHERE meeting_id = ?", [meeting_id]
).fetchone()

if existing:
    print(f"[SKIP] {meeting_id} 이미 적재됨")
else:
    insert_meeting(...)
```

### 실패 시나리오 3. Whisper STT 품질 불량

**상황**: 배경 소음이 심하거나 전문 용어 인식률이 낮아 transcript 품질이 떨어지는 경우

**대응**:
- 입력 방식을 mp3/json 선택 가능하게 설계 → STT 품질 불량 시 검증된 transcript JSON으로 우회 가능
- STT 결과를 original_text로 보존, 수동 보정 후 재처리 가능
- 약어 사전을 post-processing 단계에서 별도 적용하여 STT 오류 부분 보완

### 실패 시나리오 4. Windows 환경에서 한글 파일명 인코딩 오류

**상황**: 100명 사원 중 Windows 사용자가 한글 파일명으로 파이프라인 실행 시 터미널 인코딩 문제로 파일명이 깨지는 경우

**단기 대응**:
```bash
chcp 65001  # UTF-8 설정
python main.py --input json --file data/노바드림_20260601_캠페인사전정렬회의.json
```
README에 Windows 설정 방법 명시

**장기 대응**:
- 영문 파일명 컨벤션으로 전환 (`novadream_20260601_campaign_meeting.json`)
- 또는 파일을 드래그앤드롭으로 선택할 수 있는 GUI 래퍼 개발

### 실패 시나리오 5. Gemini API 일일 쿼터 초과

**상황**: 100명이 동시에 파이프라인을 실행하거나, 하루 무료 쿼터(20회)를 초과하여 429 RESOURCE_EXHAUSTED 오류 발생

**단기 대응**:
- 실패 청크는 confidence 0.0으로 저장 후 플래그 — 다음날 재시도 가능
- 현재 PoC는 소수 사용자 기준으로 설계

**장기 대응**:
- 유료 API 플랜 전환 (팀 단위 공용 키 사용)
- 배치 처리 방식 도입: 회의 종료 후 즉시 처리가 아닌 야간 배치로 처리
- 청크 크기 최적화 (현재 5~8개 → 10~12개 확장 시 청크 수 절반)
