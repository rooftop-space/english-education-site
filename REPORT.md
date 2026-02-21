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

## 6) 호환성/영향
- 기존 프론트 앱(`index.html`, `styles.css`, `app.js`) 미수정
- 데이터 파이프라인 파일만 추가되어 기존 앱 동작 영향 없음
