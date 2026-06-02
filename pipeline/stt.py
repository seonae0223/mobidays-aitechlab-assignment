import json
from pathlib import Path
from faster_whisper import WhisperModel

# PRD 5.2: 속도 우선 → base 모델 기본값
# device="auto": GPU 있으면 자동 사용, 없으면 CPU — 사용자 확인 완료
_DEFAULT_MODEL_SIZE = "base"
_DEFAULT_DEVICE = "auto"
_DEFAULT_COMPUTE_TYPE = "int8"


def run_stt(mp3_path: str) -> dict:
    """mp3 파일을 faster-whisper로 전사하여 transcript dict 반환.

    PRD 5.2 반환 형식:
    {
        "language": "ko",
        "speaker_count": N,
        "segment_count": N,
        "speakers": [{"name": "SPEAKER_00", "role": ""}],
        "segments": [{"id": 1, "line_no": 1, "speaker": "SPEAKER_00", "role": "", "text": "..."}]
    }

    화자 분리는 faster-whisper 자체 미지원 → 전체 SPEAKER_00 고정 (PRD 5.2 명시, 사용자 확인 완료)
    """
    print(f"[INFO] STT 시작: {mp3_path}")
    print(f"[INFO] 모델 로딩: {_DEFAULT_MODEL_SIZE} / device={_DEFAULT_DEVICE}")

    model = WhisperModel(
        _DEFAULT_MODEL_SIZE,
        device=_DEFAULT_DEVICE,
        compute_type=_DEFAULT_COMPUTE_TYPE,
    )

    # faster-whisper transcribe: word_timestamps=False로 속도 우선
    raw_segments, info = model.transcribe(
        mp3_path,
        language="ko",
        word_timestamps=False,
    )

    segments = []
    for i, seg in enumerate(raw_segments, start=1):
        segments.append({
            "id": i,
            "line_no": i,
            "speaker": "SPEAKER_00",   # 화자 분리 미지원 → 고정값 (PRD 5.2)
            "role": "",                 # STT 모드에서는 역할 정보 없음
            "text": seg.text.strip(),
        })

    transcript = {
        "language": info.language,
        "speaker_count": 1,            # 화자 분리 없으므로 1로 고정
        "segment_count": len(segments),
        "speakers": [{"name": "SPEAKER_00", "role": ""}],  # 사용자 확인 완료
        "segments": segments,
    }

    print(f"[OK] STT 완료 — segments: {len(segments)}, language: {info.language}")
    return transcript


def save_transcript(transcript: dict, mp3_path: str) -> str:
    """transcript dict를 JSON 파일로 저장.

    출력 파일명은 mp3 파일명 기반으로 자동 생성.
    예: ko_meeting_3speakers_4min_faster.mp3 → ko_meeting_3speakers_4min_faster.json
    (이전 대화에서 사용자 확인 완료)
    """
    output_path = Path(mp3_path).with_suffix(".json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    print(f"[OK] transcript 저장 완료: {output_path}")
    return str(output_path)
