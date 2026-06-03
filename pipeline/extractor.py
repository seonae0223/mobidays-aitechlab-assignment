import json
import os
import time
from datetime import datetime
import google.generativeai as genai  # google-generativeai 패키지 사용
# NOTE: google.genai(신규 SDK)로 마이그레이션 시도 시 gemini-flash-latest 모델에서
# 503 UNAVAILABLE 지속 발생 (엔드포인트 차이 추정). 파이프라인 안정성 우선으로 기존 SDK 유지.
# 마이그레이션 재시도 조건: google.genai 1.x에서 gemini-flash-latest alias 지원 확인 후
from dotenv import load_dotenv

_DAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

def _day_ko(date_str: str) -> str:
    """'YYYY-MM-DD' 문자열을 받아 한국어 요일 반환 (예: '월')."""
    return _DAYS_KO[datetime.strptime(date_str, "%Y-%m-%d").weekday()]

load_dotenv()

# 모델 변경 이력: gemini-flash-latest → gemini-2.5-flash → gemini-2.5-flash-lite → gemini-flash-lite-latest
MODEL = "gemini-flash-lite-latest"

# PRD 5.5 확정값: confidence 계산 전용 흐릿한 표현 목록
# cleaner.py의 VAGUE_PATTERNS(사용자 확장판)와 별도 관리
# — PRD가 calculate_confidence를 "그대로" 사용하도록 명시했으므로 원문 8개 유지
_CONFIDENCE_VAGUE_PATTERNS = [
    "잠정적으로", "일단 두고", "아마", "그건 이따가",
    "나중에", "한번 봐요", "어떻게 될지", "두고 봐요",
]

# ── 프롬프트 ─────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """당신은 광고·마케팅 회의에서 액션아이템을 추출하는 전문가입니다.
회의에서 CTA, ROAS, CPM, A/B 테스트 등 광고 용어가 자주 등장합니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

[deadline 추론 규칙]
user 메시지에 제공된 회의 날짜를 기준으로, 발화의 날짜 표현을 실제 날짜로 추론하여
반드시 "YYYY-MM-DD (원문 표현)" 형식으로 반환하세요.
- 당일 표현 ("오늘", "오늘 안", "오늘 저녁") → 회의 날짜
- 익일 표현 ("내일", "하루 안") → 회의 날짜 + 1일
- 요일 표현 ("수요일", "목요일 오후") → 회의 날짜 이후 가장 가까운 해당 요일
- "다음 주 ~요일" → 다음 주 해당 요일
- 추론 불가 표현 ("이따", "결과 나오는 대로", "나중에") → null

[few-shot 예시 1 - 익일 마감 / 회의 날짜: 2026-06-01 월요일]
발화: "네 오늘 안에 보정하고 내일 오전엔 공유드릴게요" (수아/퍼포먼스 마케터)
출력:
{"action": "픽셀 보정 후 수치 공유", "assignee": "수아", "deadline": "2026-06-02 오전 (내일 오전)", "source_utterance": "네 오늘 안에 보정하고 내일 오전엔 공유드릴게요"}

[few-shot 예시 2 - 요일 마감 / 회의 날짜: 2026-06-01 월요일]
발화: "캠페인 세트 분리는 제가 수요일 오전까지 해놓을게요" (수아/퍼포먼스 마케터)
출력:
{"action": "캠페인 세트 분리", "assignee": "수아", "deadline": "2026-06-03 오전 (수요일 오전까지)", "source_utterance": "캠페인 세트 분리는 제가 수요일 오전까지 해놓을게요"}

[few-shot 예시 3 - 담당자·날짜 불명확]
발화: "그거 컨펌은 누가 받기로 했죠. 아 내가 받기로 했었나…" (지훈/마케팅 팀장)
출력:
{"action": "광고주 컨펌 수령", "assignee": null, "deadline": null, "source_utterance": "그거 컨펌은 누가 받기로 했죠"}"""

# 회의 날짜·요일을 user 메시지 상단에 포함해 LLM이 날짜 추론에 활용하도록 함
_USER_PROMPT_TEMPLATE = """회의 날짜: {meeting_date} ({meeting_day}요일)

다음 회의 발화에서 액션아이템을 추출하세요.
액션아이템이 없으면 빈 배열 []을 반환하세요.

{chunk_text}

