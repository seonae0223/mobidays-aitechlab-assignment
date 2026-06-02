# PRD: 회의록 자동 정리 및 액션아이템 추출 시스템

> 이 파일은 Claude Code가 구현 시 참조하는 설계 지시서입니다.
> 코드를 짜기 전에 반드시 이 문서 전체를 읽고 시작하세요.
> 설계 변경이 필요한 경우 임의로 변경하지 말고 먼저 질문하세요.

---

## 1. 프로젝트 개요

회의 음성(mp3) 또는 transcript JSON을 입력받아:
1. 텍스트 정제
2. LLM 기반 액션아이템 추출
3. DuckDB 적재
4. Streamlit 대시보드 시각화

까지 한 흐름으로 동작하는 로컬 실행 가능한 Python 시스템입니다.

---

## 2. 기술 스택 (확정, 변경 금지)

| 항목 | 선택 | 비고 |
|---|---|---|
| 언어 | Python 3.10+ | |
| DB | DuckDB | SQLite/Postgres 사용 금지 |
| 대시보드 | Streamlit | |
| LLM | Gemini API (Google) | 모델: gemini-flash-latest |
| STT | faster-whisper (로컬) | 외부 STT API 사용 금지 |
| 데이터 처리 | pandas | |
| 환경변수 | python-dotenv | |

---

## 3. 프로젝트 구조 (확정, 변경 금지)

```
mobidays-ai-techlab/
├── data/
│   ├── ko_meeting_3speakers_4min_faster.mp3
│   └── ko_meeting_3speakers.json
├── pipeline/
│   ├── stt.py
│   ├── cleaner.py
│   ├── loader.py
│   └── extractor.py
├── dashboard/
│   └── app.py
├── db/
│   └── .gitkeep
├── main.py
├── Makefile
├── requirements.txt
├── .env.example
├── .gitignore
├── PRD.md
├── README.md
└── AI_USAGE.md
```

---

## 4. 데이터베이스 스키마 (확정, 변경 금지)

### 4.1 meetings 테이블

```sql
CREATE TABLE IF NOT EXISTS meetings (
    meeting_id    TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    advertiser    TEXT NOT NULL,
    meeting_date  DATE NOT NULL,
    participants  TEXT NOT NULL,  -- JSON 문자열
    source_file   TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT current_timestamp
);
```

**meeting_id 생성 규칙:**
```python
# 파일명에서 확장자 제거
meeting_id = Path(source_file).stem
# 예: "ko_meeting_3speakers.json" → "ko_meeting_3speakers"
```

**participants 저장 형식:**
```json
[{"name": "지훈", "role": "마케팅 팀장"},
 {"name": "수아", "role": "퍼포먼스 마케터"},
 {"name": "채린", "role": "콘텐츠 디자이너"}]
```

### 4.2 speech_segments 테이블

```sql
CREATE TABLE IF NOT EXISTS speech_segments (
    segment_id    TEXT PRIMARY KEY,
    meeting_id    TEXT NOT NULL REFERENCES meetings(meeting_id),
    speaker       TEXT NOT NULL,
    role          TEXT NOT NULL,
    original_text TEXT NOT NULL,
    cleaned_text  TEXT,           -- NULL 허용: 정제 후 빈 발화
    chunk_index   INTEGER,        -- NULL 허용: 청크 분리 후 채워짐
    created_at    TIMESTAMP DEFAULT current_timestamp
);
```

**segment_id 생성 규칙:**
```python
segment_id = f"{meeting_id}_{str(segment['id']).zfill(3)}"
# 예: "ko_meeting_3speakers_001"
```

### 4.3 action_items 테이블

```sql
CREATE TABLE IF NOT EXISTS action_items (
    action_id         TEXT PRIMARY KEY,
    meeting_id        TEXT NOT NULL REFERENCES meetings(meeting_id),
    action            TEXT NOT NULL,
    assignee          TEXT,         -- NULL 허용: 담당자 불명확
    deadline          TEXT,         -- NULL 허용: TEXT 타입 (DATE 아님)
    status            TEXT DEFAULT 'todo',
    confidence        FLOAT NOT NULL,
    source_utterance  TEXT,         -- NULL 허용
    created_at        TIMESTAMP DEFAULT current_timestamp
);
```

