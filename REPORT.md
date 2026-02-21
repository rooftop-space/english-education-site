# English Education Site 개편 작업 보고서

## 0) 프로젝트 루트
- 작업 루트: `english-education-site/`
- 아키텍처: 프론트 단일 SPA(정적 파일 + localStorage)

## 1) 이번 단계 목표
기존 REPORT.md의 미완 항목 중 아래 2가지를 MVP+1 수준으로 구현:
- 실가입/인증 플로우
- 관리자 권한/감사로그

## 2) 구현 내용

### A. 실가입/인증(localStorage 기반)
- 회원가입 추가: 이메일 + 비밀번호 + role(learner/admin)
- 최소 검증:
  - 이메일 정규식 검증
  - 비밀번호 6자 이상
  - 중복 이메일 가입 방지
- 로그인/로그아웃 플로우 추가
- 현재 로그인 사용자 상태(`currentUserId`) 저장
- 초기 admin 시드 계정 자동 생성
  - `admin@english-loop.local / Admin1234`

### B. 역할(role) 및 접근 제어
- 사용자 role 도입: `learner`, `admin`
- 관리자 페이지 가드 추가:
  - admin 계정 로그인 시에만 레슨 추가 입력폼 노출
  - 비관리자/게스트는 관리자 작업 차단 + 안내 메시지
- 레슨 추가 API(`addLessonByAdmin`)에서 role 재검증

### C. 감사로그(audit log)
- 감사로그 `auditLogs` 저장 구조 추가
- 다음 이벤트 기록:
  - `signup`
  - `login`
  - `logout`
  - `lesson_add`
  - `subscription_change`
- 로그 항목 구성:
  - 시각(ts), 행위자(actor), 액션(action), 상세(detail)
- 관리자 카드에 최근 감사로그 표시(최대 10개)

### D. UI 반영
- 헤더에 현재 사용자/권한 표시
  - 예: `현재 사용자: foo@bar.com (role: learner)`
- 인증 섹션 신설(가입/로그인/로그아웃)
- 관리자 섹션에 접근 상태 표시 및 감사로그 리스트 추가

## 3) PRD 체크리스트(업데이트)
- [x] 온보딩 진단
- [x] 학습 세션
- [x] SRS 복습 큐
- [x] 진도보드
- [x] 검색/추천 기본
- [x] 구독 퍼널
- [x] 관리자 기본
- [x] 가입/인증(실사용 플로우, localStorage MVP+1)
- [~] 결제 연동/구독 실청구: 미구현(플랜 선택 UI+로그)
- [x] 관리자 권한 인증/감사로그(프론트 MVP+1)

## 4) 변경 파일 목록
- `english-education-site/index.html`
- `english-education-site/styles.css`
- `english-education-site/app.js`
- `english-education-site/REPORT.md`

## 5) 실행 방법
```bash
cd /Users/rooftop/.openclaw/workspace/english-education-site
python3 -m http.server 4173
# 브라우저에서 http://127.0.0.1:4173/index.html 접속
```

## 6) 테스트 방법 및 결과

### 6-1. 정적 문법 검사
```bash
node --check app.js
```
- 결과: **통과(문법 오류 없음)**

### 6-2. 로컬 서빙 스모크
```bash
python3 -m http.server 4173
curl -I http://127.0.0.1:4173/index.html
```
- 결과: **HTTP 200 OK**

### 6-3. 수동 기능 테스트 시나리오
1. 회원가입(learner) → 자동 로그인 확인
2. 로그아웃 → 로그인 재시도(정상/오류 케이스)
3. learner 상태에서 관리자 영역 접근 차단 확인
4. admin 계정 로그인(`admin@english-loop.local / Admin1234`) 후 레슨 추가 성공 확인
5. 구독 버튼 클릭 시 subscription_change 로그 생성 확인
6. 로그인/로그아웃/레슨추가/구독변경 로그가 감사로그에 누적되는지 확인

- 결과: **요구된 플로우 동작 확인(수동 점검)**

## 7) 남은 TODO
1. 비밀번호 해시 고도화(현재 데모용 인코딩)
2. 세션 만료/자동 로그아웃 정책
3. 역할별 기능 분리 고도화(RBAC 세분화)
4. 백엔드 연동(실계정/토큰/서버 감사로그)
5. E2E 자동화 테스트(Playwright)