반드시 아래 JSON 형식으로만 응답하세요:
[
  {{
    "action": "할 일 내용",
    "assignee": "담당자 이름 또는 null",
    "deadline": "YYYY-MM-DD (원문 표현) 또는 null",
    "source_utterance": "근거 발화 원문"
  }}
]"""

# PRD "재시도 시 프롬프트에 강조 추가" — 구체적 문구는 PRD 미명시, 사용자 확인 완료
_RETRY_SUFFIX = "\n\n⚠️ 이전 응답이 올바른 JSON 형식이 아니었습니다. 반드시 JSON 배열만 반환하세요. 다른 텍스트는 절대 포함하지 마세요."


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _format_chunk_text(chunk_segments: list) -> str:
    """발화 목록을 LLM 입력용 텍스트로 변환.

    PRD few-shot 예시 형식 준용: 발화: "{text}" (화자/역할)
    cleaned_text 우선 사용, 없으면 original_text 사용 — 사용자 확인 완료.
    """
    lines = []
    for seg in chunk_segments:
        text = seg.get("cleaned_text") or seg.get("original_text", "")
        speaker = seg.get("speaker", "")
        role = seg.get("role", "")
        lines.append(f'발화: "{text}" ({speaker}/{role})')
    return "\n".join(lines)


def _validate_schema(actions: list) -> bool:
    """LLM 응답이 유효한 액션아이템 배열인지 확인.

    list 타입이고 각 항목에 "action" 키가 있으면 유효 — 사용자 확인 완료.
    """
    if not isinstance(actions, list):
        return False
    for item in actions:
        if not isinstance(item, dict) or "action" not in item:
            return False
    return True


def calculate_confidence(action: dict, chunk_segments: list) -> float:
    """PRD 5.5 확정 룰 기반 confidence 계산. LLM 자체 confidence 사용 금지."""
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
    source = action.get("source_utterance", "") or ""
    if not any(v in source for v in _CONFIDENCE_VAGUE_PATTERNS):
        score += 0.15

    return round(score, 2)


def _enrich_with_confidence(actions: list, chunk_segments: list) -> list:
    """각 액션아이템에 confidence 점수를 추가하여 반환."""
    return [
        {**action, "confidence": calculate_confidence(action, chunk_segments)}
        for action in actions
    ]


def _call_gemini_api(chunk_text: str, meeting_date: str, retry: bool = False) -> str:
    """Gemini API 호출. retry=True이면 강조 문구를 프롬프트 끝에 추가."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=_SYSTEM_PROMPT,
    )
    user_content = _USER_PROMPT_TEMPLATE.format(
        meeting_date=meeting_date,
        meeting_day=_day_ko(meeting_date),
        chunk_text=chunk_text,
    )
    if retry:
        user_content += _RETRY_SUFFIX

    response = model.generate_content(user_content)
    return response.text


def _group_by_chunk(segments: list) -> list:
    """chunk_index 기준으로 발화를 청크 단위로 그룹핑.
    chunk_index가 None인 발화는 청크 1로 처리.
    """
    chunks: dict = {}
    for seg in segments:
        idx = seg.get("chunk_index") or 1
        chunks.setdefault(idx, []).append(seg)
    return [chunks[k] for k in sorted(chunks)]


def _call_llm_with_retry(chunk_segments: list, meeting_id: str, meeting_date: str, max_retries: int = 3) -> list:
    """청크 하나를 LLM에 넣어 액션아이템 추출. 최대 3회 재시도 (PRD 5.5)."""
    chunk_text = _format_chunk_text(chunk_segments)

    for attempt in range(max_retries):
        try:
            response = _call_gemini_api(chunk_text, meeting_date, retry=(attempt > 0))
            actions = json.loads(response)
            if _validate_schema(actions):
                return _enrich_with_confidence(actions, chunk_segments)
        except (json.JSONDecodeError, ValueError):
            pass
        except Exception as e:
            # API 오류(쿼터 초과, 네트워크 등) → 재시도 없이 즉시 실패 처리
            print(f"[WARN] LLM API 오류 (attempt {attempt+1}): {type(e).__name__}: {str(e)[:80]}")
            break

    # 3회 모두 실패 시 confidence 0.0으로 저장 (PRD 5.5)
    print("[WARN] LLM 추출 3회 실패. confidence 0.0으로 저장.")
    return [{
        "action": "추출 실패",
        "assignee": None,
        "deadline": None,
        "confidence": 0.0,
        "source_utterance": None,
    }]


# ── 공개 함수 ────────────────────────────────────────────────────────────────

def extract_actions(segments: list, meeting_id: str, meeting_date: str) -> list:
    """정제된 발화 목록에서 액션아이템을 추출하여 반환.

    meeting_date(YYYY-MM-DD)를 LLM에 전달해 deadline을 실제 날짜로 추론하도록 함.
    반환 형식: "2026-06-02 오전 (내일 오전)" 등 날짜 + 원문 표현.
    """
    chunks = _group_by_chunk(segments)

    all_actions = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"[INFO] 청크 {i}/{len(chunks)} LLM 호출 중...")
        actions = _call_llm_with_retry(chunk, meeting_id, meeting_date, max_retries=3)
        all_actions.extend(actions)
        # 무료 티어 RPM 한도(5회/분) 초과 방지 — 청크 사이 13초 대기
        if i < len(chunks):
            time.sleep(13)

    # PRD 4.3: action_id = "{meeting_id}_action_{idx+1:03d}"
    # meeting_id도 각 항목에 주입 (loader.py INSERT에서 필요)
    result = []
    for idx, action in enumerate(all_actions):
        result.append({
            "action_id": f"{meeting_id}_action_{str(idx + 1).zfill(3)}",
            "meeting_id": meeting_id,
            **action,
        })

    print(f"[OK] 액션아이템 총 {len(result)}건 추출 완료")
    return result
