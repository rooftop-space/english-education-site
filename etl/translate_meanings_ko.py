#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import hashlib
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path

LEVELS_ALL = ["A1", "A2", "B1", "B2", "C1", "C2"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Translate level recommendation meanings (EN->KO)")
    p.add_argument("--db", required=True)
    p.add_argument("--json-out", required=True)
    p.add_argument("--levels", default="A1,A2")
    p.add_argument("--provider", choices=["deepl", "googletrans"], default="deepl")
    p.add_argument("--deepl-api-key", default=os.getenv("DEEPL_API_KEY", ""))
    p.add_argument("--deepl-free", action="store_true", help="Use DeepL Free endpoint")
    p.add_argument("--allow-unofficial-fallback", action="store_true", help="Allow fallback to google_gtx")
    p.add_argument("--batch-size", type=int, default=40)
    p.add_argument("--max-retries", type=int, default=4)
    p.add_argument("--sleep-ms", type=int, default=120)
    p.add_argument("--force-refresh", action="store_true")
    return p.parse_args()


def norm_text(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meaning_translations_ko_v2 (
          meaning_en TEXT PRIMARY KEY,
          meaning_ko TEXT NOT NULL,
          source TEXT NOT NULL,
          is_machine INTEGER NOT NULL DEFAULT 1,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_meaning_translations_ko_v2_source
          ON meaning_translations_ko_v2(source);
        """
    )
    try:
        conn.execute("ALTER TABLE meaning_translations_ko_v2 ADD COLUMN meaning_hash TEXT")
    except sqlite3.OperationalError:
        pass
    for col, typ in [
        ("meaning_1_ko", "TEXT"),
        ("meaning_2_ko", "TEXT"),
        ("ko_translation_source", "TEXT"),
        ("ko_translation_is_machine", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE level_recommendations ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass


def translate_deepl(texts: list[str], api_key: str, use_free: bool) -> list[str]:
    if not api_key:
        raise RuntimeError("DEEPL_API_KEY missing")
    url = "https://api-free.deepl.com/v2/translate" if use_free else "https://api.deepl.com/v2/translate"
    form = [("target_lang", "KO")] + [("source_lang", "EN")] + [("text", t) for t in texts]
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Authorization": f"DeepL-Auth-Key {api_key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return [norm_text(x.get("text")) or "" for x in payload.get("translations", [])]


def translate_googletrans(texts: list[str]) -> list[str]:
    out: list[str] = []
    for t in texts:
        q = urllib.parse.quote(t)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        translated = "".join(part[0] for part in payload[0] if part and part[0])
        out.append(norm_text(translated) or "")
    return out


def translate_batch(provider: str, texts: list[str], args: argparse.Namespace) -> tuple[list[str], str]:
    if provider == "deepl":
        return translate_deepl(texts, args.deepl_api_key, args.deepl_free), "deepl_api"
    return translate_googletrans(texts), "googletrans_unofficial"


def get_target_rows(conn: sqlite3.Connection, levels: list[str], force: bool):
    q = f"SELECT level, rank_in_level, meaning_1, meaning_2, meaning_1_ko, meaning_2_ko FROM level_recommendations WHERE level IN ({','.join('?' for _ in levels)}) ORDER BY level, rank_in_level"
    rows = conn.execute(q, levels).fetchall()
    if force:
        return rows
    out = []
    for r in rows:
        m1, m2, m1k, m2k = norm_text(r[2]), norm_text(r[3]), norm_text(r[4]), norm_text(r[5])
        done_m1 = (not m1) or bool(m1k)
        done_m2 = (not m2) or bool(m2k)
        if done_m1 and done_m2:
            continue
        out.append(r)
    return out


def export_json(conn: sqlite3.Connection, json_out: Path, provider_used: str) -> int:
    rules_row = conn.execute("SELECT rules_json FROM level_recommendation_mapping_rules ORDER BY created_at DESC LIMIT 1").fetchone()
    rules = json.loads(rules_row[0]) if rules_row else []
    payload = {
        "mapping_version": "meaning_ko_pipeline_v2",
        "mapping_rules": [{"level": l, "rank_pct_lte": t} for l, t in rules],
        "translation_source": provider_used,
        "levels": {},
    }
    total = 0
    for lv in LEVELS_ALL:
        rows = conn.execute(
            "SELECT word_id, lemma, pos, freq, meaning_1, meaning_2, meaning_1_ko, meaning_2_ko, ko_translation_source, ko_translation_is_machine, examples_json FROM level_recommendations WHERE level=? ORDER BY rank_in_level",
            (lv,),
        ).fetchall()
        arr = []
        for r in rows:
            item = {
                "word_id": r[0], "lemma": r[1], "pos": r[2], "freq": r[3],
                "meaning_1": r[4], "meaning_2": r[5], "meaning_1_ko": r[6], "meaning_2_ko": r[7],
                "ko_translation_source": r[8], "ko_translation_is_machine": bool(r[9]) if r[9] is not None else None,
                "examples_by_meaning": json.loads(r[10]),
            }
            total += 1 if item["meaning_1_ko"] else 0
            total += 1 if item["meaning_2_ko"] else 0
            arr.append(item)
        payload["levels"][lv] = arr
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return total


def main() -> None:
    args = parse_args()
    levels = [x.strip().upper() for x in args.levels.split(",") if x.strip()]
    conn = sqlite3.connect(args.db, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    ensure_schema(conn)

    rows = get_target_rows(conn, levels, force=args.force_refresh)
    unique = sorted({m for r in rows for m in [norm_text(r[2]), norm_text(r[3])] if m})

    cache_rows = conn.execute("SELECT meaning_en, meaning_ko FROM meaning_translations_ko_v2").fetchall()
    cache = {r[0]: r[1] for r in cache_rows}
    pending = [m for m in unique if m not in cache or args.force_refresh]

    provider_used = args.provider
    changed = 0
    for i in range(0, len(pending), args.batch_size):
        batch = pending[i:i + args.batch_size]
        last_err = None
        for attempt in range(args.max_retries):
            try:
                translations, provider_label = translate_batch(provider_used, batch, args)
                if len(translations) != len(batch):
                    raise RuntimeError("batch translate size mismatch")
                for en, ko in zip(batch, translations):
                    ko = norm_text(ko)
                    if not ko:
                        continue
                    cache[en] = ko
                    conn.execute(
                        """
                        INSERT INTO meaning_translations_ko_v2(meaning_en, meaning_hash, meaning_ko, source, is_machine, updated_at)
                        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT(meaning_en) DO UPDATE SET
                          meaning_hash=excluded.meaning_hash,
                          meaning_ko=excluded.meaning_ko,
                          source=excluded.source,
                          is_machine=excluded.is_machine,
                          updated_at=CURRENT_TIMESTAMP
                        """,
                        (en, sha1(en), ko, provider_label),
                    )
                conn.commit()
                if args.sleep_ms > 0:
                    time.sleep(args.sleep_ms / 1000)
                break
            except Exception as e:
                last_err = e
                if provider_used == "deepl" and args.allow_unofficial_fallback:
                    provider_used = "googletrans"
                    continue
                if attempt == args.max_retries - 1:
                    raise
                time.sleep((2 ** attempt) * 0.5)
        if last_err and provider_used == "google_gtx":
            pass

    for level, rank, m1, m2, _, _ in rows:
        t1 = cache.get(norm_text(m1) or "") if norm_text(m1) else None
        t2 = cache.get(norm_text(m2) or "") if norm_text(m2) else None
        if t1 and t2 and t1 == t2:
            t2 = None
        res = conn.execute(
            """
            UPDATE level_recommendations
            SET meaning_1_ko=?, meaning_2_ko=?, ko_translation_source=?, ko_translation_is_machine=1
            WHERE level=? AND rank_in_level=?
              AND (
                COALESCE(meaning_1_ko,'')<>COALESCE(?, '') OR
                COALESCE(meaning_2_ko,'')<>COALESCE(?, '') OR
                COALESCE(ko_translation_source,'')<>COALESCE(?, '') OR
                COALESCE(ko_translation_is_machine,-1)<>1
              )
            """,
            (t1, t2, ("deepl_api" if provider_used == "deepl" else "googletrans_unofficial"), level, rank, t1, t2, ("deepl_api" if provider_used == "deepl" else "googletrans_unofficial")),
        )
        changed += res.rowcount
    conn.commit()

    total_ko = export_json(conn, Path(args.json_out), provider_used)
    print("[translate_meanings_ko_v2] done")
    print(f"  levels={','.join(levels)}")
    print(f"  rows_scanned={len(rows)}")
    print(f"  unique_meanings={len(unique)}")
    print(f"  pending_meanings={len(pending)}")
    print(f"  cache_size={len(cache)}")
    print(f"  rows_changed={changed}")
    print(f"  provider_used={provider_used}")
    print(f"  ko_fields_in_json={total_ko}")


if __name__ == "__main__":
    main()
