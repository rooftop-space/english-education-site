# English Education Site 작업 보고서 (Offline Dictionary MVP)

## 0) 작업 목표
PRD 기준으로 로컬 sqlite 기반 오프라인 사전+예문 데이터 인프라 MVP를 구축.

## 1) 구현 결과 요약
완료한 필수 작업:
1. 디렉토리 구성: `data/raw`, `data/processed`, `etl`, `sql`
2. sqlite 스키마 작성: `sql/schema.sql`
   - `words`, `senses`, `examples`, `sense_examples`, `word_forms`
   - 모든 핵심 테이블에 `source`, `license`, `source_ref` 반영
   - 인덱스 + 예문 FTS5(`examples_fts`) 포함
3. ingest 스크립트 작성
   - `etl/ingest_oewn.py` (OEWN/WordNet 형태 JSON/JSONL 처리)
   - `etl/ingest_tatoeba.py` (Tatoeba TSV 처리)
4. 샘플 데이터로 E2E 적재 구성
   - `data/raw/sample_oewn.jsonl`
   - `data/raw/sample_tatoeba.tsv`
5. 최소 조회 모듈 추가
   - `etl/query_demo.py` (lemma 기반 뜻/예문 조회)
6. 라이선스/출처 문서 추가
   - `DATA_LICENSES.md`
7. 실행 가이드 + 검증 로그 문서화 (본 문서)

## 2) 파일 구조 (추가/변경)
- `sql/schema.sql`
- `etl/ingest_oewn.py`
- `etl/ingest_tatoeba.py`
- `etl/query_demo.py`
- `data/raw/sample_oewn.jsonl`
- `data/raw/sample_tatoeba.tsv`
- `DATA_LICENSES.md`
- `REPORT.md` (갱신)

## 3) 실행 가이드
```bash
cd /Users/rooftop/.openclaw/workspace/english-education-site

# 1) DB 생성 + 스키마 적용
sqlite3 data/processed/dictionary.db < sql/schema.sql

# 2) OEWN 샘플 적재
python3 etl/ingest_oewn.py \
  --db data/processed/dictionary.db \
  --input data/raw/sample_oewn.jsonl

# 3) Tatoeba 샘플 적재
python3 etl/ingest_tatoeba.py \
  --db data/processed/dictionary.db \
  --input data/raw/sample_tatoeba.tsv

# 4) 조회 데모
python3 etl/query_demo.py --db data/processed/dictionary.db --lemma run
python3 etl/query_demo.py --db data/processed/dictionary.db --lemma book
```

## 4) 실데이터 투입 방법
대용량 다운로드는 이번 작업에서 생략(샘플 우선)했으며, 실데이터 투입 경로/방법은 아래와 같음.

- OEWN 원본 위치(권장): `data/raw/oewn/`
  - 현재 ingest 지원 형식: JSONL(권장), JSON(list 또는 `{"entries": [...]}`)
- Tatoeba 원본 위치(권장): `data/raw/tatoeba/`
  - 현재 ingest 지원 형식: TSV (`id, lang, sentence` 필수)

예시:
```bash
python3 etl/ingest_oewn.py --db data/processed/dictionary.db --input data/raw/oewn/oewn.jsonl
python3 etl/ingest_tatoeba.py --db data/processed/dictionary.db --input data/raw/tatoeba/sentences.tsv
```

## 5) 검증 명령 및 결과
실행 명령:
```bash
rm -f data/processed/dictionary.db
sqlite3 data/processed/dictionary.db < sql/schema.sql
python3 etl/ingest_oewn.py --db data/processed/dictionary.db --input data/raw/sample_oewn.jsonl
python3 etl/ingest_tatoeba.py --db data/processed/dictionary.db --input data/raw/sample_tatoeba.tsv
python3 etl/query_demo.py --db data/processed/dictionary.db --lemma run
python3 etl/query_demo.py --db data/processed/dictionary.db --lemma book
sqlite3 data/processed/dictionary.db "select 'words',count(*) from words union all select 'senses',count(*) from senses union all select 'examples',count(*) from examples union all select 'sense_examples',count(*) from sense_examples union all select 'word_forms',count(*) from word_forms;"
```

실행 결과:
```text
[OEWN ingest] words processed=2, senses inserted=3, forms inserted=4
[Tatoeba ingest] examples processed=3, sense links inserted=5
WORD: run (verb) level=B1
  - Sense#1: move fast by using one's feet
  - Sense#2: operate or function
EXAMPLES:
  • I run every morning.
  • This machine runs on battery power.
WORD: book (noun) level=A1
  - Sense#3: a written work or composition
EXAMPLES:
  • I borrowed a book from the library.
words|2
senses|3
examples|3
sense_examples|5
word_forms|4
```

## 6) 300MB MVP 데이터 전략
초기 목표를 "약 300MB 내외"로 두고, 대용량 전체 적재 대신 **증분 배치**로 확장하는 방식을 채택.

핵심 전략:
1. **영어 데이터만 적재**
   - `--allow_lang en` / `--allow_lang en,eng` 필터로 비영어 제외
2. **예문 길이/품질 필터 적용**
   - `--min_tokens`, `--max_tokens`로 너무 짧거나 긴 문장 제외
3. **상위 빈도 단어 중심 컷오프**
   - 단어 ingest 시 `--max_rows`로 1차 컷오프
   - 예문 ingest 시 `--top_word_cutoff`로 상위 빈도 lemma에 매핑 가능한 예문 우선 적재
4. **증분 적재 가능 구조**
   - 모든 적재가 UPSERT/IGNORE 기반이라 같은 명령을 반복 실행해도 안전
   - `*_MAX_ROWS` 값을 단계적으로 늘려 DB 용량을 300MB 근처로 맞춤

