#!/usr/bin/env python3
"""Translate level recommendation meanings (EN -> KO) with reliable sources.

Priority order:
1) Curated glossary (local CSV, human quality)
2) DeepL API (official paid/free API)
3) Optional unofficial fallback (disabled by default)

Design goals:
- Idempotent reruns
- Explicit source/quality metadata per translated field
- Safe incremental updates for selected CEFR levels
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
MAPPING_RULES = [
    {"level": "A1", "rank_pct_lte": 0.05},
    {"level": "A2", "rank_pct_lte": 0.15},
    {"level": "B1", "rank_pct_lte": 0.35},
    {"level": "B2", "rank_pct_lte": 0.60},
    {"level": "C1", "rank_pct_lte": 0.80},
    {"level": "C2", "rank_pct_lte": 1.00},
]


@dataclass
class TranslationResult:
    ko: str
    source: str
    is_machine: int
    quality: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--json-out", required=True)
    p.add_argument("--levels", default="A1,A2")
    p.add_argument("--glossary-csv", default="data/processed/meaning_glossary_ko.csv")
    p.add_argument("--provider", choices=["deepl"], default="deepl")
    p.add_argument("--deepl-api-key", default=os.getenv("DEEPL_API_KEY", ""))
    p.add_argument("--deepl-free", action="store_true")
    p.add_argument("--batch-size", type=int, default=40)
    p.add_argument("--sleep-ms", type=int, default=80)
    p.add_argument("--force-refresh", action="store_true")
    p.add_argument("--allow-unofficial-fallback", action="store_true")
    p.add_argument("--allow-partial", action="store_true")
    return p.parse_args()


def norm_text(text: str | None) -> str | None:
    if not text:
        return None
    t = re.sub(r"\s+", " ", text).strip()
    return t or None


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meaning_translations_ko (
          meaning_en TEXT PRIMARY KEY,
          meaning_ko TEXT NOT NULL,
          source TEXT NOT NULL,
          is_machine INTEGER NOT NULL DEFAULT 1,
          quality_tier TEXT NOT NULL DEFAULT 'machine',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_meaning_translations_ko_source
          ON meaning_translations_ko(source);
        """
    )

    try:
        conn.execute("ALTER TABLE meaning_translations_ko ADD COLUMN quality_tier TEXT NOT NULL DEFAULT 'machine'")
    except sqlite3.OperationalError:
        pass

    for col, typ in [
        ("meaning_1_ko", "TEXT"),
        ("meaning_2_ko", "TEXT"),
        ("ko_translation_source", "TEXT"),
        ("ko_translation_is_machine", "INTEGER"),
        ("ko_translation_quality", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE level_recommendations ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass


def load_glossary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            en = norm_text(row.get("meaning_en"))
            ko = norm_text(row.get("meaning_ko"))
            if not en or not ko:
                continue
            out[en] = ko
    return out


def upsert_cache(conn: sqlite3.Connection, meaning_en: str, result: TranslationResult) -> None:
    conn.execute(
        """
        INSERT INTO meaning_translations_ko(meaning_en, meaning_ko, source, is_machine, quality_tier, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(meaning_en) DO UPDATE SET
          meaning_ko=excluded.meaning_ko,
          source=excluded.source,
          is_machine=excluded.is_machine,
          quality_tier=excluded.quality_tier,
          updated_at=CURRENT_TIMESTAMP
        """,
        (meaning_en, result.ko, result.source, result.is_machine, result.quality),
    )


def deepl_translate_batch(texts: list[str], api_key: str, use_free: bool) -> list[str]:
    if not api_key:
        raise RuntimeError("DEEPL_API_KEY is required for provider=deepl")

    endpoint = "https://api-free.deepl.com/v2/translate" if use_free else "https://api.deepl.com/v2/translate"
    form = [("source_lang", "EN"), ("target_lang", "KO")] + [("text", t) for t in texts]
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return [norm_text(item.get("text")) or "" for item in payload.get("translations", [])]


def gtx_translate_one(text: str) -> str:
    q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    translated = "".join(part[0] for part in payload[0] if part and part[0])
    return norm_text(translated) or ""


def fetch_target_rows(conn: sqlite3.Connection, levels: list[str], force_refresh: bool):
    q = f"""
    SELECT level, rank_in_level, meaning_1, meaning_2, meaning_1_ko, meaning_2_ko
    FROM level_recommendations
    WHERE level IN ({','.join('?' for _ in levels)})
    ORDER BY level, rank_in_level
    """
    rows = conn.execute(q, levels).fetchall()
    if force_refresh:
        return rows

    out = []
    for level, rank, m1, m2, m1k, m2k in rows:
        done_m1 = (not norm_text(m1)) or bool(norm_text(m1k))
        done_m2 = (not norm_text(m2)) or bool(norm_text(m2k))
        if done_m1 and done_m2:
            continue
        out.append((level, rank, m1, m2, m1k, m2k))
    return out


def collect_unique_meanings(rows) -> list[str]:
    seen = set()
    out = []
    for _, _, m1, m2, _, _ in rows:
        for m in [norm_text(m1), norm_text(m2)]:
            if not m or m in seen:
                continue
            seen.add(m)
            out.append(m)
    return out


def load_cache(conn: sqlite3.Connection) -> dict[str, TranslationResult]:
    rows = conn.execute(
        "SELECT meaning_en, meaning_ko, source, is_machine, quality_tier FROM meaning_translations_ko"
    ).fetchall()
    return {
        r[0]: TranslationResult(ko=r[1], source=r[2], is_machine=int(r[3]), quality=r[4])
        for r in rows
    }


def translate_missing(args: argparse.Namespace, meanings: list[str], glossary: dict[str, str], cache: dict[str, TranslationResult], conn: sqlite3.Connection) -> int:
    translated = 0

    # 1) curated glossary (human quality)
    for m in meanings:
        if m in cache:
            continue
        if m not in glossary:
            continue
        result = TranslationResult(glossary[m], "curated_glossary", 0, "human_curated")
        cache[m] = result
        upsert_cache(conn, m, result)
        translated += 1
    conn.commit()

    pending = [m for m in meanings if m not in cache]
    if not pending:
        return translated

    # 2) DeepL official API
    if args.provider == "deepl":
        if not args.deepl_api_key and not args.allow_unofficial_fallback and not args.allow_partial:
            raise RuntimeError("DEEPL_API_KEY가 없어 번역을 진행할 수 없습니다. --allow-partial 또는 --allow-unofficial-fallback 사용 가능")

        if args.deepl_api_key:
            for i in range(0, len(pending), args.batch_size):
                batch = pending[i:i + args.batch_size]
                ko_list = deepl_translate_batch(batch, args.deepl_api_key, args.deepl_free)
                if len(ko_list) != len(batch):
                    raise RuntimeError("DeepL batch size mismatch")
                for en, ko in zip(batch, ko_list):
                    ko = norm_text(ko)
                    if not ko:
                        continue
                    result = TranslationResult(ko, "deepl_api", 1, "machine_official")
                    cache[en] = result
                    upsert_cache(conn, en, result)
                    translated += 1
                conn.commit()
                if args.sleep_ms > 0:
                    time.sleep(args.sleep_ms / 1000)

    pending = [m for m in meanings if m not in cache]

    # 3) Optional unofficial fallback
    if pending and args.allow_unofficial_fallback:
        for en in pending:
            ko = gtx_translate_one(en)
            if not ko:
                continue
            result = TranslationResult(ko, "google_gtx_unofficial", 1, "machine_unofficial")
            cache[en] = result
            upsert_cache(conn, en, result)
            translated += 1
        conn.commit()

    return translated


def apply_rows(conn: sqlite3.Connection, rows, cache: dict[str, TranslationResult]) -> int:
    changed = 0
    for level, rank, m1, m2, _, _ in rows:
        m1n = norm_text(m1)
        m2n = norm_text(m2)

        r1 = cache.get(m1n) if m1n else None
        r2 = cache.get(m2n) if m2n else None

        m1_ko = r1.ko if r1 else None
        m2_ko = r2.ko if r2 else None
        source = r1.source if r1 else (r2.source if r2 else None)
        is_machine = r1.is_machine if r1 else (r2.is_machine if r2 else None)
        quality = r1.quality if r1 else (r2.quality if r2 else None)

        if m1_ko and m2_ko and m1_ko == m2_ko:
            m2_ko = None

        cur = conn.execute(
            "SELECT meaning_1_ko, meaning_2_ko, ko_translation_source, ko_translation_is_machine, ko_translation_quality FROM level_recommendations WHERE level=? AND rank_in_level=?",
            (level, rank),
        ).fetchone()
        old = tuple(cur) if cur else (None, None, None, None, None)
        new = (m1_ko, m2_ko, source, is_machine, quality)
        if old == new:
            continue

        conn.execute(
            """
            UPDATE level_recommendations
            SET meaning_1_ko=?, meaning_2_ko=?, ko_translation_source=?, ko_translation_is_machine=?, ko_translation_quality=?
            WHERE level=? AND rank_in_level=?
            """,
            (m1_ko, m2_ko, source, is_machine, quality, level, rank),
        )
        changed += 1

    conn.commit()
    return changed


def export_json(conn: sqlite3.Connection, json_out: Path) -> int:
    payload = {
        "mapping_version": "meaning_ko_pipeline_v3_reliable",
        "mapping_rules": MAPPING_RULES,
        "levels": {},
    }

    total = 0
    for level in LEVELS:
        rows = conn.execute(
            """
            SELECT word_id, lemma, pos, freq, meaning_1, meaning_2,
                   meaning_1_ko, meaning_2_ko, ko_translation_source,
                   ko_translation_is_machine, ko_translation_quality,
                   examples_json
            FROM level_recommendations
            WHERE level=?
            ORDER BY rank_in_level
            """,
            (level,),
        ).fetchall()
        arr = []
        for r in rows:
            item = {
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
            total += (1 if item["meaning_1_ko"] else 0) + (1 if item["meaning_2_ko"] else 0)
            arr.append(item)
        payload["levels"][level] = arr

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return total


def main() -> None:
    args = parse_args()
    levels = [x.strip().upper() for x in args.levels.split(",") if x.strip()]

    conn = sqlite3.connect(args.db, timeout=60)
    ensure_tables(conn)

    rows = fetch_target_rows(conn, levels, args.force_refresh)
    meanings = collect_unique_meanings(rows)
    glossary = load_glossary(Path(args.glossary_csv))
    cache = load_cache(conn)

    translated_new = translate_missing(args, meanings, glossary, cache, conn)

    unresolved = [m for m in meanings if m not in cache]
    if unresolved and not args.allow_partial:
        raise RuntimeError(f"번역 미해결 {len(unresolved)}건. API 키/설정을 확인하거나 --allow-partial 사용")

    changed_rows = apply_rows(conn, rows, cache)
    ko_fields = export_json(conn, Path(args.json_out))

    print("[translate_meanings_ko] done")
    print(f"  levels={','.join(levels)}")
    print(f"  rows_scanned={len(rows)}")
    print(f"  unique_meanings={len(meanings)}")
    print(f"  glossary_entries={len(glossary)}")
    print(f"  newly_translated={translated_new}")
    print(f"  unresolved={len(unresolved)}")
    print(f"  rows_changed={changed_rows}")
    print(f"  ko_fields_in_json={ko_fields}")

    conn.close()


if __name__ == "__main__":
    main()
