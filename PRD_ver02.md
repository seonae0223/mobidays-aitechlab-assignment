# PRD: 회의록 자동 정리 및 액션아이템 추출 시스템

> 이 파일은 Claude Code가 구현 시 참조하는 설계 지시서입니다.
> 코드를 짜기 전에 반드시 이 문서 전체를 읽고 시작하세요.
> 설계 변경이 필요한 경우 임의로 변경하지 말고 먼저 질문하세요.

**버전 이력**
| 버전 | 날짜 | 주요 변경 |
|---|---|---|
| v01 | 2026-06-01 | 최초 작성 |
| v02 | 2026-06-02 | LLM → Gemini API, 파일명 컨벤션 도입, cleaner 상수 확장, loader.py load_actions() 추가, 대시보드 차트 라이브러리 확정 |
| v02.1 | 2026-06-03 | deadline 날짜 추론 프롬프트 개선, notifier.py Slack 알림 추가 |
| v02.2 | 2026-06-03 | extractor.py 프롬프트 대규모 개선(추출기준·담당자추론·few-shot 6개·청크간컨텍스트전달), 모델 변경, rate limiting 추가 |

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
| 대시보드 | Streamlit | 차트: Altair |
| LLM | Gemini API (Google) | 모델: gemini-3.1-flash-lite-preview |
| STT | faster-whisper (로컬) | 외부 STT API 사용 금지 |
| 데이터 처리 | pandas | |
| 환경변수 | python-dotenv | |

---

## 3. 프로젝트 구조 (확정, 변경 금지)

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
├── PRD.md
├── PRD_ver02.md
├── README.md
└── AI_USAGE.md
```

---

## 3.1 파일명 컨벤션 (입력 파일 필수 준수)

파이프라인은 **파일명에서 회의 메타데이터를 자동 파싱**합니다.
입력 파일은 반드시 아래 포맷을 따라야 합니다.

**포맷:**
```
{advertiser}_{YYYYMMDD}_{title}.mp3
{advertiser}_{YYYYMMDD}_{title}.json
```

**규칙:**
- `advertiser`와 `title`에 언더스코어(`_`) 사용 금지 — 구분자로 예약됨
- 날짜는 반드시 8자리 숫자 (YYYYMMDD)
- 포맷 불일치 시 파이프라인 즉시 종료 + 오류 메시지 출력

**예시:**
```
노바드림_20260601_캠페인사전정렬회의.json
노바드림_20260601_캠페인사전정렬회의.mp3
```

**파싱 규칙:**
```python
# 정규식: ^([^_]+)_(\d{8})_([^_]+)$
stem = Path(source_file).stem
advertiser, date_str, title = stem.split("_", 2)  # maxsplit=2
meeting_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
```

**실행 환경:**
- macOS / Linux 권장
- Windows 사용 시 터미널 UTF-8 설정 필요 (`chcp 65001`)

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
# 예: "노바드림_20260601_캠페인사전정렬회의.json" → "노바드림_20260601_캠페인사전정렬회의"
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
# 예: "노바드림_20260601_캠페인사전정렬회의_001"
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
# 예: "노바드림_20260601_캠페인사전정렬회의_action_001"
```

**deadline은 반드시 TEXT로 저장합니다. DATE 파싱 시도 금지.**
LLM이 회의 날짜 기준으로 실제 날짜를 추론하여 `"YYYY-MM-DD (원문 표현)"` 형식으로 저장.
예: "내일 오전" → "2026-06-02 오전 (내일 오전)", "수요일 오전까지" → "2026-06-03 오전 (수요일 오전까지)"
날짜 추론 불가 표현("결과 나오는 대로", "이따") → null

---

## 5. 파이프라인 상세 명세

### 5.1 main.py (진입점)

```python
# 실행 방식 2가지를 모두 지원해야 합니다
# 방식 1: mp3 파일 입력 (Whisper STT 사용)
python3 main.py --input mp3 --file "data/노바드림_20260601_캠페인사전정렬회의.mp3"

# 방식 2: transcript JSON 입력 (STT 생략)
python3 main.py --input json --file "data/노바드림_20260601_캠페인사전정렬회의.json"
```