**action_id 생성 규칙:**
```python
action_id = f"{meeting_id}_action_{str(idx+1).zfill(3)}"
# 예: "ko_meeting_3speakers_action_001"
```

**deadline은 반드시 TEXT로 저장합니다. DATE 파싱 시도 금지.**
예: "내일 오전", "수요일 오전", "목요일 오후" 그대로 저장

---

## 5. 파이프라인 상세 명세

### 5.1 main.py (진입점)

```python
# 실행 방식 2가지를 모두 지원해야 합니다
# 방식 1: mp3 파일 입력 (Whisper STT 사용)
python main.py --input mp3 --file data/ko_meeting_3speakers_4min_faster.mp3

# 방식 2: transcript JSON 입력 (STT 생략)
python main.py --input json --file data/ko_meeting_3speakers.json
```

실행 순서:
1. 입력 방식에 따라 stt.py 또는 JSON 로드
2. cleaner.py 정제
3. loader.py DuckDB 적재
4. extractor.py LLM 추출
5. 완료 메시지 출력

### 5.2 pipeline/stt.py

- faster-whisper 사용 (로컬 실행, 외부 API 금지)
- 모델: base 또는 small (속도 우선)
- 출력 형식: ko_meeting_3speakers.json과 동일한 구조로 반환

```python
def run_stt(mp3_path: str) -> dict:
    # 반환 형식
    return {
        "language": "ko",
        "speaker_count": N,
        "segment_count": N,
        "speakers": [...],
        "segments": [
            {"id": 1, "line_no": 1, "speaker": "SPEAKER_00",
             "role": "", "text": "..."}
        ]
    }
```

**주의:** STT는 화자 분리가 어려울 수 있습니다. 화자명은 "SPEAKER_00" 형식으로 저장하고, role은 빈 문자열로 둡니다.

### 5.3 pipeline/cleaner.py

**처리 순서:**

1. **머뭇거림 제거**
```python
FILLER_PATTERNS = [
    r'\b어+\.{0,3}', r'\b음+\.{0,3}', r'\b아+\s',
    r'그게\s*,', r'아\s*그게', r'어\s*그건'
]
```

2. **광고·마케팅 약어 사전 적용**
```python
ABBREVIATION_DICT = {
    "CTA": "클릭 유도 버튼(CTA)",
    "ROAS": "광고 수익률(ROAS)",
    "CPM": "1000회 노출당 비용(CPM)",
    "CTR": "클릭 전환율(CTR)",
    "A/B": "A/B 테스트",
    "GA": "구글 애널리틱스(GA)",
    "PoC": "개념 검증(PoC)",
    "R&R": "역할과 책임(R&R)"
}
```

3. **흐릿한 표현 플래그**
```python
VAGUE_PATTERNS = [
    "잠정적으로", "일단 두고", "아마", "그건 이따가",
    "나중에", "한번 봐요", "어떻게 될지", "두고 봐요"
]
# 발화에 이 표현이 포함되면 is_vague=True 플래그
```

4. **빈 발화 처리**
- 정제 후 10자 미만이면 cleaned_text = None

5. **청크 분리**
- 5~8개 발화 단위로 묶기
- 화자가 바뀌는 지점 우선 고려
- chunk_index 부여

**반환 형식:**
```python
def clean(transcript: dict) -> list[dict]:
    return [
        {
            "segment_id": "ko_meeting_3speakers_001",
            "meeting_id": "ko_meeting_3speakers",
            "speaker": "지훈",
            "role": "마케팅 팀장",
            "original_text": "자, 다들 들어오셨나. 어… 오늘은...",
            "cleaned_text": "자, 다들 들어오셨나. 오늘은...",
            "chunk_index": 1,
            "is_vague": False
        },
        ...
    ]
```

### 5.4 pipeline/loader.py

**멱등성 구현 (핵심):**

