#!/usr/bin/env python3
"""Build CEFR-level word recommendations with meanings/examples.

Outputs:
1) sqlite materialized table: level_recommendations
2) sqlite view: v_level_recommendations
3) json export: data/processed/level_recommendations.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

LEVEL_RULES = [
    ("A1", 0.05),
    ("A2", 0.15),
    ("B1", 0.35),
    ("B2", 0.60),
    ("C1", 0.80),
    ("C2", 1.00),
]

MAPPING_VERSION = "freq_percentile_v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--json-out", required=True)
    p.add_argument("--per-level", type=int, default=200)
    return p.parse_args()


def assign_level(rank_pct: float) -> str:
    for level, threshold in LEVEL_RULES:
        if rank_pct <= threshold:
            return level
    return "C2"


def fetch_candidates(conn: sqlite3.Connection) -> list[dict]:
    q = """
    SELECT
      w.id,
      w.lemma,
      w.pos,
      w.freq,
      COUNT(DISTINCT s.id) AS sense_count,
      COUNT(DISTINCT se.example_id) AS example_count
    FROM words w
    JOIN senses s ON s.word_id = w.id
    JOIN sense_examples se ON se.sense_id = s.id
    WHERE w.freq IS NOT NULL
      AND w.lemma IS NOT NULL
      AND length(w.lemma) >= 2
      AND w.lemma GLOB '[a-z]*'
    GROUP BY w.id, w.lemma, w.pos, w.freq
    HAVING example_count > 0
    ORDER BY w.freq DESC, example_count DESC, w.id ASC
    """
    rows = conn.execute(q).fetchall()
    out = []
    total = len(rows)
    for idx, row in enumerate(rows):
        rank_pct = 0.0 if total <= 1 else idx / (total - 1)
        out.append(
            {
                "word_id": row[0],
                "lemma": row[1],
                "pos": row[2],
                "freq": row[3],
                "sense_count": row[4],
                "example_count": row[5],
                "rank_pct": rank_pct,
                "level": assign_level(rank_pct),
            }
        )
    return out


def top_senses(conn: sqlite3.Connection, word_id: int, limit: int = 2) -> list[tuple[int, str]]:
    q = """
    SELECT
      s.id,
      s.definition,
      COUNT(se.example_id) AS ex_cnt
    FROM senses s
    LEFT JOIN sense_examples se ON se.sense_id = s.id
    WHERE s.word_id = ?
    GROUP BY s.id, s.definition
    ORDER BY ex_cnt DESC, length(s.definition) ASC, s.id ASC
    LIMIT ?
    """
    return [(r[0], r[1]) for r in conn.execute(q, (word_id, limit)).fetchall()]


def top_examples(conn: sqlite3.Connection, sense_id: int, limit: int = 3) -> list[str]:
    q = """
    SELECT DISTINCT e.sentence
    FROM examples e
    JOIN sense_examples se ON se.example_id = e.id
    WHERE se.sense_id = ?
    ORDER BY abs(length(e.sentence) - 70) ASC, e.id ASC
    LIMIT ?
    """
    return [r[0] for r in conn.execute(q, (sense_id, limit)).fetchall()]


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS level_recommendation_mapping_rules (
          mapping_version TEXT PRIMARY KEY,
          rules_json TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS word_level_norm (
          word_id INTEGER PRIMARY KEY,
          cefr_level TEXT NOT NULL,
          rank_pct REAL NOT NULL,
          freq REAL,
          mapping_version TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(word_id) REFERENCES words(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_word_level_norm_level
          ON word_level_norm(cefr_level);

        CREATE TABLE IF NOT EXISTS level_recommendations (
          level TEXT NOT NULL,
          rank_in_level INTEGER NOT NULL,
          word_id INTEGER NOT NULL,
          lemma TEXT NOT NULL,
          pos TEXT,
          freq REAL,
          meaning_1 TEXT,
          meaning_2 TEXT,
          meaning_1_ko TEXT,
          meaning_2_ko TEXT,
          ko_translation_source TEXT,
          ko_translation_is_machine INTEGER,
          examples_json TEXT NOT NULL,
          mapping_version TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(level, rank_in_level)
        );

        CREATE INDEX IF NOT EXISTS idx_level_recommendations_level
          ON level_recommendations(level);

        CREATE INDEX IF NOT EXISTS idx_level_recommendations_word
          ON level_recommendations(word_id);

        CREATE VIEW IF NOT EXISTS v_level_recommendations AS
        SELECT level, rank_in_level, lemma, pos, freq, meaning_1, meaning_2, meaning_1_ko, meaning_2_ko,
               ko_translation_source, ko_translation_is_machine, examples_json
        FROM level_recommendations
        ORDER BY level, rank_in_level;
        """
    )

    for column_name, column_type in [
        ("meaning_1_ko", "TEXT"),
        ("meaning_2_ko", "TEXT"),
        ("ko_translation_source", "TEXT"),
        ("ko_translation_is_machine", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE level_recommendations ADD COLUMN {column_name} {column_type}")
        except sqlite3.OperationalError:
            pass


def build(conn: sqlite3.Connection, per_level: int) -> tuple[list[dict], dict[str, list[dict]]]:
    candidates = fetch_candidates(conn)
    buckets: dict[str, list[dict]] = defaultdict(list)

    for c in candidates:
        if len(buckets[c["level"]]) >= per_level:
            continue

        senses = top_senses(conn, c["word_id"], limit=2)
        if not senses:
            continue

        meanings = [s[1] for s in senses]
        examples_by_meaning = []
        total_examples = 0
        for sid, definition in senses:
            exs = top_examples(conn, sid, limit=3)
            if exs:
                total_examples += len(exs)
            examples_by_meaning.append({"meaning": definition, "examples": exs})

        if total_examples == 0:
            continue

        row = {
            "word_id": c["word_id"],
            "lemma": c["lemma"],
            "pos": c["pos"],
            "freq": c["freq"],
            "meaning_1": meanings[0] if len(meanings) > 0 else None,
            "meaning_2": meanings[1] if len(meanings) > 1 else None,
            "examples_by_meaning": examples_by_meaning,
        }
        buckets[c["level"]].append(row)

    # ensure level keys exist
    for level, _ in LEVEL_RULES:
        buckets[level] = buckets.get(level, [])

    return candidates, buckets


def write_outputs(
    conn: sqlite3.Connection,
    buckets: dict[str, list[dict]],
    json_out: Path,
    candidates: list[dict],
) -> None:
    conn.execute("DELETE FROM level_recommendations")
    conn.execute("DELETE FROM word_level_norm")
    conn.execute(
        "INSERT OR REPLACE INTO level_recommendation_mapping_rules(mapping_version, rules_json) VALUES (?, ?)",
        (MAPPING_VERSION, json.dumps(LEVEL_RULES, ensure_ascii=False)),
    )

    conn.executemany(
        """
        INSERT INTO word_level_norm(word_id, cefr_level, rank_pct, freq, mapping_version)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (c["word_id"], c["level"], c["rank_pct"], c["freq"], MAPPING_VERSION)
            for c in candidates
        ],
    )

    for level, _ in LEVEL_RULES:
        for idx, row in enumerate(buckets[level], start=1):
            conn.execute(
                """
                INSERT INTO level_recommendations(
                  level, rank_in_level, word_id, lemma, pos, freq,
                  meaning_1, meaning_2, meaning_1_ko, meaning_2_ko,
                  ko_translation_source, ko_translation_is_machine,
                  examples_json, mapping_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    level,
                    idx,
                    row["word_id"],
                    row["lemma"],
                    row["pos"],
                    row["freq"],
                    row["meaning_1"],
                    row["meaning_2"],
                    None,
                    None,
                    None,
                    None,
                    json.dumps(row["examples_by_meaning"], ensure_ascii=False),
                    MAPPING_VERSION,
                ),
            )

    conn.commit()

    payload = {
        "mapping_version": MAPPING_VERSION,
        "mapping_rules": [{"level": l, "rank_pct_lte": t} for l, t in LEVEL_RULES],
        "levels": {level: buckets[level] for level, _ in LEVEL_RULES},
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    ensure_tables(conn)
    candidates, buckets = build(conn, args.per_level)
    write_outputs(conn, buckets, Path(args.json_out), candidates)

    print("[level recommendations] done")
    for level, _ in LEVEL_RULES:
        print(f"  {level}: {len(buckets[level])}")

    conn.close()


if __name__ == "__main__":
    main()
