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

---

## 9) 실데이터 증분 구축 로그 (2026-02-21)
요청사항에 따라 실데이터 기준으로 `data/raw/real/` 경로를 정리하고, `etl/run_mvp_300mb.sh`로 1차→2차 증분 적재를 수행함.

### 9-1. 원본 수집/정리
- OEWN: `data/raw/real/oewn/x-englishwordnet-json/` (합법 미러: GitHub `x-englishwordnet/json`)
  - 사용 파일: `data/raw/real/oewn/oewn.json` (zip 해제본)
  - ingest용 변환본: `data/raw/real/oewn/oewn_2025_en.jsonl` (160,502 entries)
- Tatoeba: `data/raw/real/tatoeba/sentences.tar.bz2` (공식 exports)
  - ingest용 추출본: `data/raw/real/tatoeba/sentences_en.tsv` (2,014,479 rows, lang=en)

### 9-2. 1차 적재 (MVP 300MB 목표 배치)
실행:
```bash
rm -f data/processed/dictionary.db
DB_PATH=data/processed/dictionary.db \
OEWN_INPUT=data/raw/real/oewn/oewn_2025_en.jsonl \
TATOEBA_INPUT=data/raw/real/tatoeba/sentences_en.tsv \
OEWN_MAX_ROWS=120000 \
TATOEBA_MAX_ROWS=400000 \
TATOEBA_MIN_TOKENS=4 \
TATOEBA_MAX_TOKENS=18 \
TOP_WORD_CUTOFF=120000 \
./etl/run_mvp_300mb.sh
```

결과 (`logs/mvp_stage1.log`):
- words: 120,000
- senses: 165,861
- examples: 400,000
- sense_examples: 2,039,794
- word_forms: 0
- DB_SIZE_BYTES: 349,003,776
- DB_SIZE_MB: 332.84

### 9-3. 2차 증분 적재
실행:
```bash
DB_PATH=data/processed/dictionary.db \
OEWN_INPUT=data/raw/real/oewn/oewn_2025_en.jsonl \
TATOEBA_INPUT=data/raw/real/tatoeba/sentences_en.tsv \
OEWN_MAX_ROWS=150000 \
TATOEBA_MAX_ROWS=600000 \
TATOEBA_MIN_TOKENS=4 \
TATOEBA_MAX_TOKENS=18 \
TOP_WORD_CUTOFF=150000 \
./etl/run_mvp_300mb.sh
```

결과 (`logs/mvp_stage2.log`):
- words: 150,000
- senses: 200,222
- examples: 603,565
- sense_examples: 2,656,714
- word_forms: 0
- DB_SIZE_BYTES: 482,541,568
- DB_SIZE_MB: 460.19

### 9-4. 상태 요약
- 1차에서 이미 300MB 목표(약 333MB)를 달성.
- 2차 증분 후 현재 DB는 약 460MB.
- 현재 산출물 기준 최대치(현 배치 파라미터 내): `data/processed/dictionary.db` 460.19MB.

### 9-5. 다음 배치 제안 파라미터
현재 300MB를 초과했으므로, 운영 선택지는 2가지:
1) **300MB 근접 유지**: 1차 파라미터(120k/400k)를 기준 배포본으로 사용
2) **확장본 계속 증분**: 아래처럼 상향 실행
```bash
DB_PATH=data/processed/dictionary.db \
OEWN_INPUT=data/raw/real/oewn/oewn_2025_en.jsonl \
TATOEBA_INPUT=data/raw/real/tatoeba/sentences_en.tsv \
OEWN_MAX_ROWS=160000 \
TATOEBA_MAX_ROWS=900000 \
TOP_WORD_CUTOFF=160000 \
TATOEBA_MIN_TOKENS=4 \
TATOEBA_MAX_TOKENS=20 \
./etl/run_mvp_300mb.sh
```