```python
def load_to_db(meeting_data: dict, segments: list, db_path: str = "db/meeting.duckdb"):

    conn = duckdb.connect(db_path)

    # 테이블 생성 (없을 때만)
    conn.execute(CREATE_MEETINGS_SQL)
    conn.execute(CREATE_SPEECH_SEGMENTS_SQL)
    conn.execute(CREATE_ACTION_ITEMS_SQL)

    # 멱등성 체크: 이미 적재된 회의면 스킵
    existing = conn.execute(
        "SELECT 1 FROM meetings WHERE meeting_id = ?",
        [meeting_data["meeting_id"]]
    ).fetchone()

    if existing:
        print(f"[SKIP] {meeting_data['meeting_id']} 이미 적재됨. 스킵합니다.")
        conn.close()
        return

    # meetings 적재
    conn.execute(INSERT_MEETING_SQL, [...])

    # speech_segments 적재
    for segment in segments:
        conn.execute(INSERT_SEGMENT_SQL, [...])

    print(f"[OK] {meeting_data['meeting_id']} 적재 완료")
    conn.close()
```

### 5.5 pipeline/extractor.py

**청크 단위로 LLM 호출:**

```python
def extract_actions(segments: list, meeting_id: str) -> list[dict]:
    # chunk_index 기준으로 그룹핑
    chunks = group_by_chunk(segments)

    all_actions = []
    for chunk in chunks:
        actions = call_llm_with_retry(chunk, meeting_id, max_retries=3)
        all_actions.extend(actions)

    return all_actions
```

**LLM 프롬프트 구조:**

```
[system]
당신은 광고·마케팅 회의에서 액션아이템을 추출하는 전문가입니다.
회의에서 CTA, ROAS, CPM, A/B 테스트 등 광고 용어가 자주 등장합니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

[few-shot 예시 1 - 명확한 케이스]
발화: "네 오늘 안에 보정하고 내일 오전엔 공유드릴게요" (수아/퍼포먼스 마케터)
출력:
{"action": "픽셀 보정 후 수치 공유", "assignee": "수아", "deadline": "내일 오전",
 "source_utterance": "네 오늘 안에 보정하고 내일 오전엔 공유드릴게요"}

[few-shot 예시 2 - 불명확한 케이스]
발화: "그거 컨펌은 누가 받기로 했죠. 아 내가 받기로 했었나…" (지훈/마케팅 팀장)
출력:
{"action": "광고주 컨펌 수령", "assignee": null, "deadline": null,
 "source_utterance": "그거 컨펌은 누가 받기로 했죠"}

[user]
다음 회의 발화에서 액션아이템을 추출하세요.
액션아이템이 없으면 빈 배열 []을 반환하세요.

{chunk_text}

반드시 아래 JSON 형식으로만 응답하세요:
[
  {
    "action": "할 일 내용",
    "assignee": "담당자 이름 또는 null",
    "deadline": "마감 표현 그대로 또는 null",
    "source_utterance": "근거 발화 원문"
  }
]
```

**재시도 로직:**

```python
def call_llm_with_retry(chunk, meeting_id, max_retries=3):
    for attempt in range(max_retries):
        response = call_claude_api(chunk)
        try:
            actions = json.loads(response)
            if validate_schema(actions):
                return enrich_with_confidence(actions, chunk)
        except (json.JSONDecodeError, ValueError):
            pass
        # 재시도 시 프롬프트에 강조 추가
    # 3회 실패 시 confidence 0.0으로 저장
    return [{"action": "추출 실패", "assignee": None,
             "deadline": None, "confidence": 0.0,
             "source_utterance": None}]
```

**Confidence 계산 (룰 기반, 확정):**

```python
def calculate_confidence(action: dict, chunk_segments: list) -> float:
    score = 0.0

    # 마감 구체적 명시 +0.35
    if action.get("deadline"):
        score += 0.35

    # 담당자 명시 +0.30
    if action.get("assignee"):
        score += 0.30

    # 근거 발화 존재 +0.20
    if action.get("source_utterance"):
        score += 0.20

    # 흐릿한 표현 없음 +0.15
    VAGUE_PATTERNS = ["잠정적으로", "일단 두고", "아마", "그건 이따가",
                      "나중에", "한번 봐요", "어떻게 될지", "두고 봐요"]
    source = action.get("source_utterance", "") or ""
    if not any(v in source for v in VAGUE_PATTERNS):
        score += 0.15

    return round(score, 2)
```