**CLI 인자:**
- `--input` (필수): `mp3` 또는 `json`
- `--file` (필수): 입력 파일 경로. 파일명은 섹션 3.1 포맷을 따라야 함

**title, advertiser, meeting_date는 파일명에서 자동 파싱** (별도 CLI 인자 없음)

실행 순서:
1. 파일명에서 메타데이터 파싱 (포맷 불일치 시 즉시 종료)
2. 입력 방식에 따라 stt.py 또는 JSON 로드
3. cleaner.py 정제
4. loader.py DuckDB 적재 (meetings + speech_segments)
5. extractor.py LLM 추출
6. loader.py 액션아이템 적재 (`load_actions()`)
7. notifier.py Slack 알림 전송 (`build_slack_payload()` → `send_to_slack()`)
8. 완료 메시지 출력

### 5.2 pipeline/stt.py

- faster-whisper 사용 (로컬 실행, 외부 API 금지)
- 모델: base (속도 우선), device="auto" (GPU 자동 감지), compute_type="int8"
- 출력 형식: transcript JSON 파일 구조와 동일하게 반환

```python
def run_stt(mp3_path: str) -> dict:
    # 반환 형식
    return {
        "language": "ko",
        "speaker_count": 1,           # 화자 분리 미지원 → 1 고정
        "segment_count": N,
        "speakers": [{"name": "SPEAKER_00", "role": ""}],
        "segments": [
            {"id": 1, "line_no": 1, "speaker": "SPEAKER_00",
             "role": "", "text": "..."}
        ]
    }

def save_transcript(transcript: dict, mp3_path: str) -> str:
    # mp3 파일명 기반 JSON 자동 저장
    # 예: 노바드림_20260601_캠페인사전정렬회의.mp3
    #   → 노바드림_20260601_캠페인사전정렬회의.json
    output_path = Path(mp3_path).with_suffix(".json")
    ...
    return str(output_path)
```

**주의:** STT는 화자 분리 미지원. 화자명은 "SPEAKER_00" 형식으로 저장하고, role은 빈 문자열로 둡니다.

### 5.3 pipeline/cleaner.py

