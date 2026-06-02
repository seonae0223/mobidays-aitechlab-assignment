"""Slack Block Kit 메시지 페이로드 생성 및 전송 모듈.

회의 메타데이터와 액션아이템 목록을 받아
Slack Incoming Webhook으로 전송 가능한 JSON 페이로드를 생성하고,
실제 채널로 전송한다.
"""

import json
import urllib.request
import urllib.error
from pathlib import Path


def build_slack_payload(meeting_data: dict, actions: list) -> dict:
    """Slack Block Kit 페이로드 생성.

    Args:
        meeting_data: meetings 테이블의 한 row (dict)
        actions: action_items 목록 (list of dict)

    Returns:
        Slack Incoming Webhook 전송용 dict
    """
    title      = meeting_data.get("title", "")
    advertiser = meeting_data.get("advertiser", "")
    date       = meeting_data.get("meeting_date", "")
    total      = len(actions)
    unassigned = sum(1 for a in actions if not a.get("assignee"))
    low_conf   = sum(1 for a in actions if a.get("confidence", 1) < 0.5)

    blocks = []

    # ── 헤더 ──────────────────────────────────────────────────────────────────
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"📋 [{advertiser}] {title} — 액션아이템 요약"}
    })

    # ── 회의 메타 요약 ─────────────────────────────────────────────────────────
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*광고주*\n{advertiser}"},
            {"type": "mrkdwn", "text": f"*회의 일자*\n{date}"},
            {"type": "mrkdwn", "text": f"*총 액션아이템*\n{total}건"},
            {"type": "mrkdwn", "text": f"*담당자 미정*\n{unassigned}건"},
        ]
    })
    blocks.append({"type": "divider"})

    # ── 담당자별 액션아이템 ────────────────────────────────────────────────────
    # 담당자 있는 항목 → 담당자별로 묶기
    assigned = [a for a in actions if a.get("assignee")]
    by_person: dict = {}
    for a in assigned:
        by_person.setdefault(a["assignee"], []).append(a)

    for person, items in by_person.items():
        lines = []
        for a in items:
            deadline = a.get("deadline") or "마감 미정"
            conf     = a.get("confidence", 0)
            flag     = " ⚠️" if conf < 0.5 else ""
            lines.append(f"• {a['action']}  |  `{deadline}`{flag}")

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{person}* ({len(items)}건)\n" + "\n".join(lines)
            }
        })

    # ── 담당자 미정 항목 ───────────────────────────────────────────────────────
    unassigned_items = [a for a in actions if not a.get("assignee")]
    if unassigned_items:
        blocks.append({"type": "divider"})
        lines = [f"• {a['action']}  |  `{a.get('deadline') or '마감 미정'}`"
                 for a in unassigned_items]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚠️ 담당자 미정* ({len(unassigned_items)}건)\n" + "\n".join(lines)
            }
        })

    # ── 검수 필요 알림 ─────────────────────────────────────────────────────────
    if low_conf:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔴 *신뢰도 낮은 항목 {low_conf}건* — 대시보드에서 검수해주세요."
            }
        })

    # ── 푸터 ──────────────────────────────────────────────────────────────────
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": "자동 생성 by 회의록 AI 파이프라인  |  대시보드에서 상세 내용 확인 가능"
        }]
    })

    return {
        "text": f"[{advertiser}] {title} 액션아이템 {total}건",
        "blocks": blocks,
    }


def save_slack_payload(payload: dict, output_path: str = "samples/slack_payload.json") -> str:
    """페이로드를 JSON 파일로 저장."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] Slack 페이로드 저장: {output_path}")
    return output_path


def send_to_slack(payload: dict, webhook_url: str) -> bool:
    """Slack Incoming Webhook으로 페이로드를 전송한다.

    Args:
        payload:     build_slack_payload()가 반환한 dict
        webhook_url: Slack Incoming Webhook URL

    Returns:
        전송 성공 시 True, 실패 시 False
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            success = resp.status == 200
            if success:
                print("[OK] Slack '회의내용-한눈에-보기' 채널 전송 완료")
            return success
    except urllib.error.URLError as e:
        print(f"[WARN] Slack 전송 실패: {e}")
        return False