---

## 6. 대시보드 명세 (dashboard/app.py)

**위젯 4개 필수 구현:**

### 위젯 1. 주차별 회의·액션아이템 발생 추이
```sql
SELECT
    DATE_TRUNC('week', meeting_date) AS week,
    COUNT(DISTINCT m.meeting_id) AS meeting_count,
    COUNT(a.action_id) AS action_count
FROM meetings m
LEFT JOIN action_items a ON m.meeting_id = a.meeting_id
GROUP BY week
ORDER BY week
```
→ 라인 차트 또는 바 차트

### 위젯 2. 담당자별 미완료 액션아이템 Top N
```sql
SELECT assignee, COUNT(*) as count
FROM action_items
WHERE status = 'todo' AND assignee IS NOT NULL
GROUP BY assignee
ORDER BY count DESC
LIMIT 10
```
→ 바 차트. N은 슬라이더로 조절 가능하게

### 위젯 3. 캠페인/광고주별 반복 이슈 키워드
```sql
SELECT m.advertiser, a.action
FROM action_items a
JOIN meetings m ON a.meeting_id = m.meeting_id
```
→ action 텍스트에서 TF-IDF 또는 단순 단어 빈도로 키워드 추출
→ 광고주별 상위 키워드 테이블 또는 워드클라우드

### 위젯 4. LLM confidence 분포 + 낮은 항목 드릴다운
```sql
SELECT action_id, action, assignee, deadline,
       confidence, source_utterance
FROM action_items
ORDER BY confidence ASC
```
→ 히스토그램으로 분포 표시
→ confidence < 0.5 항목은 테이블로 드릴다운 (source_utterance 함께 표시)

**대시보드 설계 원칙:**
단순 차트 나열이 아니라 "의사결정자가 무엇을 보고 무엇을 결정할 수 있는가"가 흐름으로 보여야 합니다.

---

## 7. Makefile

```makefile
.PHONY: run dashboard install

install:
	pip install -r requirements.txt

run:
	python main.py --input json --file data/ko_meeting_3speakers.json

run-mp3:
	python main.py --input mp3 --file data/ko_meeting_3speakers_4min_faster.mp3

dashboard:
	streamlit run dashboard/app.py
```

---

## 8. .env.example

```
ANTHROPIC_API_KEY=your_api_key_here
```

---

## 9. .gitignore

```
.env
db/*.duckdb
__pycache__/
*.pyc
.DS_Store
```

---

## 10. AI_USAGE.md 업데이트 규칙

각 파일 구현이 완료될 때마다 AI_USAGE.md의 "작업 로그" 섹션에 아래 형식으로 자동 추가하세요.

```markdown
### [파일명] - 구현 완료
- Claude Code가 한 것: (구현한 내용 간략히 자동 작성)
- 사용한 프롬프트 요약: (어떤 지시를 받았는지 자동 작성)
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]
```

**규칙:**
- "Claude Code가 한 것"과 "사용한 프롬프트 요약"은 Claude Code가 자동으로 작성
- "내가 수정한 것"과 "수정 이유"는 반드시 [입력 필요]로 표시해두고 비워둘 것
- [입력 필요] 부분은 사용자가 직접 채워야 함
- 수정한 것이 없으면 "수정 없음"이라고 써도 됨
- 보고서처럼 쓰지 말고 작업 로그처럼 쓸 것

---

## 11. 중요 제약사항 (반드시 준수)

1. **외부 데이터 전송 금지**: 회의 원천 데이터를 외부 SaaS·공개 API로 전송 금지. Whisper는 로컬 실행.
2. **멱등성 필수**: 파이프라인 재실행 시 중복 적재 없어야 함. meeting_id PK로 체크.
3. **deadline은 TEXT**: DATE 파싱 시도 금지.
4. **confidence는 룰 기반**: LLM 자체 confidence 사용 금지. 위 calculate_confidence 함수 그대로 사용.
5. **재시도 최대 3회**: LLM 호출 무한루프 금지.
6. **설계 임의 변경 금지**: 스키마, 파일 구조, confidence 룰은 확정된 설계. 변경 필요 시 먼저 질문.
