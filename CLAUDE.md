# Weekly Marketing Report Automation

## 프로젝트 개요
매주 월요일, GA4 + Google Ads + 네이버 검색광고 + 네이버 블로그 + Monday.com에서 전주(월~일) 데이터를 수집하여 Monday.com `[LI] Weekly Report` 보드에 자동 작성하는 Python 프로젝트.

## 코드 컨벤션
- 모든 함수에 **한글 docstring** (설명, Args, Returns)
- 변수명은 직관적 영어
- `print` 대신 `logging` 모듈 (INFO/WARNING/ERROR)
- `datetime.now()` 대신 `datetime.now(ZoneInfo("Asia/Seoul"))` — 항상 KST
- 환경변수 누락 시 시작 시점에 즉시 에러 + 어떤 변수가 빠졌는지 명시

## 디렉토리 구조
```
weekly_report/
├── config.py              # 환경변수 로드 + 검증
├── collectors/
│   ├── __init__.py
│   ├── base.py            # BaseCollector 추상 클래스
│   ├── ga4.py             # GA4Collector
│   ├── google_ads.py      # GoogleAdsCollector
│   ├── naver_ads.py       # NaverAdsCollector
│   ├── naver_blog.py      # NaverBlogCollector (Playwright)
│   └── monday_lead.py     # MondayLeadCollector (7개 보드 합산)
├── writers/
│   ├── __init__.py
│   └── monday_writer.py   # 6단계 업로드 + 전주대비 라벨 계산
├── notifiers/
│   ├── __init__.py
│   └── gmail_notifier.py  # 성공/실패/중복 알림
├── utils/
│   ├── __init__.py
│   └── week_calc.py       # 주차/날짜 계산
├── tools/
│   └── explore_boards.py  # Monday.com 보드 탐색 (1회성, 이미 완료)
├── orchestrator.py        # 중앙 실행 로직
├── main.py                # CLI 진입점
├── requirements.txt
├── .env                   # 환경변수 (git에 올리지 않음)
├── .env.example
├── .gitignore
├── service-account.json   # GA4 서비스 계정 키 (git에 올리지 않음)
├── .github/workflows/weekly_report.yml
└── README.md
```

## BaseCollector 패턴
모든 collector는 이 추상 클래스를 상속한다:
```python
from abc import ABC, abstractmethod

class BaseCollector(ABC):
    @abstractmethod
    def collect(self, start_date: str, end_date: str) -> dict:
        """데이터 수집. 반환: {"필드명": 값} 딕셔너리"""
        pass
```
새 데이터 소스 추가 시 collector 파일만 추가 + orchestrator에 1줄 등록. 기존 코드 수정 불필요.

---

## Monday.com 보드 상세 정보

### [LI] Weekly Report 보드
- **보드 ID:** `1901011628`
- **워크스페이스:** SPH 마케팅 (Closed — API 워크스페이스 목록에 안 나옴. 보드 ID로 직접 접근)

### 그룹 규칙
- 월별 분리. 형식: `"2026 {M}월 주간 KPI"`
- 해당 주 7일 중 더 많은 날이 속한 달의 그룹에 배정
- 해당 월 그룹이 없으면 `create_group`으로 자동 생성
- 최신 주차가 그룹 내 최상단 (create_item 기본 동작이므로 별도 처리 불필요)

### 컬럼 ID 매핑 (검증 완료 — 실제 데이터와 대조함)

