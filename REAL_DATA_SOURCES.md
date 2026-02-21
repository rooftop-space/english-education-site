# Real Data Sources (Offline Dictionary)

## OEWN (CC BY 4.0)
- Mirror used: https://github.com/x-englishwordnet/json
- File used: `oewn-2025.json.zip` → extracted `oewn.json`
- Local path: `data/raw/real/oewn/`
- Ingest-ready derived file: `data/raw/real/oewn/oewn_2025_en.jsonl`

## Tatoeba (CC BY 2.0 FR)
- Official exports index: https://downloads.tatoeba.org/exports/
- File used: `sentences.tar.bz2` (contains `sentences.csv`)
- Local path: `data/raw/real/tatoeba/`
- Ingest-ready derived file: `data/raw/real/tatoeba/sentences_en.tsv`

## Notes
- Only sources compatible with `DATA_LICENSES.md` were used.
- Large raw/generated binaries are intentionally git-ignored.
