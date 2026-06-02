import json
import duckdb

# ── 테이블 생성 SQL ──────────────────────────────────────────────────────────

# 회의 메타데이터 테이블: 회의 1건 = 행 1개
# participants는 JSON 문자열로 저장 (예: [{"name": "지훈", "role": "마케팅 팀장"}])
CREATE_MEETINGS_SQL = """
CREATE TABLE IF NOT EXISTS meetings (
    meeting_id    TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    advertiser    TEXT NOT NULL,
    meeting_date  DATE NOT NULL,
    participants  TEXT NOT NULL,
    source_file   TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT current_timestamp
)
"""

# 발화 단위 테이블: 회의 1건에 N개의 발화 행이 연결됨
# cleaned_text, chunk_index는 cleaner.py 처리 후 채워지므로 NULL 허용
CREATE_SPEECH_SEGMENTS_SQL = """
CREATE TABLE IF NOT EXISTS speech_segments (
    segment_id    TEXT PRIMARY KEY,
    meeting_id    TEXT NOT NULL REFERENCES meetings(meeting_id),
    speaker       TEXT NOT NULL,
    role          TEXT NOT NULL,
    original_text TEXT NOT NULL,
    cleaned_text  TEXT,
    chunk_index   INTEGER,
    created_at    TIMESTAMP DEFAULT current_timestamp
)
"""

# 액션아이템 테이블: extractor.py가 LLM으로 추출한 결과 저장
# deadline은 TEXT 타입 고정 — "내일 오전" 같은 자연어 표현 그대로 저장, DATE 파싱 금지
# confidence는 룰 기반으로 계산된 0.0~1.0 점수 (extractor.py의 calculate_confidence 참고)
CREATE_ACTION_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS action_items (
    action_id         TEXT PRIMARY KEY,
    meeting_id        TEXT NOT NULL REFERENCES meetings(meeting_id),
    action            TEXT NOT NULL,
    assignee          TEXT,
    deadline          TEXT,
    status            TEXT DEFAULT 'todo',
    confidence        FLOAT NOT NULL,
    source_utterance  TEXT,
    created_at        TIMESTAMP DEFAULT current_timestamp
)
"""

# ── INSERT SQL ───────────────────────────────────────────────────────────────

INSERT_MEETING_SQL = """
INSERT INTO meetings (meeting_id, title, advertiser, meeting_date, participants, source_file)
VALUES (?, ?, ?, ?, ?, ?)
"""

INSERT_SEGMENT_SQL = """
INSERT INTO speech_segments (segment_id, meeting_id, speaker, role, original_text, cleaned_text, chunk_index)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

INSERT_ACTION_SQL = """
INSERT INTO action_items (action_id, meeting_id, action, assignee, deadline, confidence, source_utterance)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _init_tables(conn: duckdb.DuckDBPyConnection) -> None:
    # 세 테이블을 모두 초기화. CREATE IF NOT EXISTS이므로 이미 존재해도 안전하게 실행됨
    conn.execute(CREATE_MEETINGS_SQL)
    conn.execute(CREATE_SPEECH_SEGMENTS_SQL)
    conn.execute(CREATE_ACTION_ITEMS_SQL)


# ── 공개 함수 ────────────────────────────────────────────────────────────────

def load_to_db(meeting_data: dict, segments: list, db_path: str = "db/meeting.duckdb") -> None:
    """meetings + speech_segments 적재. 동일 meeting_id가 이미 있으면 전체 스킵(멱등성)."""
    conn = duckdb.connect(db_path)
    _init_tables(conn)

    # 멱등성 체크: 동일 meeting_id가 이미 적재된 경우 중복 삽입 방지
    existing = conn.execute(
        "SELECT 1 FROM meetings WHERE meeting_id = ?",
        [meeting_data["meeting_id"]]
    ).fetchone()

    if existing:
        print(f"[SKIP] {meeting_data['meeting_id']} 이미 적재됨. 스킵합니다.")
        conn.close()
        return

    # participants가 dict/list로 전달된 경우 JSON 문자열로 변환
    # 이미 문자열이면 그대로 사용 (JSON 파일에서 직접 읽어온 경우)
    participants_json = (
        meeting_data["participants"]
        if isinstance(meeting_data["participants"], str)
        else json.dumps(meeting_data["participants"], ensure_ascii=False)
    )

    # 회의 메타데이터 1행 삽입
    conn.execute(INSERT_MEETING_SQL, [
        meeting_data["meeting_id"],
        meeting_data["title"],
        meeting_data["advertiser"],
        meeting_data["meeting_date"],
        participants_json,
        meeting_data["source_file"],
    ])

    # 발화 N행 삽입. cleaned_text/chunk_index는 cleaner.py 결과에 없을 수 있으므로 .get() 사용
    for seg in segments:
        conn.execute(INSERT_SEGMENT_SQL, [
            seg["segment_id"],
            seg["meeting_id"],
            seg["speaker"],
            seg["role"],
            seg["original_text"],
            seg.get("cleaned_text"),   # 정제 후 10자 미만이면 None
            seg.get("chunk_index"),    # 청크 분리 후 채워짐
        ])

    print(f"[OK] {meeting_data['meeting_id']} 적재 완료 (segments: {len(segments)})")
    conn.close()


def load_actions(actions: list, db_path: str = "db/meeting.duckdb") -> None:
    """extractor.py가 반환한 액션아이템 목록을 action_items 테이블에 적재.

    PRD 5.4에 별도 명시는 없으나, main.py 흐름(extractor 실행 후 DB 저장)에서
    반드시 필요하므로 load_to_db와 분리하여 구현.
    """
    if not actions:
        print("[SKIP] 저장할 액션아이템 없음.")
        return

    conn = duckdb.connect(db_path)
    _init_tables(conn)

    for action in actions:
        # assignee, deadline, source_utterance는 LLM이 null로 반환할 수 있으므로 .get() 사용
        conn.execute(INSERT_ACTION_SQL, [
            action["action_id"],
            action["meeting_id"],
            action["action"],
            action.get("assignee"),        # 담당자 불명확 시 None
            action.get("deadline"),        # TEXT 그대로 저장, DATE 변환 금지
            action["confidence"],          # 룰 기반 점수 (0.0~1.0)
            action.get("source_utterance"),
        ])

    print(f"[OK] 액션아이템 {len(actions)}건 적재 완료")
    conn.close()
