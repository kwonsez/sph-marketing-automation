# Weekly Marketing Report Automation

매주 월요일, GA4 · Google Ads · 네이버 검색광고 · 네이버 블로그 · Monday.com 리드 데이터를  
자동으로 수집하여 Monday.com `[LI] Weekly Report` 보드에 업로드하는 Python 자동화 스크립트.

---

## 목차

1. [데이터 수집 항목](#1-데이터-수집-항목)
2. [사전 요구사항](#2-사전-요구사항)
3. [로컬 설치 및 설정](#3-로컬-설치-및-설정)
4. [CLI 사용법](#4-cli-사용법)
5. [GitHub Actions 자동화 배포](#5-github-actions-자동화-배포)
6. [프로젝트 구조](#6-프로젝트-구조)
7. [에러 처리 정책](#7-에러-처리-정책)

---

## 1. 데이터 수집 항목

| 데이터 | 출처 | Monday.com 컬럼 |
|---|---|---|
| WAU (주간 활성 사용자) | GA4 | WAU |
| 신청문의 페이지 사용자 | GA4 `/contact` | 신청문의 페이지 사용자 |
| Lead Gen | Monday.com 7개 보드 합산 | Lead Gen |
| 노출수 · 클릭수 · 광고비 | Google Ads | G노출수 · G클릭수 · G광고비 |
| 노출수 · 클릭수 · 광고비 | 네이버 검색광고 | N노출수 · N클릭수 · N광고비 |
| 포스팅수 · 조회수 | 네이버 블로그 (Playwright) | Naver 포스팅수 · N블로그 조회수 |
| 전주대비 Status (4개) | 자동 계산 | 전주대비 / GCTR / NCTR / N전주대비 |

---

## 2. 사전 요구사항

- Python 3.11 이상
- GA4 서비스 계정 JSON 키 (`service-account.json`)
- Google Ads OAuth2 Refresh Token ([tools/ads_refresh_token.py](tools/ads_refresh_token.py) 참고)
- 네이버 블로그 로그인 세션 (`naver_session.json`, [tools/save_naver_session.py](tools/save_naver_session.py) 참고)
- Gmail 앱 비밀번호

---

## 3. 로컬 설치 및 설정

### 3-1. 클론 및 의존성 설치

```bash
git clone <repo-url>
cd weekly_report

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

### 3-2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 채운다.

| 구분 | 변수 | 설명 |
|---|---|---|
| **Monday.com** | `MONDAY_API_TOKEN` | Monday.com API 토큰 |
| | `MONDAY_WEEKLY_BOARD_ID` | `1901011628` (고정) |
| | `MONDAY_LEAD_BOARD_IDS` | 콤마 구분 7개 보드 ID (고정) |
| | `MONDAY_COL_*` | 컬럼 ID 매핑 (`.env.example` 기본값 사용) |
| **GA4** | `GA4_PROPERTY_ID` | GA4 속성 ID (숫자) |
| | `GOOGLE_APPLICATION_CREDENTIALS` | `./service-account.json` (고정) |
| **Google Ads** | `GOOGLE_ADS_DEVELOPER_TOKEN` | 개발자 토큰 |
| | `GOOGLE_ADS_CLIENT_ID` | OAuth2 Client ID |
| | `GOOGLE_ADS_CLIENT_SECRET` | OAuth2 Client Secret |
| | `GOOGLE_ADS_REFRESH_TOKEN` | OAuth2 Refresh Token |
| | `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC 계정 ID (`4692622227`, 고정) |
| | `GOOGLE_ADS_CUSTOMER_ID` | 운영 계정 ID (`4717848584`, 고정) |
| **네이버 검색광고** | `NAVER_ADS_API_KEY` | API 키 |
| | `NAVER_ADS_SECRET_KEY` | Secret 키 |
| | `NAVER_ADS_CUSTOMER_ID` | 고객 ID |
| **네이버 블로그** | `NAVER_LOGIN_ID` | 네이버 로그인 ID |
| | `NAVER_LOGIN_PW` | 네이버 비밀번호 |
| | `NAVER_BLOG_ID` | 블로그 ID (URL의 영문명) |
| **Gmail** | `GMAIL_SENDER` | 발신 Gmail 주소 |
| | `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 (16자리) |
| | `GMAIL_RECIPIENT` | 수신 이메일 주소 |

### 3-3. GA4 서비스 계정 키

`service-account.json` 파일을 프로젝트 루트에 배치한다. (git 제외됨)

### 3-4. Google Ads Refresh Token 발급

```bash
python tools/ads_refresh_token.py
```

출력된 `refresh_token` 값을 `.env`의 `GOOGLE_ADS_REFRESH_TOKEN`에 입력.

### 3-5. 네이버 블로그 세션 저장

네이버는 2단계 인증이 있어 Playwright로 세션을 직접 저장해야 한다.

```bash
python tools/save_naver_session.py
```

브라우저 창이 열리면 직접 로그인 → 완료 후 Enter → `naver_session.json` 저장됨.

> **Note:** 세션은 약 30일 후 만료된다. 만료 시 위 명령을 다시 실행한다.

---

## 4. CLI 사용법

```bash
# 지난주 데이터 자동 수집 및 Monday.com 업로드
python main.py

# 특정 주 지정 (해당 주 월요일 날짜 입력)
python main.py --date 2026-03-30

# 수집만 하고 Monday.com에 쓰지 않음 (테스트)
python main.py --dry-run

# 특정 주 + dry-run
python main.py --date 2026-03-30 --dry-run
```

실행 로그는 콘솔과 `automation.log` 파일에 동시 기록된다.

---

## 5. GitHub Actions 자동화 배포

### 5-1. Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions

**Secrets (민감한 값):**

| Secret 이름 | 값 |
|---|---|
| `MONDAY_API_TOKEN` | Monday.com API 토큰 |
| `GA4_PROPERTY_ID` | GA4 속성 ID |
| `GOOGLE_SA_JSON` | `service-account.json` 파일 내용 전체 (JSON 문자열) |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads 개발자 토큰 |
| `GOOGLE_ADS_CLIENT_ID` | OAuth2 Client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth2 Client Secret |
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth2 Refresh Token |
| `NAVER_ADS_API_KEY` | 네이버 검색광고 API 키 |
| `NAVER_ADS_SECRET_KEY` | 네이버 검색광고 Secret 키 |
| `NAVER_LOGIN_ID` | 네이버 로그인 ID |
| `NAVER_LOGIN_PW` | 네이버 비밀번호 |
| `NAVER_SESSION_JSON` | `naver_session.json` 파일 내용 전체 (JSON 문자열) |
| `GMAIL_SENDER` | 발신 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 |
| `GMAIL_RECIPIENT` | 수신 이메일 주소 |

**Variables (민감하지 않은 값):**

| Variable 이름 | 값 |
|---|---|
| `MONDAY_WEEKLY_BOARD_ID` | `1901011628` |
| `MONDAY_LEAD_BOARD_IDS` | `3126575269,3126575612,...` |
| `MONDAY_COL_START_DATE` | `date__1` |
| `MONDAY_COL_LEAD_GEN` | `numeric1__1` |
| `MONDAY_COL_WAU` | `__` |
| `MONDAY_COL_CONTACT_USERS` | `dup__of_______` |
| `MONDAY_COL_G_IMPRESSIONS` | `___1` |
| `MONDAY_COL_G_CLICKS` | `___2` |
| `MONDAY_COL_G_COST` | `dup__of____` |
| `MONDAY_COL_WOW_CONVERSION` | `status` |
| `MONDAY_COL_WOW_GCTR` | `dup__of_____` |
| `MONDAY_COL_N_IMPRESSIONS` | `dup__of_g___4` |
| `MONDAY_COL_N_CLICKS` | `dup__of____3` |
| `MONDAY_COL_N_COST` | `dup__of_g___6` |
| `MONDAY_COL_WOW_NCTR` | `dup__of_____2` |
| `MONDAY_COL_N_BLOG_POSTS` | `dup__of________` |
| `MONDAY_COL_N_BLOG_VIEWS` | `dup__of_naver_____` |
| `MONDAY_COL_WOW_NAVER` | `dup__of_____4` |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | `4692622227` |
| `GOOGLE_ADS_CUSTOMER_ID` | `4717848584` |
| `NAVER_ADS_CUSTOMER_ID` | 네이버 검색광고 고객 ID |
| `NAVER_BLOG_ID` | 블로그 ID |

### 5-2. GOOGLE_SA_JSON 설정 방법

```bash
# macOS / Linux
cat service-account.json | pbcopy   # 클립보드 복사 후 GitHub에 붙여넣기

# Windows PowerShell
Get-Content service-account.json | Set-Clipboard
```

### 5-3. NAVER_SESSION_JSON 설정 방법

로컬에서 `tools/save_naver_session.py` 실행 후 저장된 `naver_session.json` 내용을 복사해 Secret에 등록.

> **주의:** 세션 만료 시 로컬에서 재생성 후 Secret을 업데이트해야 한다.

### 5-4. 스케줄

- 자동 실행: **매주 월요일 오전 10:00 KST**
- 수동 실행: GitHub Actions → `Weekly Marketing Report` → `Run workflow`  
  날짜 입력 또는 Dry Run 옵션 선택 가능

### 5-5. 실패 시 디버깅

워크플로우 실패 시 Artifacts에서 다운로드 가능:
- `automation-log` — `automation.log` 전체 로그
- `debug-screenshots` — 네이버 블로그 스크래핑 실패 시 스크린샷

---

## 6. 프로젝트 구조

```
weekly_report/
├── .github/workflows/
│   └── weekly_report.yml      # GitHub Actions 워크플로우
├── collectors/
│   ├── base.py                # BaseCollector 추상 클래스
│   ├── ga4.py                 # GA4 수집기
│   ├── google_ads.py          # Google Ads 수집기 (MCC 구조)
│   ├── naver_ads.py           # 네이버 검색광고 수집기 (HMAC 인증)
│   ├── naver_blog.py          # 네이버 블로그 수집기 (Playwright)
│   └── monday_lead.py         # Lead Gen 수집기 (7개 보드 합산)
├── writers/
│   └── monday_writer.py       # Monday.com 6단계 업로드 + 전주대비 계산
├── notifiers/
│   └── gmail_notifier.py      # 성공/실패/중복 Gmail 알림
├── utils/
│   └── week_calc.py           # 주차/날짜 계산 유틸
├── tools/
│   ├── ads_refresh_token.py   # Google Ads Refresh Token 발급 도구
│   ├── save_naver_session.py  # 네이버 로그인 세션 저장 도구
│   └── debug_naver_blog.py    # 블로그 스크래핑 디버깅 도구
├── config.py                  # 환경변수 로드 + 검증 (dataclass)
├── orchestrator.py            # 전체 파이프라인 조율
├── main.py                    # CLI 진입점
├── requirements.txt
├── .env.example               # 환경변수 템플릿
└── .gitignore
```

---

## 7. 에러 처리 정책

| 상황 | 동작 |
|---|---|
| GA4 / Google Ads / 네이버 검색광고 / Lead Gen 수집 실패 | Monday.com 작성 중단. Gmail 에러 알림 발송 |
| **네이버 블로그만 실패** | **나머지 데이터로 Monday.com 정상 작성. 블로그 2개 필드 + N전주대비 빈 칸** |
| 동일 주차 아이템 중복 감지 | Gmail 알림 발송 후 새 아이템 생성 계속 진행 |
| 전주 데이터 없음 (전주대비 계산 불가) | 해당 Status 컬럼 빈 칸으로 처리 |
| 전체 성공 | Monday.com 작성 + Gmail 성공 요약 알림 |