추가된 실행 스크립트:
- `etl/run_mvp_300mb.sh`

실행 예시(실데이터 투입 시):
```bash
cd /Users/rooftop/.openclaw/workspace/english-education-site

# 1차 배치(초기 용량 목표)
DB_PATH=data/processed/dictionary.db \
OEWN_INPUT=data/raw/oewn/oewn.jsonl \
TATOEBA_INPUT=data/raw/tatoeba/sentences.tsv \
OEWN_MAX_ROWS=120000 \
TATOEBA_MAX_ROWS=400000 \
TATOEBA_MIN_TOKENS=4 \
TATOEBA_MAX_TOKENS=18 \
TOP_WORD_CUTOFF=120000 \
./etl/run_mvp_300mb.sh

# 2차 증분(필요시 컷오프 상향)
OEWN_MAX_ROWS=180000 TATOEBA_MAX_ROWS=650000 TOP_WORD_CUTOFF=180000 ./etl/run_mvp_300mb.sh
```

## 7) 1차 배치 실행 결과(현재 환경)
현재 저장소에는 샘플 데이터만 존재하므로, 동일 전략 옵션을 적용해 1차 적재를 실행.

실행 명령:
```bash
rm -f data/processed/dictionary.db
./etl/run_mvp_300mb.sh
```

결과:
- words: 2
- senses: 3
- examples: 3
- sense_examples: 5
- word_forms: 4
- DB 파일: `data/processed/dictionary.db`
- DB 크기: `86,016 bytes` (`0.08 MB`)

## 8) 호환성/영향
- 기존 프론트 앱(`index.html`, `styles.css`, `app.js`) 미수정
- 데이터 파이프라인 파일만 변경/추가되어 기존 앱 동작 영향 없음

## 9) 실데이터 증분 구축 로그 (2026-02-21)
(기존 내용 생략)

---

## 10) 요청사항 기반 품질 업그레이드 & 배포 (2026-02-21)

### 10-1. 품질 업그레이드 항목
대상: `data/processed/dictionary.db` 의 `level_recommendations` (총 1,200행)

신규 스크립트:
- `etl/upgrade_level_recommendations.py`

개선 로직:
1. meaning 정규화
   - 공백 정리, 말미 구두점 제거
   - `to + 동사` 형태의 불필요 접두 제거
   - `meaning_1 == meaning_2` 중복 시 `meaning_2` 제거
2. examples_json 품질 개선
   - 예문 공백/구두점 정리 (`..` → `.` 등)
   - 길이 기준 필터(8~180자)
   - 영문 포함 여부 검증
   - 대소문자 normalize 및 문장부호 보정
   - 동일 예문(case-insensitive) 중복 제거
3. 한국어 의미(ko) 보강 가능한 범위 반영
   - `meaning_translations_ko` 캐시 존재 시 `meaning_1_ko`, `meaning_2_ko` 자동 보강

### 10-2. 안전 절차 수행 기록 (백업 → 변환(dry-run) → 검증 → 반영)
실행 순서:
```bash
# 1) dry-run + 자동 백업
python3 etl/upgrade_level_recommendations.py --db data/processed/dictionary.db

# 2) apply + 자동 백업
python3 etl/upgrade_level_recommendations.py --db data/processed/dictionary.db --apply

# 3) idempotency 검증(dry-run 0건 확인)
python3 etl/upgrade_level_recommendations.py --db data/processed/dictionary.db --no-backup
```

결과 요약:
- 백업 생성:
  - `data/processed/backups/dictionary.backup.20260221_115745.db`
  - `data/processed/backups/dictionary.backup.20260221_115747.db`
- 변환 스캔: 1,200행
- 반영 변경: 892행(+ 후속 정규화 6행)
- 최종 idempotency: dry-run 변경 0행
- 레벨별 건수 유지: A1~C2 각 200행
- 빈 examples_json: 0행

### 10-3. 업데이트 시각 표시 구현 위치
요구 형식: `업데이트: YYYY-MM-DD HH:mm:ss`

구현 파일:
- `index.html`
  - `<body>` 최상단에 `#update-timestamp` 추가
- `styles.css`
  - `#update-timestamp`를 `position: fixed; top: 0; ...`로 항상 보이게 적용
  - 매우 작은 글씨(`font-size: 10px`)
- `app.js`
  - `const SITE_UPDATED_AT = "2026-02-21 11:57:51";`
  - `renderUpdateTimestamp()`에서 `업데이트: ...` 렌더

표시 예시:
- `업데이트: 2026-02-21 11:57:51`

### 10-4. 검증 결과 (기존 기능 영향)
실행:
```bash
node --check app.js
python3 etl/upgrade_level_recommendations.py --db data/processed/dictionary.db --no-backup
```

결과:
- JS 문법 검사 통과
- 품질 업그레이드 스크립트 dry-run 결과 변경 0행(재실행 안전)
- 레코드 수/레벨 분포 유지로 기존 추천 구조 훼손 없음

### 10-5. 샘플 개선 결과(전/후 요약)
샘플 파일: `logs/quality_upgrade_samples.json`

예시 1) `portuguese`
- 전: `Portuguese words sound squished..`
- 후: `Portuguese words sound squished.`

예시 2) `eternity`
- 전: `Eternity exists. It exists here..`
- 후: `Eternity exists. It exists here.`

### 10-6. 배포 결과
- GitHub 저장소: `https://github.com/rooftop-space/english-education-site`
- GitHub Pages URL(설정 관례 기준): `https://rooftop-space.github.io/english-education-site/`
- Pages 반영 확인: 커밋 푸시 후 URL 접속으로 확인(최대 수 분 지연 가능)
