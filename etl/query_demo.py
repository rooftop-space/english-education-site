#!/usr/bin/env python3
"""Minimal dictionary query demo for app integration."""

from __future__ import annotations

import argparse
import sqlite3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="sqlite db path")
    p.add_argument("--lemma", required=True, help="lemma to query")
    p.add_argument("--limit", type=int, default=5)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT w.id, w.lemma, w.pos, w.level, s.id, s.definition
        FROM words w
        LEFT JOIN senses s ON s.word_id = w.id
        WHERE w.lemma = ?
        ORDER BY s.id
        """,
        (args.lemma.lower(),),
    )
    rows = cur.fetchall()

    if not rows:
        print(f"No entry for lemma='{args.lemma}'")
        return

    word_id, lemma, pos, level, _, _ = rows[0]
    print(f"WORD: {lemma} ({pos or 'unknown'}) level={level or '-'}")

    sense_ids = []
    for _, _, _, _, sense_id, definition in rows:
        if sense_id is None:
            continue
        sense_ids.append(sense_id)
        print(f"  - Sense#{sense_id}: {definition}")

    if not sense_ids:
        return

    q_marks = ",".join("?" for _ in sense_ids)
    cur.execute(
        f"""
        SELECT DISTINCT e.sentence
        FROM examples e
        JOIN sense_examples se ON se.example_id = e.id
        WHERE se.sense_id IN ({q_marks})
        ORDER BY e.id
        LIMIT ?
        """,
        (*sense_ids, args.limit),
    )

    examples = [r[0] for r in cur.fetchall()]
    if examples:
        print("EXAMPLES:")
        for ex in examples:
            print(f"  • {ex}")

    conn.close()


if __name__ == "__main__":
    main()
