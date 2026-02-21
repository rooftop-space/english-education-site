#!/usr/bin/env python3
"""Ingest OEWN/WordNet-like lexical data into sqlite.

Accepted input format (JSON or JSONL):
- JSONL: one entry per line
- JSON: either a list of entries or {"entries": [...]} 

Entry shape (minimum):
{
  "lemma": "run",
  "pos": "verb",
  "level": "B1",
  "freq": 12.3,
  "source_ref": "oewn:run%2:38:00::",
  "forms": [{"form": "runs", "form_type": "3sg"}],
  "senses": [
    {
      "sense_key": "run.v.01",
      "definition": "move fast by using one's feet",
      "domain": "general"
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List

DEFAULT_SOURCE = "OEWN"
DEFAULT_LICENSE = "CC BY 4.0"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="sqlite db path")
    p.add_argument("--input", required=True, help="path to json/jsonl")
    p.add_argument("--source", default=DEFAULT_SOURCE)
    p.add_argument("--license", dest="license_name", default=DEFAULT_LICENSE)
    return p.parse_args()


def load_entries(path: Path) -> Iterable[Dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return data["entries"]
    raise ValueError("Unsupported OEWN input shape")


def upsert_word(cur: sqlite3.Cursor, entry: Dict, source: str, license_name: str) -> int:
    lemma = (entry.get("lemma") or "").strip().lower()
    if not lemma:
        raise ValueError("lemma is required")

    pos = entry.get("pos")
    level = entry.get("level")
    freq = entry.get("freq")
    source_ref = entry.get("source_ref")

    cur.execute(
        """
        INSERT INTO words (lemma, pos, level, freq, source, license, source_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lemma, pos, source) DO UPDATE SET
          level=COALESCE(excluded.level, words.level),
          freq=COALESCE(excluded.freq, words.freq),
          license=excluded.license,
          source_ref=COALESCE(excluded.source_ref, words.source_ref)
        """,
        (lemma, pos, level, freq, source, license_name, source_ref),
    )

    cur.execute("SELECT id FROM words WHERE lemma=? AND pos IS ? AND source=?", (lemma, pos, source))
    return cur.fetchone()[0]


def upsert_senses(cur: sqlite3.Cursor, word_id: int, senses: List[Dict], source: str, license_name: str) -> int:
    count = 0
    for s in senses or []:
        definition = (s.get("definition") or "").strip()
        if not definition:
            continue
        cur.execute(
            """
            INSERT OR IGNORE INTO senses
            (word_id, sense_key, definition, domain, source, license, source_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                word_id,
                s.get("sense_key"),
                definition,
                s.get("domain"),
                source,
                license_name,
                s.get("source_ref"),
            ),
        )
        if cur.rowcount:
            count += 1
    return count


def upsert_forms(cur: sqlite3.Cursor, word_id: int, forms: List[Dict], source: str, license_name: str) -> int:
    count = 0
    for f in forms or []:
        form = (f.get("form") or "").strip().lower()
        if not form:
            continue
        cur.execute(
            """
            INSERT OR IGNORE INTO word_forms
            (word_id, form, form_type, source, license, source_ref)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (word_id, form, f.get("form_type"), source, license_name, f.get("source_ref")),
        )
        if cur.rowcount:
            count += 1
    return count


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    input_path = Path(args.input)

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path} (create schema first)")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    inserted_words = inserted_senses = inserted_forms = 0
    for entry in load_entries(input_path):
        word_id = upsert_word(cur, entry, args.source, args.license_name)
        inserted_words += 1
        inserted_senses += upsert_senses(cur, word_id, entry.get("senses", []), args.source, args.license_name)
        inserted_forms += upsert_forms(cur, word_id, entry.get("forms", []), args.source, args.license_name)

    conn.commit()
    conn.close()

    print(
        f"[OEWN ingest] words processed={inserted_words}, senses inserted={inserted_senses}, forms inserted={inserted_forms}"
    )


if __name__ == "__main__":
    main()