**함수 시그니처:**
```python
def clean(transcript: dict, source_file: str) -> list[dict]:
```
`source_file` 파라미터 추가 — meeting_id / segment_id 생성에 필요 (v01 대비 변경)

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
    # 기본
    "CTA": "클릭 유도 버튼(CTA)",
    "ROAS": "광고 수익률(ROAS)",
    "CPM": "1000회 노출당 비용(CPM)",
    "CTR": "클릭 전환율(CTR)",
    "A/B": "A/B 테스트",
    "GA": "구글 애널리틱스(GA)",
    "PoC": "개념 검증(PoC)",
    "R&R": "역할과 책임(R&R)",
    # 확장 (v02 추가)
    "CPC": "클릭당 비용(CPC)",
    "CPV": "조회당 비용(CPV)",
    "CPA": "전환당 비용(CPA)",
    "CVR": "전환율(CVR)",
    "ROI": "투자 대비 수익(ROI)",
    "KPI": "핵심 성과 지표(KPI)",
    "CAC": "고객 획득 비용(CAC)",
    "LTV": "고객 생애 가치(LTV)",
    "UTM": "UTM 추적 파라미터",
    "GDN": "구글 디스플레이 네트워크(GDN)",
    "DA":  "디스플레이 광고(DA)",
    "SA":  "검색 광고(SA)",
    "SNS": "소셜 미디어(SNS)",
    "UGC": "사용자 생성 콘텐츠(UGC)",
    "MOQ": "최소 주문 수량(MOQ)",
}
```

3. **흐릿한 표현 플래그**
```python
VAGUE_PATTERNS = [
    # 기본
    "잠정적으로", "일단 두고", "아마", "그건 이따가",
    "나중에", "한번 봐요", "어떻게 될지", "두고 봐요",
    # 확장 (v02 추가 — 실제 transcript에서 발견된 표현)
    "일단은", "우선은", "어떻게든",
    "되면 좋겠고", "해볼게요",
    "그렇게 갔죠?", "맞죠?",
    "했었나",
    "어 그건", "음 그게",
    "뭐 어떻게", "좀 봐야",
    "논의해봐야", "검토해볼게요",
    "될 것 같긴 한데", "같긴 한데",
    "아닌가",
]
# 발화에 이 표현이 포함되면 is_vague=True 플래그
# is_vague 판단은 정제 전 original_text 기준으로 수행
```

4. **빈 발화 처리**
- 정제 후 10자 미만이면 cleaned_text = None

5. **청크 분리**
- 화자가 바뀌고 현재 청크 크기 ≥ 5이면 새 청크 시작
- 현재 청크 크기 = 8이면 무조건 새 청크 시작 (하드 캡)
- chunk_index 부여

**반환 형식:**
```python
def clean(transcript: dict, source_file: str) -> list[dict]:
    return [
        {
            "segment_id": "노바드림_20260601_캠페인사전정렬회의_001",
            "meeting_id": "노바드림_20260601_캠페인사전정렬회의",
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

**함수 2개:**

```python
def load_to_db(meeting_data: dict, segments: list, db_path: str = "db/meeting.duckdb"):
    """meetings + speech_segments 적재. 동일 meeting_id 재실행 시 전체 스킵 (멱등성)."""
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

    conn.execute(INSERT_MEETING_SQL, [...])
    for segment in segments:
        conn.execute(INSERT_SEGMENT_SQL, [...])

    print(f"[OK] {meeting_data['meeting_id']} 적재 완료")
    conn.close()


def load_actions(actions: list, db_path: str = "db/meeting.duckdb"):
    """extractor.py가 반환한 액션아이템 목록을 action_items 테이블에 적재.
    main.py 5단계(extractor 실행 후)에서 호출."""
    ...
```

### 5.5 pipeline/notifier.py

**Slack Incoming Webhook 알림 모듈:**

```python
def build_slack_payload(meeting_data: dict, actions: list) -> dict:
    """Slack Block Kit 페이로드 생성.
    헤더 / 회의 메타 / 담당자별 액션 목록 / 담당자 미정 / 신뢰도 경고 / 푸터 구성.
    """

def save_slack_payload(payload: dict, output_path: str = "samples/slack_payload.json") -> str:
    """페이로드를 JSON 파일로 저장 (산출물 샘플)."""

def send_to_slack(payload: dict, webhook_url: str) -> bool:
    """urllib.request로 Slack Incoming Webhook에 POST 전송.
    SLACK_WEBHOOK_URL 미설정 시 파일만 저장하고 전송 생략.
    """
```

**환경변수:**
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

**산출물:** `samples/slack_payload.json` — 파이프라인 실행마다 갱신

### 5.6 pipeline/extractor.py

**청크 단위로 LLM 호출:**

```python
def extract_actions(segments: list, meeting_id: str, meeting_date: str) -> list[dict]:
    # meeting_date(YYYY-MM-DD)를 LLM에 전달해 deadline 날짜 추론에 활용
    chunks = group_by_chunk(segments)

    all_actions = []
    for chunk in chunks:
        actions = call_llm_with_retry(chunk, meeting_id, meeting_date, max_retries=3)
        all_actions.extend(actions)

    # PRD 4.3: action_id, meeting_id 전역 카운터로 일괄 주입
    result = []
    for idx, action in enumerate(all_actions):
        result.append({
            "action_id": f"{meeting_id}_action_{str(idx + 1).zfill(3)}",
            "meeting_id": meeting_id,
            **action,
        })
    return result
```

**LLM API 호출 (Gemini):**

```python
def _call_gemini_api(chunk_text: str, meeting_date: str, retry: bool = False) -> str:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(model_name=MODEL, system_instruction=_SYSTEM_PROMPT)
    user_content = _USER_PROMPT_TEMPLATE.format(
        meeting_date=meeting_date,
        meeting_day=_day_ko(meeting_date),  # "월"/"화"/... 한국어 요일
        chunk_text=chunk_text,
    )
    if retry:
        user_content += _RETRY_SUFFIX
    response = model.generate_content(user_content)
    return response.text
```

**청크 텍스트 포맷 (LLM 입력):**
```
발화: "{cleaned_text 또는 original_text}" (화자/역할)
발화: "네 오늘 안에 보정하고 내일 오전엔 공유드릴게요" (수아/퍼포먼스 마케터)
```

**LLM 프롬프트 구조:**

```
[system]
당신은 광고·마케팅 회의에서 액션아이템을 추출하는 전문가입니다.
회의에서 CTA, ROAS, CPM, A/B 테스트 등 광고 용어가 자주 등장합니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

[액션아이템 추출 기준]
아래 표현이 포함된 발화만 추출:
- 확정 약속: "~할게요", "~하겠습니다", "~맡겠습니다"
- 지시·요청: "~해주세요", "~부탁드려요", "~푸쉬할게요"
- 이미 수행 중인 행동: "~요청했는데", "~보냈는데" (발화자가 담당자)
- 재확인 확정: "~그대로", "~그대로 가는 거" (이미 합의된 사항 재확인)

아래 표현은 추출하지 않음:
- 회의 아젠다 나열: "~봐야 할 것 같아요", "~볼게 있어서"
- 단순 예측·가능성: "~할 것 같아요", "~가능할 것 같아요"
- 현황 보고: "~아직 못 했어요", "~진행 중이에요"

[담당자 추론 규칙]
- "제가 할게요", "제가 챙길게요" → 발화자가 담당자
- "오전에 요청했는데", "내가 보냈는데" → 발화자가 담당자 (이미 수행 중)
- "~해주세요", "~부탁드려요" → 지시 대상자가 담당자
- "누가 하기로 했죠", "누가 받기로 했나" → null (불명확)

[deadline 추론 규칙]
user 메시지에 제공된 회의 날짜를 기준으로 "YYYY-MM-DD (원문 표현)" 형식으로 반환.
- 당일 표현 → 회의 날짜 / 익일 표현 → +1일
- 요일 표현 → 회의 날짜 이후 가장 가까운 해당 요일
- "다음 주 ~요일" → 다음 주 해당 요일
- 추론 불가 ("이따", "결과 나오는 대로") → null

[few-shot 예시 1 - 확정 약속 / 2026-06-01 월요일]
발화: "네 오늘 안에 보정하고 내일 오전엔 공유드릴게요" (수아/퍼포먼스 마케터)
출력: {"action": "픽셀 보정 후 수치 공유", "assignee": "수아",
       "deadline": "2026-06-02 오전 (내일 오전)", ...}

[few-shot 예시 2 - 요일 마감 / 2026-06-01 월요일]
발화: "캠페인 세트 분리는 제가 수요일 오전까지 해놓을게요" (수아/퍼포먼스 마케터)
출력: {"action": "캠페인 세트 분리", "assignee": "수아",
       "deadline": "2026-06-03 오전 (수요일 오전까지)", ...}

[few-shot 예시 3 - 수행 중인 행동 → 발화자가 담당자]
발화: "오전 열 시쯤 담당자에게 요청했는데 아직 답이 없어요" (수아/퍼포먼스 마케터)
출력: {"action": "광고주 담당자에게 누끼 컷 전달 요청", "assignee": "수아",
       "deadline": null, ...}

[few-shot 예시 4 - 담당자·날짜 불명확]
발화: "그거 컨펌은 누가 받기로 했죠. 아 내가 받기로 했었나…" (지훈/마케팅 팀장)
출력: {"action": "광고주 컨펌 수령", "assignee": null, "deadline": null, ...}

[few-shot 예시 5 - 아젠다 나열 → 추출 안 함]
발화: "채널별 성과랑 예산 배분 좀 보고, 봐야 할 것 같아요" (수아/퍼포먼스 마케터)
출력: []

[few-shot 예시 6 - 재확인 확정 / 2026-06-01 월요일]
발화: "제안서는 어쨌든 목요일 오후 그대로 가는 거니까" (지훈/마케팅 팀장)
출력: {"action": "제안서 제출", "assignee": null,
       "deadline": "2026-06-04 오후 (목요일 오후)", ...}

[user]
회의 날짜: {meeting_date} ({meeting_day}요일)
{previous_actions_section}   ← 직전 청크 추출 결과 (중복 방지용, 첫 청크는 생략)

다음 회의 발화에서 액션아이템을 추출하세요.
액션아이템이 없으면 빈 배열 []을 반환하세요.

{chunk_text}

반드시 아래 JSON 형식으로만 응답하세요:
[{"action": "...", "assignee": "... 또는 null",
  "deadline": "YYYY-MM-DD (원문) 또는 null", "source_utterance": "..."}]
```

**청크 간 컨텍스트 전달 (중복 방지):**
```python
# extract_actions()에서 이전 청크 액션 목록을 다음 청크 프롬프트에 포함
all_actions = []
for chunk in chunks:
    actions = _call_llm_with_retry(chunk, meeting_id, meeting_date,
                                   previous_actions=all_actions)
    all_actions.extend(actions)
```
이미 추출된 액션아이템과 중복이면 추출하지 않도록 LLM에 지시.

**재시도 로직:**

```python
def call_llm_with_retry(chunk, meeting_id, meeting_date,
                        previous_actions=None, max_retries=3):
    for attempt in range(max_retries):
        response = _call_gemini_api(chunk_text, meeting_date,
                                    previous_actions=previous_actions,
                                    retry=(attempt > 0))
        try:
            actions = json.loads(response)
            if validate_schema(actions):
                return enrich_with_confidence(actions, chunk)
        except (json.JSONDecodeError, ValueError):
            pass
        except Exception as e:
            # API 오류(쿼터 초과 등) → 재시도 없이 즉시 실패 처리
            break
    return [{"action": "추출 실패", "assignee": None,
             "deadline": None, "confidence": 0.0,
             "source_utterance": None}]
```

**Rate Limiting:**
```python
# 무료 티어 RPM 한도 초과 방지 — 청크 사이 13초 대기
if i < len(chunks):
    time.sleep(13)
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
    # confidence 계산 전용 VAGUE_PATTERNS — cleaner.py 확장판과 별도 관리 (PRD 확정값 8개)
    VAGUE_PATTERNS = ["잠정적으로", "일단 두고", "아마", "그건 이따가",
                      "나중에", "한번 봐요", "어떻게 될지", "두고 봐요"]
    source = action.get("source_utterance", "") or ""
    if not any(v in source for v in VAGUE_PATTERNS):
        score += 0.15

    return round(score, 2)
```

---

## 6. 대시보드 명세 (dashboard/app.py)

**차트 라이브러리: Altair** (Streamlit 내장 의존성, 추가 설치 불필요)

**위젯 5개 구현 (v2 재구성):**

### ① KPI 카드 4개
- 총 액션아이템 수
- 담당자 미정 건수 (assignee IS NULL)
- 검수 필요 건수 (confidence < 0.5)
- 완료 건수 (status = 'done')

→ `st.columns(4)` + `st.metric()` 4개

### ② 전체 액션아이템 테이블 (핵심)
```sql
SELECT a.action, a.assignee, a.deadline, a.confidence, a.status,
       a.source_utterance, m.title, m.advertiser
FROM action_items a JOIN meetings m ON a.meeting_id = m.meeting_id
ORDER BY confidence ASC
```
→ confidence 낮은 순 기본 정렬
→ 담당자 multiselect 필터
→ ⚠️ 중복 의심 자동 감지: 같은 담당자 내 액션 키워드 교집합 있으면 뱃지 표시 (자동 제거 아님 — 사람이 판단)

### ③ 담당자별 미완료 액션아이템
```sql
SELECT assignee, COUNT(*) AS count
FROM action_items
WHERE status = 'todo' AND assignee IS NOT NULL
GROUP BY assignee
ORDER BY count DESC
```
→ Altair 가로 바 차트 (None 담당자 제외)

### ④ 주차별 회의·액션아이템 발생 추이
```sql
SELECT DATE_TRUNC('week', meeting_date) AS week,
       COUNT(DISTINCT m.meeting_id) AS meeting_count,
       COUNT(a.action_id) AS action_count
FROM meetings m
LEFT JOIN action_items a ON m.meeting_id = a.meeting_id
GROUP BY week ORDER BY week
```

**시각화 — 쌍막대 차트 (Altair xOffset)**
- 주차별로 회의 수 / 액션아이템 수 막대를 나란히(쌍으로) 표시
- 파란 바: 회의 수 / 주황 바: 액션아이템 수
- 레전드 상단 표시
- 각 바 위에 숫자 레이블 표시 (mark_text)
- X축 레이블: `N월 N주차` 형식
  ```python
  week_str = f"{d.month}월 {(d.day - 1) // 7 + 1}주차"
  ```
- long format 변환 후 `xOffset=alt.XOffset("구분:N")` 적용

### ⑤ LLM 신뢰도 분포 + 검수 드릴다운
```sql
SELECT action_id, action, assignee, deadline,
       confidence, source_utterance
FROM action_items ORDER BY confidence ASC
```

**분포 시각화 — 신호등 카드 3개 + 3구간 가로 바 차트**

| 구간 | 기준 | 색상 |
|---|---|---|
| 🔴 저신뢰 | confidence < 0.5 | 빨강 |
| 🟡 중간   | 0.5 ≤ confidence < 0.8 | 주황 |
| 🟢 고신뢰 | confidence ≥ 0.8 | 초록 |

→ 카드 3개로 건수 즉시 파악
→ 3구간 가로 바 차트로 비율 시각화 (히스토그램 미사용)

**상태 메시지**
- 검수 필요 항목 없음 → `✅ 검수 필요 항목 없음 — 전체 N건 추출 품질 양호`
- 검수 필요 항목 있음 → `⚠️ 검수 필요 N건 (저신뢰: N건 · 중복 의심: N건)`

**검수 드릴다운 테이블 — 저신뢰 + 중복 의심 통합**

검수 사유 조건:
- `confidence < 0.5` → "저신뢰"
- 같은 담당자 내 액션 키워드 교집합 → "⚠️ 중복 의심"
- 두 조건 동시 해당 → "저신뢰 · ⚠️ 중복 의심"

컬럼: 검수 사유 / 담당자 / 액션 내용 / 마감 / 신뢰도 / 근거 발화

**대시보드 설계 원칙:**
상단 KPI → 전체 목록 조감 → 세부 분석 순서로 흐름 구성.
"의사결정자가 무엇을 보고 무엇을 결정할 수 있는가"가 화면 흐름으로 보여야 합니다.

---

## 7. Makefile

```makefile
.PHONY: run dashboard install

install:
	pip3 install -r requirements.txt

run:
	python3 main.py --input json --file "data/노바드림_20260601_캠페인사전정렬회의.json"

run-mp3:
	python3 main.py --input mp3 --file "data/노바드림_20260601_캠페인사전정렬회의.mp3"

dashboard:
	streamlit run dashboard/app.py
```

---

## 8. .env.example

```
GEMINI_API_KEY=your_gemini_api_key_here
SLACK_WEBHOOK_URL=your_slack_webhook_url_here
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

## 10. 중요 제약사항 (반드시 준수)

1. **외부 데이터 전송 금지**: 회의 원천 데이터를 외부 SaaS·공개 API로 전송 금지. Whisper는 로컬 실행.
2. **멱등성 필수**: 파이프라인 재실행 시 중복 적재 없어야 함. meeting_id PK로 체크.
3. **deadline은 TEXT**: DATE 파싱 시도 금지.
4. **confidence는 룰 기반**: LLM 자체 confidence 사용 금지. 위 calculate_confidence 함수 그대로 사용.
5. **재시도 최대 3회**: LLM 호출 무한루프 금지.
6. **설계 임의 변경 금지**: 스키마, 파일 구조, confidence 룰은 확정된 설계. 변경 필요 시 먼저 질문.
7. **파일명 컨벤션 준수**: 입력 파일은 반드시 `{advertiser}_{YYYYMMDD}_{title}` 포맷. advertiser·title에 언더스코어 금지.
