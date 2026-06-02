import os
import re

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "meeting.duckdb")

_STOPWORDS = {
    "및", "또는", "의", "을", "를", "이", "가", "은", "는", "에", "에서",
    "으로", "로", "와", "과", "한", "하는", "하기", "위한", "대한",
    "후", "전", "통해", "위해", "관련", "해당", "이후", "이전", "등",
    "대해", "따른", "위해서", "이를", "그", "저", "확인", "작업", "정리",
}


@st.cache_resource
def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)


def _keywords(text: str) -> set:
    text = re.sub(r"[^\w\s]", " ", str(text))
    return {w for w in text.split() if len(w) >= 2 and w not in _STOPWORDS}


def _flag_duplicates(df: pd.DataFrame) -> pd.Series:
    """같은 담당자 내에서 액션 키워드가 겹치는 항목을 True로 표시."""
    flagged = pd.Series(False, index=df.index)
    for assignee, group in df.groupby("assignee", dropna=True):
        idxs = group.index.tolist()
        if len(idxs) < 2:
            continue
        kw = {i: _keywords(df.loc[i, "action"]) for i in idxs}
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                if kw[ia] & kw[ib]:
                    flagged[ia] = True
                    flagged[ib] = True
    return flagged


# ── 페이지 설정 ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="회의록 액션아이템 대시보드", layout="wide")
st.title("회의록 액션아이템 대시보드")
st.caption("의사결정자가 회의 직후 무엇을 결정하고 누구에게 무엇을 요청할지 한눈에 파악합니다.")

try:
    conn = get_conn()
except Exception as e:
    st.error(f"DB 연결 실패: {e}\n\n`make run`을 먼저 실행하여 데이터를 적재하세요.")
    st.stop()

# ── 데이터 로드 ───────────────────────────────────────────────────────────────

df = conn.execute("""
    SELECT
        a.action_id,
        a.action,
        a.assignee,
        a.deadline,
        a.status,
        a.confidence,
        a.source_utterance,
        m.meeting_id,
        m.title,
        m.advertiser,
        m.meeting_date
    FROM action_items a
    JOIN meetings m ON a.meeting_id = m.meeting_id
""").df()

df_weekly = conn.execute("""
    SELECT
        DATE_TRUNC('week', meeting_date) AS week,
        COUNT(DISTINCT m.meeting_id)     AS meeting_count,
        COUNT(a.action_id)               AS action_count
    FROM meetings m
    LEFT JOIN action_items a ON m.meeting_id = a.meeting_id
    GROUP BY week
    ORDER BY week
""").df()
df_weekly["week"] = pd.to_datetime(df_weekly["week"])

if df.empty:
    st.warning("적재된 데이터가 없습니다. `make run`을 실행하세요.")
    st.stop()

# 중복 의심 플래그 (전체 기준)
df["_dup"] = _flag_duplicates(df)

st.divider()

# ── ① KPI 카드 ───────────────────────────────────────────────────────────────

st.subheader("① 현황 요약")

k1, k2, k3, k4 = st.columns(4)
k1.metric("총 액션아이템", len(df))
k2.metric("담당자 미정", int(df["assignee"].isna().sum()),
          help="assignee가 지정되지 않은 항목 — 담당자 배정 필요")
k3.metric("검수 필요 (신뢰도 < 0.5)", int((df["confidence"] < 0.5).sum()),
          help="LLM 추출 신뢰도 낮음 — 사람이 직접 확인 권장")
k4.metric("완료", int((df["status"] == "done").sum()),
          help="status = done 항목")

st.divider()

# ── ② 전체 액션아이템 테이블 ─────────────────────────────────────────────────

st.subheader("② 전체 액션아이템")
st.caption("담당자·마감·신뢰도를 한눈에 조감하고 즉시 후속 조치를 결정합니다. ⚠️는 중복 의심 항목입니다.")

# 담당자 필터
all_assignees = sorted(df["assignee"].dropna().unique().tolist())
selected_assignees = st.multiselect(
    "담당자 필터 (복수 선택 가능)",
    options=all_assignees,
    default=[],
    placeholder="선택 없으면 전체 표시",
)

