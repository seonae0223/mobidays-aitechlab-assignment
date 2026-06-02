import re
from pathlib import Path

# ── 상수 정의 (PRD 5.3 확정값, 변경 금지) ────────────────────────────────────

# 머뭇거림 패턴: 음성 전사 시 나타나는 간투사·필러 표현
FILLER_PATTERNS = [
    r'\b어+\.{0,3}',
    r'\b음+\.{0,3}',
    r'\b아+\s',
    r'그게\s*,',
    r'아\s*그게',
    r'어\s*그건',
]

# 광고·마케팅 약어 → 풀어쓰기 사전
# 대시보드와 LLM이 용어를 정확히 인식하도록 약어 뒤에 원어를 병기
ABBREVIATION_DICT = {
    # PRD 기존
    "CTA": "클릭 유도 버튼(CTA)",
    "ROAS": "광고 수익률(ROAS)",
    "CPM": "1000회 노출당 비용(CPM)",
    "CTR": "클릭 전환율(CTR)",
    "A/B": "A/B 테스트",
    "GA": "구글 애널리틱스(GA)",
    "PoC": "개념 검증(PoC)",
    "R&R": "역할과 책임(R&R)",

    # 추가 제안
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

# 흐릿한 표현 목록: 이 표현이 포함된 발화는 is_vague=True
# extractor.py의 confidence 계산에서 -0.15 패널티 적용
VAGUE_PATTERNS = [
    # PRD 기존
    "잠정적으로", "일단 두고", "아마", "그건 이따가",
    "나중에", "한번 봐요", "어떻게 될지", "두고 봐요",

    # 추가 제안 (실제 transcript에서 발견된 표현 포함)
    "일단은", "우선은", "어떻게든",
    "되면 좋겠고", "해볼게요",        # 의지 불명확
    "그렇게 갔죠?", "맞죠?",          # transcript id:35 실제 등장
    "했었나",                          # transcript id:19 실제 등장
    "어 그건", "음 그게",
    "뭐 어떻게", "좀 봐야",
    "논의해봐야", "검토해볼게요",
    "될 것 같긴 한데", "같긴 한데",   # 확신 없는 표현
    "아닌가",                          # transcript id:12 실제 등장
]


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _remove_fillers(text: str) -> str:
    """FILLER_PATTERNS에 해당하는 간투사·머뭇거림 표현 제거."""
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, "", text)
    # 제거 후 생긴 연속 공백 정리
    return re.sub(r"\s+", " ", text).strip()


def _expand_abbreviations(text: str) -> str:
    """ABBREVIATION_DICT 기준으로 약어를 풀어쓰기로 교체."""
    for abbr, expanded in ABBREVIATION_DICT.items():
        text = text.replace(abbr, expanded)
    return text


def _is_vague(text: str) -> bool:
    """VAGUE_PATTERNS 중 하나라도 포함되면 True."""
    return any(pattern in text for pattern in VAGUE_PATTERNS)


def _assign_chunks(segments: list) -> list:
    """발화 목록에 chunk_index를 부여한다.

    규칙 (PRD 5.3):
    - 화자가 바뀌고 현재 청크 크기가 5 이상이면 새 청크 시작
    - 현재 청크 크기가 8에 도달하면 다음 발화에서 무조건 새 청크 시작 (하드 캡)
    """
    chunk_index = 1
    chunk_size = 0
    prev_speaker = None

    for seg in segments:
        speaker = seg["speaker"]

        if prev_speaker is not None:
            speaker_changed = speaker != prev_speaker
            if (speaker_changed and chunk_size >= 5) or chunk_size >= 8:
                chunk_index += 1
                chunk_size = 0

        seg["chunk_index"] = chunk_index
        chunk_size += 1
        prev_speaker = speaker

    return segments


# ── 공개 함수 ────────────────────────────────────────────────────────────────

def clean(transcript: dict, source_file: str) -> list:
    """transcript를 정제하여 발화 단위 목록을 반환.

    PRD 명시 시그니처: clean(transcript: dict) → list[dict]
    실제 시그니처: clean(transcript, source_file) — meeting_id 생성을 위해 source_file 추가
    (PRD 4.1의 meeting_id 생성 규칙 적용: Path(source_file).stem)

    처리 순서 (PRD 5.3):
    1. 머뭇거림 제거
    2. 약어 사전 적용
    3. 빈 발화 처리 (10자 미만 → cleaned_text = None)
    4. 흐릿한 표현 플래그 (is_vague)
    5. 청크 분리 (chunk_index 부여)
    """
    # PRD 4.1: 파일명에서 확장자 제거하여 meeting_id 생성
    meeting_id = Path(source_file).stem

    result = []
    for seg in transcript["segments"]:
        original_text = seg["text"]

        # 1. 머뭇거림 제거
        cleaned = _remove_fillers(original_text)

        # 2. 약어 사전 적용
        cleaned = _expand_abbreviations(cleaned)

        # 3. 빈 발화 처리: 정제 후 10자 미만이면 None
        cleaned_text = cleaned if len(cleaned) >= 10 else None

        # 4. 흐릿한 표현은 원문 기준으로 판단 (정제 전 텍스트 사용)
        is_vague = _is_vague(original_text)

        # PRD 4.2: segment_id = "{meeting_id}_{id:03d}"
        segment_id = f"{meeting_id}_{str(seg['id']).zfill(3)}"

        result.append({
            "segment_id": segment_id,
            "meeting_id": meeting_id,
            "speaker": seg["speaker"],
            "role": seg.get("role", ""),
            "original_text": original_text,
            "cleaned_text": cleaned_text,
            "chunk_index": None,  # 5단계 청크 분리 후 채워짐
            "is_vague": is_vague,
        })

    # 5. 청크 분리: chunk_index 부여
    result = _assign_chunks(result)

    return result