**자동 입력 (스크립트가 값 넣음):**
| 컬럼명 | 컬럼 ID | 타입 | 데이터 소스 | JSON 포맷 |
|---|---|---|---|---|
| 아이템명 | (name) | item_name | 자동 생성 | create_item의 item_name 인자 |
| 시작날짜 | `date__1` | date | 해당 주 월요일 | `{"date": "2026-03-30"}` |
| Lead Gen | `numeric1__1` | numbers | 7개 보드 합산 | `2` |
| WAU | `__` | numbers | GA4 totalUsers | `4083` |
| 신청문의 페이지 사용자 | `dup__of_______` | numbers | GA4 /contact activeUsers | `52` |
| G노출수 | `___1` | numbers | Google Ads impressions | `15442` |
| G클릭수 | `___2` | numbers | Google Ads clicks | `403` |
| G광고비 | `dup__of____` | numbers | Google Ads cost (KRW) | `212449` |
| N노출수 | `dup__of_g___4` | numbers | 네이버 검색광고 impCnt | `553716` |
| N클릭수 | `dup__of____3` | numbers | 네이버 검색광고 clkCnt | `763` |
| N광고비 | `dup__of_g___6` | numbers | 네이버 검색광고 salesAmt | `80446` |
| Naver 포스팅수 | `dup__of________` | numbers | 네이버 블로그 (Playwright) | `0` |
| N블로그 조회수 | `dup__of_naver_____` | numbers | 네이버 블로그 (Playwright) | `70` |

**전주대비 Status 컬럼 (스크립트가 계산하여 입력, 4개):**
| 컬럼명 | 컬럼 ID | 비교 대상 | 계산 방법 |
|---|---|---|---|
| 전주대비 | `status` | 전환률 | (신청문의사용자÷WAU) 이번주 vs 전주. UP/Down/SAME |
| 전주대비(GCTR) | `dup__of_____` | Google CTR | (G클릭수÷G노출수) 이번주 vs 전주. UP/Down (동일시 UP) |
| 전주대비(NCTR) | `dup__of_____2` | Naver CTR | (N클릭수÷N노출수) 이번주 vs 전주. UP/Down/SAME |
| N전주대비 | `dup__of_____4` | 블로그 조회수 | 이번주 조회수 vs 전주. UP/Down/SAME |

⚠️ **Status 라벨 대소문자 주의:** 보드 실제 값은 `"UP"`, `"Down"`, `"SAME"` (혼용). JSON: `{"label": "UP"}`

**입력 안 함 (Formula 또는 FB 관련):**
- 전환률 (`formula__1`) — Monday 자체 수식
- G평균CPC 원 (`dup__of_ctr__`) — Monday 자체 수식
- GCTR % (`__2`) — Monday 자체 수식
- N평균CPC 원 (`dup__of_g__cpc__`) — Monday 자체 수식
- NCTR % (`dup__of_ctr__8`) — Monday 자체 수식
- FB포스팅수 (`dup__of_fb____`) — 미사용
- FB 광고비 (`__0`) — 미사용
- FB총도달수 (`__7`) — 미사용
- F전주대비 (`dup__of_n____`) — 미사용

---

## Lead Gen 데이터 구조

**단일 보드가 아닌 7개 보드의 아이템 생성수 합산:**

| 보드명 | 보드 ID |
|---|---|
| [LI] 세미나 자료 신청 | `3126575269` |
| [LI] 세미나 신청 | `3126575612` |
| [LI] 세미나 자료 | `3126577988` |
| [LI] SPH 홈페이지 문의 | `3126579902` |
| [LI] LI뉴스레터 신청 | `3126587413` |
| [LI] 슈퍼맵 자료 신청 | `3190959132` |
| [LI] 구글 인바운드 리드 | `6680201428` |

**카운트 방식:**
- 각 보드의 아이템 조회 → `created_at` 필드로 해당 주 월~일 범위 필터링 → 카운트
- 날짜 컬럼은 `creation_log` 타입이라 API 필터링 불가 → Python에서 `created_at` 값으로 필터
- 7개 보드 카운트 합산 = Lead Gen 숫자

---

## 주차 계산 규칙

- **기준점:** 2026-03-30(월) = 117주차
- **규칙:** 전주 월요일~일요일
- **아이템명 형식:** `{M}월 {W}주차 ({시작 M/DD}~{종료 M/DD}) {N}주차`
  - 예: `"4월 1주차 (3/30~4/05) 117주차"`
- **그룹 배정:** 7일 중 더 많은 날이 속한 달 기준

---

## API 명세

