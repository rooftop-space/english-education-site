#!/usr/bin/env python3
"""Quality-upgrade level_recommendations JSON payload in dictionary.db.

Safety procedure:
1) backup sqlite file
2) transform rows (dry-run by default)
3) validate summary checks
4) apply changes when --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class RowChange:
    level: str
    rank: int
    lemma: str
    before_meaning_1: str | None
    after_meaning_1: str | None
    before_meaning_2: str | None
    after_meaning_2: str | None
    before_examples_json: str
    after_examples_json: str
    before_meaning_1_ko: str | None
    after_meaning_1_ko: str | None
    before_meaning_2_ko: str | None
    after_meaning_2_ko: str | None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--apply", action="store_true", help="Persist DB changes")
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--backup-dir", default="data/processed/backups")
    p.add_argument("--sample-out", default="logs/quality_upgrade_samples.json")
    p.add_argument("--json-out", default="data/processed/level_recommendations.json")
    return p.parse_args()


def norm_text(v: str | None) -> str | None:
    if not v:
        return None
    t = re.sub(r"\s+", " ", v).strip()
    t = re.sub(r"\s*([;:,.])\s*$", "", t)
    return t or None


def norm_meaning(v: str | None) -> str | None:
    t = norm_text(v)
    if not t:
        return None
    t = re.sub(r"^to\s+", "", t, flags=re.IGNORECASE)
    return t


def norm_example(v: str | None) -> str | None:
    t = norm_text(v)
    if not t:
        return None
    if len(t) < 8 or len(t) > 180:
        return None
    if not re.search(r"[A-Za-z]", t):
        return None
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    t = re.sub(r"([.!?]){2,}$", r"\1", t)
    t = t[0].upper() + t[1:] if len(t) > 1 else t.upper()
    if t[-1] not in ".!?":
        t += "."
    return t


def backup_db(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"dictionary.backup.{ts}.db"
    shutil.copy2(db_path, out)
    return out


def export_json(conn: sqlite3.Connection, out_path: Path) -> None:
    payload = {"levels": {}}
    for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        rows = conn.execute(
            """
            SELECT word_id, lemma, pos, freq, meaning_1, meaning_2,
                   meaning_1_ko, meaning_2_ko, ko_translation_source,
                   ko_translation_is_machine, ko_translation_quality,
                   examples_json
            FROM level_recommendations WHERE level=? ORDER BY rank_in_level
            """,
            (level,),
        ).fetchall()
        payload["levels"][level] = [
            {
                "word_id": r[0],
                "lemma": r[1],
                "pos": r[2],
                "freq": r[3],
                "meaning_1": r[4],
                "meaning_2": r[5],
                "meaning_1_ko": r[6],
                "meaning_2_ko": r[7],
                "ko_translation_source": r[8],
                "ko_translation_is_machine": bool(r[9]) if r[9] is not None else None,
                "ko_translation_quality": r[10],
                "examples_by_meaning": json.loads(r[11]),
            }
            for r in rows
        ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def transform_row(conn: sqlite3.Connection, row) -> RowChange | None:
    level, rank, lemma, m1, m2, m1k, m2k, ex_json = row
    m1n = norm_meaning(m1)
    m2n = norm_meaning(m2)
    if m2n and m1n and m2n.casefold() == m1n.casefold():
        m2n = None

    try:
        groups = json.loads(ex_json)
    except Exception:
        groups = []

    used_examples = set()
    out_groups = []
    for g in groups:
        gm = norm_meaning(g.get("meaning"))
        if not gm:
            continue
        if out_groups and out_groups[-1]["meaning"].casefold() == gm.casefold():
            target = out_groups[-1]
        else:
            target = {"meaning": gm, "examples": []}
            out_groups.append(target)

        for ex in g.get("examples", []):
            enx = norm_example(ex)
            if not enx:
                continue
            key = enx.casefold()
            if key in used_examples:
                continue
            used_examples.add(key)
            target["examples"].append(enx)

    # drop empty meaning buckets
    out_groups = [g for g in out_groups if g["examples"]]
    if not out_groups:
        return None

    # KO backfill from cache if absent
    if (not m1k) and m1n:
        hit = conn.execute(
            "SELECT meaning_ko FROM meaning_translations_ko WHERE meaning_en=?",
            (m1n,),
        ).fetchone()
        if hit:
            m1k = hit[0]
    if (not m2k) and m2n:
        hit = conn.execute(
            "SELECT meaning_ko FROM meaning_translations_ko WHERE meaning_en=?",
            (m2n,),
        ).fetchone()
        if hit:
            m2k = hit[0]
    if m1k and m2k and m1k == m2k:
        m2k = None

    ex_after = json.dumps(out_groups, ensure_ascii=False)
    if (m1n, m2n, ex_after, m1k, m2k) == (m1, m2, ex_json, row[5], row[6]):
        return None

    return RowChange(
        level=level,
        rank=rank,
        lemma=lemma,
        before_meaning_1=m1,
        after_meaning_1=m1n,
        before_meaning_2=m2,
        after_meaning_2=m2n,
        before_examples_json=ex_json,
        after_examples_json=ex_after,
        before_meaning_1_ko=row[5],
        after_meaning_1_ko=m1k,
        before_meaning_2_ko=row[6],
        after_meaning_2_ko=m2k,
    )


def validate(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM level_recommendations").fetchone()[0]
    bad_examples = conn.execute(
        "SELECT COUNT(*) FROM level_recommendations WHERE examples_json IS NULL OR length(trim(examples_json))=0"
    ).fetchone()[0]
    per_level = conn.execute(
        "SELECT level, COUNT(*) FROM level_recommendations GROUP BY level ORDER BY level"
    ).fetchall()
    return {
        "total_rows": total,
        "rows_with_empty_examples_json": bad_examples,
        "per_level": [{"level": l, "count": c} for l, c in per_level],
    }


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    conn = sqlite3.connect(db_path)

    backup_path = None
    if not args.no_backup:
        backup_path = backup_db(db_path, Path(args.backup_dir))

    rows = conn.execute(
        """
        SELECT level, rank_in_level, lemma, meaning_1, meaning_2,
               meaning_1_ko, meaning_2_ko, examples_json
        FROM level_recommendations
        ORDER BY level, rank_in_level
        """
    ).fetchall()

    changes: list[RowChange] = []
    for row in rows:
        c = transform_row(conn, row)
        if c:
            changes.append(c)

    samples = [
        {
            "level": c.level,
            "rank": c.rank,
            "lemma": c.lemma,
            "meaning_1": {"before": c.before_meaning_1, "after": c.after_meaning_1},
            "meaning_2": {"before": c.before_meaning_2, "after": c.after_meaning_2},
            "examples_before": json.loads(c.before_examples_json)[:1],
            "examples_after": json.loads(c.after_examples_json)[:1],
            "meaning_1_ko": {"before": c.before_meaning_1_ko, "after": c.after_meaning_1_ko},
            "meaning_2_ko": {"before": c.before_meaning_2_ko, "after": c.after_meaning_2_ko},
        }
        for c in changes[:10]
    ]
    sample_path = Path(args.sample_out)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply:
        for c in changes:
            conn.execute(
                """
                UPDATE level_recommendations
                SET meaning_1=?, meaning_2=?, meaning_1_ko=?, meaning_2_ko=?, examples_json=?
                WHERE level=? AND rank_in_level=?
                """,
                (
                    c.after_meaning_1,
                    c.after_meaning_2,
                    c.after_meaning_1_ko,
                    c.after_meaning_2_ko,
                    c.after_examples_json,
                    c.level,
                    c.rank,
                ),
            )
        conn.commit()
        export_json(conn, Path(args.json_out))

    result = {
        "mode": "apply" if args.apply else "dry-run",
        "backup": str(backup_path) if backup_path else None,
        "rows_scanned": len(rows),
        "rows_changed": len(changes),
        "sample_path": str(sample_path),
        "validation": validate(conn),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