if selected_assignees:
    view = df[df["assignee"].isin(selected_assignees)].copy()
else:
    view = df.copy()

# confidence 낮은 순 정렬
view = view.sort_values("confidence").reset_index(drop=True)

display = view[["_dup", "assignee", "action", "deadline", "confidence", "status"]].copy()
display["_dup"] = display["_dup"].map({True: "⚠️", False: ""})
display = display.rename(columns={
    "_dup": "",
    "assignee": "담당자",
    "action": "액션 내용",
    "deadline": "마감",
    "confidence": "신뢰도",
    "status": "상태",
})
display["담당자"] = display["담당자"].fillna("(미정)")
display["마감"] = display["마감"].fillna("(미정)")

st.dataframe(display, use_container_width=True, hide_index=True)

dup_cnt = int(view["_dup"].sum())
if dup_cnt:
    st.caption(f"⚠️ 중복 의심 {dup_cnt}건 — 같은 담당자의 액션에서 키워드가 겹칩니다. 병합 여부를 검토하세요.")

st.divider()

# ── ③ 담당자별 미완료 액션아이템 ─────────────────────────────────────────────

st.subheader("③ 담당자별 미완료 액션아이템")
st.caption("업무가 특정 담당자에게 쏠려 있다면 재분배 또는 우선순위 조정이 필요합니다.")

df_bar = (
    df[df["status"] == "todo"]
    .dropna(subset=["assignee"])
    .groupby("assignee", as_index=False)
    .size()
    .rename(columns={"size": "미완료 건수"})
    .sort_values("미완료 건수", ascending=False)
)

if df_bar.empty:
    st.success("모든 액션아이템이 완료되었습니다.")
else:
    chart3 = (
        alt.Chart(df_bar)
        .mark_bar()
        .encode(
            x=alt.X("미완료 건수:Q", title="미완료 건수"),
            y=alt.Y("assignee:N", sort="-x", title="담당자"),
            color=alt.Color("미완료 건수:Q",
                            scale=alt.Scale(scheme="orangered"), legend=None),
            tooltip=["assignee:N", "미완료 건수:Q"],
        )
        .properties(height=max(180, len(df_bar) * 45))
    )
    st.altair_chart(chart3, use_container_width=True)

st.divider()

# ── ④ 주차별 회의·액션아이템 발생 추이 ───────────────────────────────────────

st.subheader("④ 주차별 회의·액션아이템 발생 추이")
st.caption("회의 빈도와 액션아이템 발생량을 독립 스케일로 비교해 업무 부하 집중 시점을 파악합니다.")

if df_weekly.empty:
    st.info("데이터가 없습니다.")
else:
    df_weekly["week_str"] = df_weekly["week"].apply(
        lambda d: f"{d.month}월 {(d.day - 1) // 7 + 1}주차"
    )

    # 쌍막대 차트용 long format 변환
    df_melted = df_weekly.melt(
        id_vars=["week_str"],
        value_vars=["meeting_count", "action_count"],
        var_name="구분",
        value_name="건수",
    )
    df_melted["구분"] = df_melted["구분"].map(
        {"meeting_count": "회의 수", "action_count": "액션아이템 수"}
    )

    bars = (
        alt.Chart(df_melted)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("week_str:N", title="주차", sort=None),
            xOffset=alt.XOffset("구분:N"),
            y=alt.Y("건수:Q", title="건수", scale=alt.Scale(domainMin=0)),
            color=alt.Color(
                "구분:N",
                scale=alt.Scale(
                    domain=["회의 수", "액션아이템 수"],
                    range=["#4A90D9", "#E8825A"],
                ),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("week_str:N", title="주차"),
                alt.Tooltip("구분:N", title="구분"),
                alt.Tooltip("건수:Q", title="건수"),
            ],
        )
    )

    labels = (
        alt.Chart(df_melted)
        .mark_text(dy=-8, fontSize=12, fontWeight="bold")
        .encode(
            x=alt.X("week_str:N", sort=None),
            xOffset=alt.XOffset("구분:N"),
            y=alt.Y("건수:Q"),
            text=alt.Text("건수:Q"),
            color=alt.Color(
                "구분:N",
                scale=alt.Scale(
                    domain=["회의 수", "액션아이템 수"],
                    range=["#4A90D9", "#E8825A"],
                ),
            ),
        )
    )

    st.altair_chart((bars + labels).properties(height=260), use_container_width=True)