### 1. GA4 (Google Analytics Data API v1beta)
- **인증:** 서비스 계정 JSON 키 (`GOOGLE_APPLICATION_CREDENTIALS`)
- **WAU:** `runReport` → metric `totalUsers`
- **/contact 사용자:** `runReport` → metric `activeUsers`, dimension `pagePath`, filter contains `/contact`
- 날짜 범위는 해당 주 월~일 지정

### 2. Google Ads API
- **인증:** OAuth2
- **계정 구조 (중요!):**
  - 관리자 MCC: `469-262-2227` → `login_customer_id`로 사용 (하이픈 제거: `4692622227`)
  - 운영 계정: `471-784-8584` → `customer_id`로 사용 (하이픈 제거: `4717848584`)
- **쿼리:**
```sql
SELECT metrics.impressions, metrics.clicks, metrics.cost_micros
FROM customer
WHERE segments.date BETWEEN '{start}' AND '{end}'
```
- `cost_micros` ÷ 1,000,000 → 원화 정수로 반올림

### 3. 네이버 검색광고 API
- **인증:** HMAC-SHA256 서명 (X-API-KEY, X-Customer, X-Signature, X-Timestamp)
- **흐름:** `GET /ncc/campaigns` → 캠페인 ID 목록 확보 → `GET /stats` 에서 각 캠페인 통계 조회
- **필드:** `impCnt`(노출수), `clkCnt`(클릭수), `salesAmt`(비용)
- `timeRange` 파라미터로 날짜 범위 지정

### 4. 네이버 블로그 (Playwright 스크래핑)
- 네이버 로그인 → 블로그 통계 페이지 접근
- 포스팅수: 해당 주 작성 게시글 카운트
- 조회수: 통계 > 주간 조회수
- **⚠️ GitHub Actions에서 2단계 인증 실패 가능 → 실패 시 해당 2필드만 None 처리**

### 5. Monday.com API (GraphQL)
- **인증:** API Token (`Authorization` 헤더)
- **⚠️ SPH 마케팅 워크스페이스는 Closed. 보드 ID로 직접 접근.**
- API 호출 간 `time.sleep(1)` 필수 (complexity rate limit)

---

## Monday.com 업로드 6단계 흐름

```
Step 1) boards(ids: [1901011628]) { groups { id title } }
Step 2) 해당 월 그룹 없으면 → create_group (형식: "2026 {M}월 주간 KPI")
Step 3) items_page로 아이템 목록 조회
Step 4) 동일 아이템명 있으면 → Gmail 알림 + 계속 진행 (새 아이템 생성)
Step 5) create_item(board_id, group_id, item_name, column_values)
Step 6) 응답에서 item ID 확인
```

**전주대비 계산:**
- Step 5 전에, 직전 주차 아이템의 관련 컬럼 값 조회
- 이번 주 vs 전주 비교하여 4개 Status 라벨 결정
- 전주 데이터 없거나 비교 불가 → 해당 라벨 입력 안 함 (빈 칸)

---

## 에러 처리 정책

| 상황 | 동작 |
|---|---|
| 필수 collector 실패 (GA4, Google Ads, 네이버 광고, Monday Lead) | Monday.com에 작성하지 않음. Gmail 에러 알림만 발송 |
| **네이버 블로그만 실패** | **예외 — 나머지 데이터로 Monday.com 작성. 블로그 2필드 + N전주대비 라벨은 빈 칸** |
| 중복 주차 감지 | Gmail 알림 + 새 아이템 생성 (중단하지 않음) |
| 전체 성공 | Monday.com 작성 + Gmail 성공 요약 알림 |

---

## Gmail 알림
- **smtplib** + Gmail 앱 비밀번호 사용
- **발송 조건:** (a) 필수 collector 실패, (b) 중복 감지, (c) 성공 완료
- **내용:** 대상 주차, 성공/실패 collector 목록, 데이터 요약

---

## CLI 옵션 (main.py)
```bash
python main.py                    # 전주 데이터 자동 처리
python main.py --date 2026-03-30  # 특정 주 월요일 지정
python main.py --local-blog       # 네이버 블로그만 수집 → 기존 아이템 업데이트
python main.py --dry-run          # 수집만 하고 Monday.com에 안 씀 (테스트용)
```

