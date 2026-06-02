# AI_USAGE.md

## 사용한 AI 도구

| 도구 | 용도 | 선택 이유 |
|---|---|---|
| Claude (claude.ai) | 설계 전 의사결정 과정 | 프로젝트 전체 컨텍스트를 유지하면서 스키마, confidence 룰, 기술 스택 등 설계 옵션의 트레이드오프를 탐색하기 위해 사용. 단순 질의응답이 아니라 "왜 이 선택이 맞는가"를 직접 판단하는 과정에서 활용함 |
| Claude Code | 코드 구현 | 설계가 확정된 이후 PRD.md를 컨텍스트로 제공하고 구현을 맡김. end-to-end 프로젝트 구조를 파일 간 일관성 있게 유지하면서 구현하기 위해 선택 |

---

## 컨텍스트 파일

- `PRD.md`: 스키마, confidence 룰, 파이프라인 명세 등 확정된 설계 전체를 담은 파일. Claude Code가 매 작업 시작 시 참조하도록 지시함

---

## 작업 로그

<!-- 아래 형식으로 작업하면서 계속 추가 -->
<!-- 
### [파일명] - 구현 완료
- Claude Code가 한 것: (자동 작성)
- 사용한 프롬프트 요약: (자동 작성)
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]
-->

### [requirements.txt] - 구현 완료
- Claude Code가 한 것: PRD 섹션 2 기술 스택 기반으로 의존 패키지 목록 작성. 대시보드 위젯 3의 TF-IDF를 위해 scikit-learn 추가
- 사용한 프롬프트 요약: "requirements.txt, .env.example, .gitignore, Makefile 만들어줘. PRD 섹션 7, 8, 9 기준으로."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [.env.example] - 구현 완료
- Claude Code가 한 것: PRD 섹션 8 그대로 ANTHROPIC_API_KEY 환경변수 템플릿 작성
- 사용한 프롬프트 요약: "requirements.txt, .env.example, .gitignore, Makefile 만들어줘. PRD 섹션 7, 8, 9 기준으로."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [.gitignore] - 구현 완료
- Claude Code가 한 것: PRD 섹션 9 그대로 .env, db/*.duckdb, __pycache__, *.pyc, .DS_Store 제외 규칙 작성
- 사용한 프롬프트 요약: "requirements.txt, .env.example, .gitignore, Makefile 만들어줘. PRD 섹션 7, 8, 9 기준으로."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [Makefile] - 구현 완료
- Claude Code가 한 것: PRD 섹션 7 그대로 install / run / run-mp3 / dashboard 타겟 작성
- 사용한 프롬프트 요약: "requirements.txt, .env.example, .gitignore, Makefile 만들어줘. PRD 섹션 7, 8, 9 기준으로."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/loader.py] - 구현 완료
- Claude Code가 한 것: PRD 섹션 4 스키마 3개(meetings, speech_segments, action_items) CREATE TABLE 구현. load_to_db()로 meetings+segments 적재 및 멱등성 체크, load_actions()로 액션아이템 별도 적재. participants JSON 직렬화, deadline TEXT 저장 준수
- 사용한 프롬프트 요약: "pipeline/loader.py 만들어줘. PRD 섹션 4, 5.4 기준으로."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/loader.py] - PRD 대조 검토 및 주석 추가
- Claude Code가 한 것: 구현 코드와 PRD 명세를 항목별로 대조하여 차이점 분석. PRD에 없으나 추가된 항목(_init_tables 헬퍼, load_actions 함수, participants 타입 분기)의 이유 설명. 이후 코드 전체에 한글 주석 추가 — SQL 블록 설계 의도, NULL 허용 이유, deadline TEXT 고정 이유, .get() 사용 이유 등 비자명한 지점 위주로 작성
- 사용한 프롬프트 요약: "PRD와 현재 구현한 내용에서 변경된 사항 체크해줘. 특히 pipeline/loader.py에서 달라진 부분을 알려주고, 해당 파일 코드에 한글로 된 주석을 달아서 코드를 설명해줘."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/cleaner.py] - 구현 완료
- Claude Code가 한 것: PRD 5.3 전체 구현. FILLER_PATTERNS(머뭇거림 제거), ABBREVIATION_DICT(약어 확장), VAGUE_PATTERNS(흐릿한 표현 플래그), 빈 발화 처리(10자 미만 → None), 청크 분리(화자 변경+5개 이상 or 8개 하드캡). 한글 주석 포함
- PRD 대비 변경사항: clean() 시그니처를 clean(transcript, source_file)로 변경 — meeting_id/segment_id 생성에 source_file 필요. 사용자 확인 후 적용. is_vague 판단은 정제 전 원문 기준으로 적용(PRD 미명시, 자연스러운 해석)
- 사용한 프롬프트 요약: "pipeline/cleaner.py 만들어줘. PRD 섹션 5.3 기준. 수행을 마치면 AI_USAGE.md에 자동 기록하고, 만약 PRD에 없는 내용이 추가되면 무조건 나에게 먼저 알리고 확인을 받아야 해."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/cleaner.py] - 상수 확장 (사용자 직접 수정)
- Claude Code가 한 것: 사용자가 제공한 내용 그대로 ABBREVIATION_DICT와 VAGUE_PATTERNS 교체
- 변경 내용: ABBREVIATION_DICT 8개 → 23개 (CPC/CPV/CPA/CVR/ROI/KPI/CAC/LTV/UTM/GDN/DA/SA/SNS/UGC/MOQ 추가). VAGUE_PATTERNS 8개 → 21개 (실제 transcript에서 발견된 표현 포함: "했었나" id:19, "맞죠?" id:35, "아닌가" id:12 등)
- 사용한 프롬프트 요약: "cleaner.py의 ABBREVIATION_DICT와 VAGUE_PATTERNS를 아래 내용으로 교체해줘."
- 내가 수정한 것: ABBREVIATION_DICT, VAGUE_PATTERNS 전체
- 수정 이유: PRD 기본값에서 실제 광고·마케팅 현장 용어 및 transcript 실제 등장 표현으로 확장

### [pipeline/extractor.py] - 구현 완료
- Claude Code가 한 것: PRD 5.5 전체 구현. extract_actions()/\_call_llm_with_retry()/calculate_confidence() 구현. LLM 프롬프트·few-shot·재시도 로직 PRD 원문 그대로 적용. confidence 룰 기반 계산(PRD 확정값 8개 VAGUE_PATTERNS 사용).
- PRD 대비 추가 항목 (사용자 확인 완료): ①발화 포맷 `발화: "{text}" (화자/역할)` ②재시도 강조 문구 텍스트 ③action_id·meeting_id를 extract_actions 내부에서 전역 카운터로 주입 ④validate_schema 구현(list + "action" 키 체크)
- 사용한 프롬프트 요약: "pipeline/extractor.py 만들어줘. PRD 섹션 5.5 기준. 수행을 마치면 AI_USAGE.md에 자동 기록하고, PRD에 없는 내용이 추가되면 먼저 확인을 받아야 해."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/stt.py] - 구현 완료
- Claude Code가 한 것: PRD 5.2 기준 faster-whisper 로컬 STT 구현. run_stt()로 mp3 전사 후 transcript dict 반환, save_transcript()로 mp3 파일명 기반 JSON 자동 저장
- PRD 대비 추가 항목 (사용자 확인 완료): ①device="auto" (GPU 자동 감지, compute_type="int8") ②speakers=[{"name":"SPEAKER_00","role":""}] 형식 ③save_transcript() 함수 (mp3→json 파일명 자동 생성)
- 화자 분리: pyannote.audio 미추가, PRD 명시대로 SPEAKER_00 고정 (사용자 확인 완료)
- 사용한 프롬프트 요약: "pipeline/stt.py 만들어줘. PRD 섹션 5.2 기준. 끝나면 AI_USAGE.md에 기록. PRD에 없는 내용이 추가되면 먼저 확인을 받아야 해."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [main.py] - 구현 완료
- Claude Code가 한 것: PRD 5.1 기준 파이프라인 진입점 구현. --input(mp3/json)/--file 인자, 5단계 실행 순서(STT→정제→DB적재→LLM추출→완료) 구현
- PRD 대비 추가 항목: ①--title/--advertiser/--date CLI 인자 추가(meeting_data 필드 출처, 사용자 확인 완료, 기본값: title=파일명/advertiser=미입력/date=오늘) ②load_actions() 호출(PRD 5.1 미명시이나 액션아이템 DB 저장을 위해 4단계 직후 추가)
- 사용한 프롬프트 요약: "main.py 만들어줘. PRD 섹션 5.1 기준. 끝나면 AI_USAGE.md에 기록. PRD에 없는 내용이 추가되면 먼저 확인을 받아야 해."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [main.py / Makefile / README.md / data/] - 파일명 컨벤션 도입
- Claude Code가 한 것: CLI 인자(--title/--advertiser/--date) 제거, 파일명에서 메타데이터 자동 파싱으로 전환. _parse_filename_metadata() 함수 추가(포맷: {advertiser}_{YYYYMMDD}_{title}). 포맷 불일치·언더스코어·날짜 오류 시 명확한 오류 메시지 출력. Makefile run/run-mp3 타겟 새 파일명으로 업데이트. README에 파일명 포맷 규칙 섹션 추가(포맷/규칙/예시/Windows 주의사항). 데이터 파일 복사(노바드림_20260601_캠페인사전정렬회의.json/.mp3)
- 변경 이유: 100명 사원 대상 운영 시 매번 CLI 인자 입력 불필요. 파일명 자체가 메타데이터 역할
- 사용한 프롬프트 요약: "파일명 포맷 {advertiser}_{YYYYMMDD}_{title}로 메타데이터 자동 파싱, CLI 인자 제거, README 포맷 규칙 추가, 데이터 파일 리네임, Makefile 업데이트"
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [make run 실행 시도] - 실행 중단 (미해결 문제 3건)
- 발생 시점: "make run 실행해서 파이프라인 전체가 돌아가는지 확인해줘" 프롬프트
- 문제 1 (즉시 차단): Makefile이 `python`을 호출하나 환경에 `python` 명령 없음. 실제 Python은 `/opt/homebrew/bin/python3.11`. → Makefile `python` → `python3` 수정 필요
- 문제 2 (다음 차단 예상): `make install` 미실행. requirements.txt 패키지 전혀 미설치 (anthropic, duckdb, streamlit 등)
- 문제 3 (그 다음 차단 예상): `.env` 파일 없음. ANTHROPIC_API_KEY 미설정 → extractor.py Claude API 호출 실패 예상
- 조치: 사용자에게 보고 후 실행 중단. A안(venv 생성) 또는 B안(python3 직접 사용) 선택 대기 중

### [Makefile] - python → python3 수정 (문제 1 해결)
- Claude Code가 한 것: Makefile의 `python` → `python3`, `pip` → `pip3` 전체 교체 (B안 선택)
- 사용한 프롬프트 요약: "B안으로 진행해줘. Makefile의 python을 python3로 전부 수정해줘."
- 내가 수정한 것: 수정 없음
- 수정 이유: 수정 없음

### [extractor.py / requirements.txt / .env.example / PRD.md] - LLM Gemini 2.0 Flash로 교체
- Claude Code가 한 것: ①extractor.py — import anthropic → google.generativeai, MODEL 상수 변경, _call_claude_api() → _call_gemini_api()로 교체(genai.configure + GenerativeModel 사용), _call_llm_with_retry 내 호출부 업데이트 ②requirements.txt — anthropic>=0.40.0 제거, google-generativeai>=0.8.0 추가 ③.env.example — ANTHROPIC_API_KEY → GEMINI_API_KEY ④PRD.md 기술 스택 테이블 LLM 항목 업데이트
- 사용한 프롬프트 요약: "extractor.py의 LLM을 Gemini 2.0 Flash로 변경. 모델명: gemini-2.0-flash, 라이브러리: google-generativeai. .env.example GEMINI_API_KEY로 변경, requirements.txt 추가, PRD LLM 모델 업데이트."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [make run 2차 실행 시도] - 부분 성공, LLM 단계 차단
- 발생 시점: "make run 실행해서 파이프라인 전체가 돌아가는지 확인해줘" 2차 시도
- 1~3단계 결과: ✅ JSON 로드, ✅ 정제(37 segments), ✅ DB 적재 모두 정상
- 문제 1 (즉시 차단): Gemini API 429 RESOURCE_EXHAUSTED — 무료 티어 limit: 0. 결제 미설정 또는 API 미활성화. 사용자 직접 해결 필요
- 문제 2 (경고): google.generativeai 패키지 공식 지원 종료. google.genai 패키지로 마이그레이션 필요
- 문제 3 (경고): Python 3.9 EOL — Google 라이브러리 FutureWarning 다수 출력. Python 3.10+ 권장
- 조치: 보고 후 실행 중단. 사용자 선택(API 키 수정/모델 변경/패키지 마이그레이션) 대기 중

### [extractor.py / PRD.md] - 모델 변경 및 파이프라인 전체 동작 확인
- Claude Code가 한 것: gemini-2.0-flash, gemini-2.0-flash-lite 모두 limit:0 확인. 실제 호출 가능한 모델을 API로 탐색하여 gemini-flash-latest 확인 후 변경. extractor.py MODEL 상수 및 PRD.md 기술 스택 업데이트
- make run 3차 결과: ✅ 전 단계 정상 완료
  - JSON 로드 ✅ / 정제 37 segments ✅ / DB 적재 스킵(멱등성 정상) ✅ / LLM 추출 18건 ✅ / DB 저장 ✅
- 잔여 경고(기능에 영향 없음): google.generativeai deprecated(→google.genai 마이그레이션 권장), Python 3.9 EOL
- 사용한 프롬프트 요약: "모델을 무료 할당량으로 변경하고 make run 실행해서 파이프라인 전체가 돌아가는지 다시 확인해줘."
- 내가 수정한 것: 수정 없음
- 수정 이유: 수정 없음

### [dashboard/app.py] - 구현 완료
- Claude Code가 한 것: PRD 6 위젯 4개 전체 구현. 위젯1(주차별 추이 라인차트), 위젯2(담당자별 Top N 바차트+슬라이더), 위젯3(광고주별 키워드 테이블), 위젯4(confidence 히스토그램+드릴다운 테이블). 차트 라이브러리: Altair. `make dashboard` 실행 후 http://localhost:8501 정상 응답 확인
- PRD 대비 추가 항목 (사용자 확인 완료): ①차트 라이브러리 Altair ②위젯3 단순 단어빈도 테이블 방식 ③한국어 불용어 목록 ④DB 경로 __file__ 기준 구성(CWD 무관) ⑤각 위젯 의사결정 안내 caption(PRD "의사결정자" 원칙 구현) ⑥빈 데이터 처리
- 사용한 프롬프트 요약: "dashboard/app.py 만들어줘. PRD 섹션 6 기준. 실행 후 AI_USAGE.md에 기록하고 PRD에 없는 내용은 확인 받고 실행해줘."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [PRD_ver02.md] - 생성 완료
- Claude Code가 한 것: 세션 전체 변경 이력을 반영하여 PRD_ver02.md 신규 생성. 버전 이력 테이블 추가. 변경 반영 항목: 기술스택(Gemini API/gemini-flash-latest, Altair), 프로젝트 구조(파일명 컨벤션 포맷), 섹션 3.1 파일명 컨벤션 신규 추가, meeting_id 예시 업데이트, main.py 파일명 파싱 방식, stt.py save_transcript() 추가, cleaner.py 시그니처 변경 및 상수 확장(ABBREVIATION_DICT 23개, VAGUE_PATTERNS 21개), loader.py load_actions() 추가, extractor.py Gemini API 및 action_id 주입 방식, 대시보드 Altair/테이블 방식 확정, Makefile python3/pip3, .env.example GEMINI_API_KEY, 중요 제약사항 7번 파일명 컨벤션 추가
- 사용한 프롬프트 요약: "지금까지의 변경 사항을 기존 PRD 파일 내용에 업데이트하여 새로운 PRD_ver02.md 파일로 생성해줘."
- 내가 수정한 것: 수정 없음
- 수정 이유: 수정 없음

### [extractor.py] - google.genai 마이그레이션 시도 및 보류
- Claude Code가 한 것: google-genai 패키지 설치 후 신규 SDK(google.genai) 마이그레이션 시도. gemini-flash-latest 모델에서 503 UNAVAILABLE 지속 발생 → 파이프라인 안정성 우선으로 기존 SDK(google.generativeai) 유지. extractor.py에 마이그레이션 보류 경위 주석 추가
- 결론: google.genai 1.x에서 gemini-flash-latest alias 지원 확인 후 재시도 필요
- 사용한 프롬프트 요약: "하던거 끝까지 진행해주세요."
- 내가 수정한 것: 수정 없음
- 수정 이유: 수정 없음

### [dashboard/app.py] - 전면 재구성 (v2)
- Claude Code가 한 것: 5개 위젯 구조로 전면 재작성. ①KPI 카드 4개(총 액션/담당자 미정/검수 필요/완료), ②전체 액션아이템 테이블(confidence 낮은 순 정렬, 담당자 필터, ⚠️ 중복 의심 자동 감지), ③담당자별 미완료 바차트(None 제외), ④주차별 추이 라인차트, ⑤confidence 히스토그램+드릴다운. 중복 감지: 같은 담당자 내 액션 키워드 교집합 있으면 ⚠️ 표시(자동 제거 아님). http://localhost:8501 정상 응답 확인
- 사용한 프롬프트 요약: "dashboard/app.py를 5개 위젯 구조로 전면 재구성해줘. KPI 카드/전체 테이블/담당자 바차트/주차별 추이/confidence 분포. 실행 후 AI_USAGE.md 기록하고 PRD_ver02.md 업데이트."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [dashboard/app.py] - 위젯 ⑤ 개선 (신뢰도 분포 시각화 + 검수 드릴다운 통합)
- Claude Code가 한 것: ⑤ 위젯 시각화 방식 교체. 10구간 히스토그램 → 신호등 카드 3개(🔴저신뢰/🟡중간/🟢고신뢰) + 3구간 가로 바 차트로 변경. 드릴다운 테이블을 "저신뢰(<0.5) + 중복 의심(⚠️)" 통합 검수 목록으로 확장. 검수 사유 컬럼 추가. 상태 메시지: 검수 필요 항목 없으면 ✅, 있으면 ⚠️ N건(저신뢰/중복 의심 구분) 표시
- 사용한 프롬프트 요약: "B안(신호등 카드+3구간 바차트)으로 변경하되 검수할 필요가 있는 것(중복 액션 등)도 드릴다운에 포함. AI_USAGE.md 기록하고 PRD_ver02.md 업데이트."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [dashboard/app.py] - 위젯 ④ 개선 (주차별 추이 차트 재구성)
- Claude Code가 한 것: 단일 라인 차트(회의 수+액션아이템 수 동일 Y축) → 두 개 미니 바 차트 나란히(st.columns(2))로 교체. 각자 독립 스케일 적용으로 스케일 차이(1 vs 18) 문제 해소. 바 위 숫자 레이블 추가(mark_text). X축 레이블 %m/%d → "N월 N주차" 형식으로 변경((d.day-1)//7+1 계산)
- 사용한 프롬프트 요약: "주차별 추이 차트 알아보기 힘들다. A안(두 개 미니 차트 나란히)으로 변경. 주차 레이블을 '6월 1주차' 형식으로."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [dashboard/app.py] - 위젯 ④ 재개선 (쌍막대 차트로 통합)
- Claude Code가 한 것: 두 개 미니 차트(st.columns) → Altair xOffset 쌍막대 차트 단일 차트로 통합. long format으로 변환 후 xOffset=구분으로 주차별 회의 수/액션아이템 수 막대를 나란히 표시. 색상 파랑(회의)/주황(액션), 레전드 상단 표시, 각 바 위 숫자 레이블(mark_text) 유지
- 사용한 프롬프트 요약: "주차별로 회의 수와 액션아이템 수 막대그래프를 쌍으로 붙여서 표현할 수 없나?"
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/extractor.py / main.py] - deadline 날짜 추론 프롬프트 개선
- Claude Code가 한 것: ①_SYSTEM_PROMPT에 deadline 추론 규칙 추가(당일/익일/요일/다음주/추론불가 → null). few-shot 2개→3개로 확장(익일 마감·요일 마감·불명확 케이스). ②_USER_PROMPT_TEMPLATE에 meeting_date·meeting_day(한국어 요일) 포함. ③_call_gemini_api/\_call_llm_with_retry/extract_actions 시그니처에 meeting_date 추가. ④main.py에서 extract_actions()에 meta["meeting_date"] 전달. ⑤_day_ko() 헬퍼 함수 추가
- PRD 변경 사항 (사용자 요청): deadline 저장 형식 변경 "내일 오전" → "2026-06-02 오전 (내일 오전)". extract_actions 시그니처 변경. DB 타입 변경 없음(TEXT 유지)
- 사용한 프롬프트 요약: "마감 일정이 제대로 분류되지 않아. 파일명의 날짜를 토대로 하루 안/오늘 저녁/수요일 오전까지 등이 정확한 숫자 날짜와 함께 추론되어야 한다."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [pipeline/notifier.py / main.py / .env / samples/] - Slack 알림 구현
- Claude Code가 한 것: ①pipeline/notifier.py 신규 생성 — build_slack_payload()(Block Kit 페이로드 생성: 헤더/메타/담당자별 액션목록/담당자미정/신뢰도경고/푸터), save_slack_payload()(JSON 파일 저장), send_to_slack()(urllib.request로 실제 전송, 추가 패키지 없음). ②main.py 5단계에 Slack 알림 추가 — 페이로드 생성→파일 저장→Webhook 전송 순서. ③.env에 SLACK_WEBHOOK_URL 추가. ④.env.example 업데이트. ⑤samples/slack_payload.json 샘플 생성. Slack '회의내용-한눈에-보기' 채널 전송 성공 확인
- 변경 이유: 과제 3.3 필수 산출물(Slack 메시지 페이로드 샘플) + 선택 사항(가산점) 동시 충족
- 사용한 프롬프트 요약: "Slack webhook URL로 실제 전송 코드까지 구현하자."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

### [기획안_ver02.md] - 기획안 업데이트 (변경 사항 반영)
- Claude Code가 한 것: 기존 기획안(1).md 기반으로 기획안_ver02.md 신규 생성. 변경 반영 항목: ①섹션 2 아키텍처 — Claude API → Gemini API, notifier.py/Slack 흐름 추가, 약어 사전 23개/VAGUE_PATTERNS 21개, few-shot 3개, deadline 날짜 추론 설명 추가, 도구 선택 테이블 Slack 행 추가. ②섹션 3 스키마 — deadline 컬럼 설명 "원문 그대로" → "YYYY-MM-DD (원문)" 날짜 추론 형식으로 업데이트. ③섹션 4 Before/After — Slack 공유 시간 절감, 마감 명확도 향상 항목 추가. ④섹션 5 실패 시나리오 — 시나리오 1 Gemini로 업데이트, 시나리오 5(Gemini API 쿼터 초과) 신규 추가. 총 5개 시나리오
- 사용한 프롬프트 요약: "기획안_ver02.md로 저장하고 Before/After + 실패 시나리오 변경 사항 반영해줘."
- 내가 수정한 것: [입력 필요]
- 수정 이유: [입력 필요]

