# DATA_LICENSES

오프라인 사전 데이터 MVP에서 사용하는 소스와 라이선스 고지.

## 1) Open English WordNet (OEWN)
- 용도: 단어/품사/뜻/활용형 기본 사전 데이터
- 저장 테이블: `words`, `senses`, `word_forms`
- 기본 source 값: `OEWN`
- 기본 license 값: `CC BY 4.0`
- 참고: 배포 전 실제 사용 버전의 라이선스 원문/저작자 표시 요구사항 재검증 필요

## 2) Tatoeba
- 용도: 예문 데이터
- 저장 테이블: `examples`, `sense_examples`
- 기본 source 값: `Tatoeba`
- 기본 license 값: `CC BY 2.0 FR`
- 참고: 문장별 작성자 attribution 요구사항 및 재배포 정책 검토 필요

## 3) 필드 정책
모든 핵심 테이블에 아래 필드를 유지:
- `source`: 데이터 출처
- `license`: 라이선스 식별
- `source_ref`: 원문 레퍼런스(예: 원본 id/URL/키)

## 4) 실제 대용량 데이터 배치 위치
- OEWN 원본: `data/raw/real/oewn/`
  - 사용본: `x-englishwordnet/json` 저장소의 `oewn-2025.json.zip` (OEWN CC BY 4.0)
- Tatoeba 원본: `data/raw/real/tatoeba/`
  - 사용본: Tatoeba 공식 exports의 `sentences.tar.bz2` (문장 라이선스 CC BY 2.0 FR)
- 정규화/중간 산출물: `data/processed/`

샘플 파일(`data/raw/sample_oewn.jsonl`, `data/raw/sample_tatoeba.tsv`)은 개발/테스트용이며,
실데이터 적재 시에는 위 real 경로의 원본/가공본만 사용.