**--local-blog 모드:**
- NaverBlogCollector만 실행
- Monday.com에서 해당 주차 아이템명으로 검색 → item_id 확인
- `change_multiple_column_values` mutation으로 블로그 2필드 + N전주대비만 업데이트

---

## GitHub Actions 배포
- **스케줄:** 매주 월요일 KST 10:00 (UTC 01:00)
- `workflow_dispatch` 포함 (수동 실행 가능)
- 환경변수는 GitHub Secrets에서 주입
- `service-account.json`은 Secret `GOOGLE_SA_JSON`에 JSON 내용 통째로 저장 → 워크플로우에서 파일로 복원

---

## 환경변수 (.env)
```env
# Monday.com
MONDAY_API_TOKEN=
MONDAY_WEEKLY_BOARD_ID=1901011628
MONDAY_LEAD_BOARD_IDS=3126575269,3126575612,3126577988,3126579902,3126587413,3190959132,6680201428
MONDAY_COL_START_DATE=date__1
MONDAY_COL_LEAD_GEN=numeric1__1
MONDAY_COL_WAU=__
MONDAY_COL_CONTACT_USERS=dup__of_______
MONDAY_COL_G_IMPRESSIONS=___1
MONDAY_COL_G_CLICKS=___2
MONDAY_COL_G_COST=dup__of____
MONDAY_COL_WOW_CONVERSION=status
MONDAY_COL_WOW_GCTR=dup__of_____
MONDAY_COL_N_IMPRESSIONS=dup__of_g___4
MONDAY_COL_N_CLICKS=dup__of____3
MONDAY_COL_N_COST=dup__of_g___6
MONDAY_COL_WOW_NCTR=dup__of_____2
MONDAY_COL_N_BLOG_POSTS=dup__of________
MONDAY_COL_N_BLOG_VIEWS=dup__of_naver_____
MONDAY_COL_WOW_NAVER=dup__of_____4

# GA4
GA4_PROPERTY_ID=
GOOGLE_APPLICATION_CREDENTIALS=./service-account.json

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=4692622227
GOOGLE_ADS_CUSTOMER_ID=4717848584

# 네이버 검색광고
NAVER_ADS_API_KEY=
NAVER_ADS_SECRET_KEY=
NAVER_ADS_CUSTOMER_ID=

# 네이버 블로그
NAVER_LOGIN_ID=
NAVER_LOGIN_PW=
NAVER_BLOG_ID=

# Gmail
GMAIL_SENDER=
GMAIL_APP_PASSWORD=
GMAIL_RECIPIENT=
```

---

## 개발 순서

**각 Phase 완료 후 사용자 확인을 받고 다음으로 넘어간다.**

### Phase 0: 기반 코드
1. `utils/week_calc.py` — 주차 계산, 아이템명/그룹명 생성, 전주대비 비교
2. `config.py` — 환경변수 로드 + dataclass + 시작 시 누락 검증
3. `requirements.txt`
4. `.env.example`, `.gitignore`

### Phase 1: Collector
5. `collectors/base.py` — BaseCollector
6. `collectors/ga4.py` — WAU + /contact 사용자
7. `collectors/google_ads.py` — 노출수, 클릭수, 비용 (MCC 구조)
8. `collectors/naver_ads.py` — 노출수, 클릭수, 비용 (HMAC 인증)
9. `collectors/naver_blog.py` — 포스팅수, 조회수 (Playwright)
10. `collectors/monday_lead.py` — 7개 보드 created_at 필터 합산

### Phase 2: Writer + Notifier
11. `writers/monday_writer.py` — 6단계 흐름 + 전주대비 4개 라벨
12. `notifiers/gmail_notifier.py` — 3종 알림

### Phase 3: Orchestrator + CLI
13. `orchestrator.py` — 파이프라인 조율
14. `main.py` — CLI (기본/--date/--local-blog/--dry-run)

### Phase 4: 배포
15. `.github/workflows/weekly_report.yml`
16. `README.md` (한글 설정 가이드)