st.divider()

# ── ⑤ Confidence 분포 + 낮은 항목 드릴다운 ──────────────────────────────────

st.subheader("⑤ LLM 신뢰도 분포")
st.caption("신뢰도 낮은 항목을 먼저 검수하면 LLM 오추출로 인한 누락을 방지할 수 있습니다.")

# 3구간 분류
n_low  = int((df["confidence"] < 0.5).sum())
n_mid  = int(((df["confidence"] >= 0.5) & (df["confidence"] < 0.8)).sum())
n_high = int((df["confidence"] >= 0.8).sum())
total_conf = len(df)

# 신호등 카드 3개
c1, c2, c3 = st.columns(3)
c1.metric("🔴 저신뢰  (< 50%)",  f"{n_low}건",
          help="LLM 추출 신뢰도 낮음 — 사람이 직접 확인 필요")
c2.metric("🟡 중간 (50 ~ 80%)", f"{n_mid}건",
          help="담당자 또는 마감 중 하나가 불명확")
c3.metric("🟢 고신뢰  (≥ 80%)", f"{n_high}건",
          help="담당자·마감·근거 발화 모두 명확")

# 3구간 가로 바 차트
df_conf_band = pd.DataFrame({
    "구간":  ["🔴 저신뢰 (< 50%)", "🟡 중간 (50~80%)", "🟢 고신뢰 (≥ 80%)"],
    "건수":  [n_low, n_mid, n_high],
    "색상":  ["#e74c3c", "#f39c12", "#27ae60"],
    "순서":  [0, 1, 2],
})
df_conf_band["비율"] = (df_conf_band["건수"] / total_conf * 100).round(1).astype(str) + "%"

chart5 = (
    alt.Chart(df_conf_band)
    .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
    .encode(
        x=alt.X("건수:Q", title="건수", scale=alt.Scale(domain=[0, total_conf])),
        y=alt.Y("구간:N", sort=alt.SortField("순서"), title=None),
        color=alt.Color("색상:N", scale=None, legend=None),
        tooltip=["구간:N", "건수:Q", "비율:N"],
    )
    .properties(height=140)
)
st.altair_chart(chart5, use_container_width=True)

# 검수 필요 항목 수집: 저신뢰 OR 중복 의심
review_mask = (df["confidence"] < 0.5) | df["_dup"]
df_review = df[review_mask].copy()
df_review["검수 사유"] = ""
df_review.loc[df_review["confidence"] < 0.5, "검수 사유"] += "저신뢰"
df_review.loc[df_review["_dup"], "검수 사유"] = df_review.loc[df_review["_dup"], "검수 사유"].apply(
    lambda x: (x + " · " if x else "") + "⚠️ 중복 의심"
)

# 상태 메시지
if df_review.empty:
    st.success(f"✅ 검수 필요 항목 없음 — 전체 {total_conf}건 추출 품질 양호")
else:
    st.warning(f"⚠️ 검수 필요 {len(df_review)}건 (저신뢰: {n_low}건 · 중복 의심: {int(df['_dup'].sum())}건) — 아래 항목을 확인하세요.")

# 드릴다운 테이블
if not df_review.empty:
    review_display = df_review[
        ["검수 사유", "assignee", "action", "deadline", "confidence", "source_utterance"]
    ].sort_values("confidence").copy()
    review_display = review_display.rename(columns={
        "assignee": "담당자", "action": "액션 내용", "deadline": "마감",
        "confidence": "신뢰도", "source_utterance": "근거 발화",
    })
    review_display["담당자"] = review_display["담당자"].fillna("(미정)")
    review_display["마감"]   = review_display["마감"].fillna("(미정)")
    st.dataframe(review_display, use_container_width=True, hide_index=True)
