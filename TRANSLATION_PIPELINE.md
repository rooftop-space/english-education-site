# meaning_ko 파이프라인 v2

## 목적
- 신뢰 가능한 소스(DeepL API) 기반 EN->KO 번역
- 대량처리: 캐시/재시도/증분
- 결과 동기화: DB + JSON

## 소스 근거
- Primary: DeepL API
  - 라이선스/약관: DeepL API Terms
  - 요금/쿼터: Free 월 500,000 chars, Pro는 과금
- Fallback: googletrans (비공식, 안정성 보장 없음)

## 실행
```bash
# A1~A2 우선
DEEPL_API_KEY=... ../.venv/bin/python etl/translate_meanings_ko.py \
  --db data/processed/dictionary.db \
  --json-out data/processed/level_recommendations.json \
  --levels A1,A2 \
  --provider deepl \
  --deepl-free

# 전 레벨
DEEPL_API_KEY=... ../.venv/bin/python etl/translate_meanings_ko.py \
  --db data/processed/dictionary.db \
  --json-out data/processed/level_recommendations.json \
  --levels A1,A2,B1,B2,C1,C2 \
  --provider deepl \
  --deepl-free
```

## 검증
```bash
sqlite3 data/processed/dictionary.db "
select level,
       sum(case when meaning_1_ko is not null and trim(meaning_1_ko)<>'' then 1 else 0 end) m1_ko,
       sum(case when meaning_2_ko is not null and trim(meaning_2_ko)<>'' then 1 else 0 end) m2_ko,
       count(*) cnt
from level_recommendations
group by level
order by level;"
```

## 품질 비교 샘플(기존 vs v2)
- 기존: `meaning_translations_ko` (legacy)
- 신규: `meaning_translations_ko_v2`
- 샘플 쿼리:
```bash
sqlite3 data/processed/dictionary.db "
select lr.lemma, lr.meaning_1,
       old.meaning_ko as legacy_ko,
       new.meaning_ko as v2_ko
from level_recommendations lr
left join meaning_translations_ko old on old.meaning_en=lr.meaning_1
left join meaning_translations_ko_v2 new on new.meaning_en=lr.meaning_1
where lr.level in ('A1','A2')
limit 5;"
```
