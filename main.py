import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from pipeline.stt import run_stt, save_transcript
from pipeline.cleaner import clean
from pipeline.loader import load_to_db, load_actions
from pipeline.extractor import extract_actions
from pipeline.notifier import build_slack_payload, save_slack_payload, send_to_slack

# 파일명 포맷: {advertiser}_{YYYYMMDD}_{title}
# advertiser와 title에 언더스코어('_') 사용 금지
_FILENAME_PATTERN = re.compile(r'^([^_]+)_(\d{8})_([^_]+)$')


def _parse_filename_metadata(source_file: str) -> dict:
    """파일명에서 advertiser, meeting_date, title을 파싱한다.

    포맷: {advertiser}_{YYYYMMDD}_{title}.mp3/.json
    예시: 노바드림_20260601_캠페인사전정렬회의.json
    """
    stem = Path(source_file).stem
    match = _FILENAME_PATTERN.match(stem)

    if not match:
        raise SystemExit(
            f"\n[오류] 파일명 포맷 불일치: '{stem}'\n"
            f"  올바른 포맷 : {{advertiser}}_{{YYYYMMDD}}_{{title}}\n"
            f"  규칙        : advertiser와 title에 언더스코어('_') 사용 금지\n"
            f"  올바른 예시 : 노바드림_20260601_캠페인사전정렬회의.json\n"
        )

    advertiser, date_str, title = match.groups()

    try:
        meeting_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        raise SystemExit(
            f"\n[오류] 날짜 형식 불일치: '{date_str}'\n"
            f"  올바른 날짜 포맷: YYYYMMDD (예: 20260601)\n"
        )

    return {
        "advertiser": advertiser,
        "meeting_date": meeting_date,
        "title": title,
    }


def _parse_args():
    parser = argparse.ArgumentParser(description="회의록 자동 정리 및 액션아이템 추출 파이프라인")
    parser.add_argument(
        "--input", required=True, choices=["mp3", "json"],
        help="입력 방식: mp3 (STT 사용) 또는 json (transcript 직접 로드)",
    )
    parser.add_argument(
        "--file", required=True,
        help="입력 파일 경로. 파일명 포맷: {advertiser}_{YYYYMMDD}_{title}.mp3/.json",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    source_file = args.file

    # 파일명에서 메타데이터 파싱 (포맷 불일치 시 즉시 종료)
    meta = _parse_filename_metadata(source_file)
    meeting_id = Path(source_file).stem  # PRD 4.1: 파일명에서 확장자 제거

    # ── 1단계: 입력 방식에 따라 transcript 로드 ─────────────────────────────
    if args.input == "mp3":
        print(f"[INFO] 입력 방식: mp3 → STT 실행")
        transcript = run_stt(source_file)
        save_transcript(transcript, source_file)
    else:
        print(f"[INFO] 입력 방식: json → transcript 직접 로드")
        with open(source_file, encoding="utf-8") as f:
            transcript = json.load(f)

    # ── 2단계: cleaner.py 정제 ───────────────────────────────────────────────
    print("[INFO] 발화 정제 중...")
    segments = clean(transcript, source_file)
    print(f"[INFO] 정제 완료 — segments: {len(segments)}")

    # ── 3단계: loader.py DuckDB 적재 ────────────────────────────────────────
    participants = json.dumps(transcript.get("speakers", []), ensure_ascii=False)

    meeting_data = {
        "meeting_id": meeting_id,
        "title": meta["title"],
        "advertiser": meta["advertiser"],
        "meeting_date": meta["meeting_date"],
        "participants": participants,
        "source_file": source_file,
    }

    print("[INFO] 회의 데이터 DB 적재 중...")
    load_to_db(meeting_data, segments)

    # ── 4단계: extractor.py LLM 추출 ────────────────────────────────────────
    print("[INFO] 액션아이템 LLM 추출 중...")
    actions = extract_actions(segments, meeting_id, meta["meeting_date"])
    load_actions(actions)

    # ── 5단계: Slack 알림 전송 ───────────────────────────────────────────────
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    payload = build_slack_payload(meeting_data, actions)
    save_slack_payload(payload)               # samples/slack_payload.json 저장
    if slack_webhook:
        send_to_slack(payload, slack_webhook)
    else:
        print("[INFO] SLACK_WEBHOOK_URL 미설정 — 파일만 저장됨 (samples/slack_payload.json)")

    # ── 6단계: 완료 메시지 출력 ─────────────────────────────────────────────
    print()
    print("=" * 50)
    print(f"[완료] 파이프라인 실행 완료")
    print(f"  - 회의 ID   : {meeting_id}")
    print(f"  - 광고주    : {meta['advertiser']}")
    print(f"  - 회의 일자 : {meta['meeting_date']}")
    print(f"  - 발화 수   : {len(segments)}")
    print(f"  - 액션아이템: {len(actions)}건")
    print("=" * 50)


if __name__ == "__main__":
    main()
