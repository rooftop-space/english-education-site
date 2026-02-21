#!/usr/bin/env python3
"""Ingest Tatoeba-like TSV sentence data into sqlite.

Expected TSV columns:
- id, lang, sentence, license, source_ref, lemma(optional), level(optional), synthetic(optional)

If lemma is provided, the script links examples to all senses of that lemma.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

DEFAULT_SOURCE = "Tatoeba"
DEFAULT_LICENSE = "CC BY 2.0 FR"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="sqlite db path")
    p.add_argument("--input", required=True, help="tsv path")
    p.add_argument("--source", default=DEFAULT_SOURCE)
    p.add_argument("--license", dest="license_name", default=DEFAULT_LICENSE)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    input_path = Path(args.input)

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path} (create schema first)")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    inserted_examples = linked = 0

    with input_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {"id", "lang", "sentence"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise SystemExit("TSV must include: id, lang, sentence")

        for row in reader:
            sentence = (row.get("sentence") or "").strip()
            if not sentence:
                continue

            ex_license = row.get("license") or args.license_name
            source_ref = row.get("source_ref") or f"tatoeba:{row.get('id')}"
            level = row.get("level") or None
            synthetic = 1 if (row.get("synthetic") or "0") in {"1", "true", "True"} else 0

            cur.execute(
                """
                INSERT INTO examples (sentence, lang, level, source, license, source_ref, synthetic)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sentence, source) DO UPDATE SET
                  lang=excluded.lang,
                  level=COALESCE(excluded.level, examples.level),
                  license=excluded.license,
                  source_ref=COALESCE(excluded.source_ref, examples.source_ref),
                  synthetic=excluded.synthetic
                """,
                (sentence, row.get("lang") or "eng", level, args.source, ex_license, source_ref, synthetic),
            )

            cur.execute("SELECT id FROM examples WHERE sentence=? AND source=?", (sentence, args.source))
            example_id = cur.fetchone()[0]
            inserted_examples += 1

            lemma = (row.get("lemma") or "").strip().lower()
            if lemma:
                cur.execute(
                    """
                    SELECT s.id
                    FROM senses s
                    JOIN words w ON w.id = s.word_id
                    WHERE w.lemma = ?
                    """,
                    (lemma,),
                )
                sense_ids = [r[0] for r in cur.fetchall()]
                for sense_id in sense_ids:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO sense_examples
                        (sense_id, example_id, source, license, source_ref)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (sense_id, example_id, args.source, ex_license, source_ref),
                    )
                    if cur.rowcount:
                        linked += 1

    conn.commit()
    conn.close()

    print(f"[Tatoeba ingest] examples processed={inserted_examples}, sense links inserted={linked}")


if __name__ == "__main__":
    main()
