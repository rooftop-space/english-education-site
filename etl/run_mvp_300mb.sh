#!/usr/bin/env bash
set -euo pipefail

# 300MB 내외 오프라인 사전 MVP 1차 적재 스크립트
# - 영어만 적재
# - 예문 길이 품질 필터 적용
# - 상위 빈도 단어 중심(입력 데이터가 freq 내림차순이라는 가정 하에 max_rows 컷오프)
# - 증분 실행 가능(UPSERT + max_rows)

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${DB_PATH:-$ROOT_DIR/data/processed/dictionary.db}"
OEWN_INPUT="${OEWN_INPUT:-$ROOT_DIR/data/raw/sample_oewn.jsonl}"
TATOEBA_INPUT="${TATOEBA_INPUT:-$ROOT_DIR/data/raw/sample_tatoeba.tsv}"

# 목표치: 약 300MB(상황에 따라 조정)
OEWN_MAX_ROWS="${OEWN_MAX_ROWS:-120000}"
TATOEBA_MAX_ROWS="${TATOEBA_MAX_ROWS:-400000}"
TATOEBA_MIN_TOKENS="${TATOEBA_MIN_TOKENS:-4}"
TATOEBA_MAX_TOKENS="${TATOEBA_MAX_TOKENS:-18}"
TOP_WORD_CUTOFF="${TOP_WORD_CUTOFF:-120000}"

mkdir -p "$(dirname "$DB_PATH")"

if [[ ! -f "$DB_PATH" ]]; then
  sqlite3 "$DB_PATH" < "$ROOT_DIR/sql/schema.sql"
fi

echo "[1/3] OEWN ingest"
python3 "$ROOT_DIR/etl/ingest_oewn.py" \
  --db "$DB_PATH" \
  --input "$OEWN_INPUT" \
  --allow_lang en \
  --max_rows "$OEWN_MAX_ROWS"

echo "[2/3] Tatoeba ingest"
python3 "$ROOT_DIR/etl/ingest_tatoeba.py" \
  --db "$DB_PATH" \
  --input "$TATOEBA_INPUT" \
  --allow_lang en \
  --min_tokens "$TATOEBA_MIN_TOKENS" \
  --max_tokens "$TATOEBA_MAX_TOKENS" \
  --top_word_cutoff "$TOP_WORD_CUTOFF" \
  --max_rows "$TATOEBA_MAX_ROWS"

echo "[3/3] DB stats"
sqlite3 "$DB_PATH" "
select 'words',count(*) from words
union all select 'senses',count(*) from senses
union all select 'examples',count(*) from examples
union all select 'sense_examples',count(*) from sense_examples
union all select 'word_forms',count(*) from word_forms;
"

if command -v stat >/dev/null 2>&1; then
  BYTES=$(stat -f%z "$DB_PATH")
  MB=$(python3 - <<PY
b = $BYTES
print(f"{b/1024/1024:.2f}")
PY
)
  echo "DB_SIZE_BYTES=$BYTES"
  echo "DB_SIZE_MB=$MB"
fi

echo "Done. Re-run with larger *_MAX_ROWS for incremental expansion."
