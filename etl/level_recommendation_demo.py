#!/usr/bin/env python3
"""CLI demo: show level-based recommendations from sqlite materialized table."""

from __future__ import annotations

import argparse
import json
import sqlite3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--level", default="A1", choices=["A1", "A2", "B1", "B2", "C1", "C2"])
    p.add_argument("--limit", type=int, default=5)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT rank_in_level, lemma, pos, meaning_1, meaning_2, examples_json
        FROM level_recommendations
        WHERE level = ?
        ORDER BY rank_in_level
        LIMIT ?
        """,
        (args.level, args.limit),
    )

    rows = cur.fetchall()
    if not rows:
        print(f"No recommendations found for level={args.level}")
        return

    print(f"LEVEL: {args.level} (top {len(rows)})")
    for rank, lemma, pos, m1, m2, examples_json in rows:
        print(f"\n[{rank}] {lemma} ({pos or 'unknown'})")
        if m1:
            print(f" - meaning1: {m1}")
        if m2:
            print(f" - meaning2: {m2}")

        blocks = json.loads(examples_json)
        seen = set()
        for b in blocks:
            for ex in b.get("examples", [])[:3]:
                if ex in seen:
                    continue
                seen.add(ex)
                print(f"    • {ex}")

    conn.close()


if __name__ == "__main__":
    main()
