"""
네이버 블로그 데이터 수집기
===========================
1. 포스팅 수: #mainFrame 아이프레임 내 #toplistSpanBlind 버튼으로 목록 펼친 후
             tr[id^="topListRow"] 행의 .date.pcol2 날짜로 기간 내 카운트
2. 조회수: admin 통계 페이지 주간 버튼 클릭 → 테이블에서 해당 주 행의 '전체' td 값 추출
"""

import os
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from collectors.base import BaseCollector, NaverBlogError
from config import NaverBlogConfig


class NaverBlogCollector(BaseCollector):
    """네이버 블로그 포스팅 수 및 주간 조회수 수집기."""

    name = "naver_blog"

    def __init__(self, config: NaverBlogConfig):
        super().__init__()
        self.blog_id = config.blog_id
        self.session_path = "naver_session.json"

    def collect(self, start_date: str, end_date: str) -> dict:
        """포스팅 수와 주간 조회수를 수집한다.

        Args:
            start_date: 조회 시작일 "YYYY-MM-DD".
            end_date: 조회 종료일 "YYYY-MM-DD".

        Returns:
            {"n_blog_posts": int, "n_blog_views": int}
        """
        self._validate_dates(start_date, end_date)
        try:
            return self._scrape(start_date, end_date)
        except NaverBlogError:
            raise
        except Exception as e:
            raise NaverBlogError(f"네이버 블로그 수집 중 예외 발생: {e}") from e

    def _scrape(self, start_date: str, end_date: str) -> dict:
        if not os.path.exists(self.session_path):
            raise NaverBlogError(
                "세션 파일이 없습니다. tools/save_naver_session.py를 실행하세요."
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=self.session_path,
                viewport={"width": 1280, "height": 1024},
            )
            page = context.new_page()
            try:
                post_count = self._count_posts(page, start_date, end_date)
                view_count = self._get_views(page, start_date, end_date)
            finally:
                browser.close()

        self.logger.info(f"블로그 수집 완료: 포스팅={post_count}, 조회={view_count}")
        return {"n_blog_posts": post_count, "n_blog_views": view_count}

    def _count_posts(self, page, start_date: str, end_date: str) -> int:
        """#mainFrame 아이프레임 내 목록 테이블에서 해당 기간의 포스팅 수를 센다.

        흐름: 블로그 메인 접속 → #mainFrame 전환 → #toplistSpanBlind 버튼으로 목록 펼치기
              → tr[id^="topListRow"] 순회 → .date.pcol2 날짜 추출 → 범위 비교 카운트

        Args:
            page: Playwright Page 객체.
            start_date: 조회 시작일 "YYYY-MM-DD".
            end_date: 조회 종료일 "YYYY-MM-DD".

        Returns:
            해당 기간에 작성된 포스팅 수.
        """
        url = f"https://blog.naver.com/{self.blog_id}"
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except PlaywrightTimeout:
            self.logger.warning("블로그 메인 페이지 로딩 타임아웃, 계속 진행합니다.")

        # #mainFrame 아이프레임으로 컨텍스트 전환
        frame = page.frame_locator("#mainFrame")

        # 목록열기/닫기 버튼 확인 — '목록열기' 상태면 클릭하여 테이블을 펼침
        # 실제 HTML: <span class="txt" id="toplistSpanBlind">목록열기</span>
        try:
            list_btn = frame.locator("#toplistSpanBlind")
            list_btn.wait_for(state="visible", timeout=10000)
            btn_text = list_btn.inner_text(timeout=5000).strip()
            if "열기" in btn_text:
                list_btn.click()
                page.wait_for_timeout(1500)
                self.logger.info("목록열기 버튼 클릭 완료.")
            else:
                self.logger.info("목록은 이미 펼쳐진 상태입니다.")
        except PlaywrightTimeout:
            self.logger.warning("#toplistSpanBlind을 찾을 수 없습니다. 목록 테이블 직접 탐색합니다.")
        except Exception as e:
            self.logger.warning(f"목록 버튼 처리 중 오류 (무시): {e}")

        # #toplistWrapper가 나타날 때까지 대기 후 tbody 행 순회
        # 실제 DOM: <div id="toplistWrapper"><table><tbody><tr class=""><td class="date">
        #           <span class="date pcol2">2026. 4. 6.</span>
        # tr_tag 클래스는 태그 행(스킵 대상), 날짜는 td.date > span.date.pcol2 에 있음
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        count = 0

        try:
            frame.locator("#toplistWrapper").wait_for(state="visible", timeout=8000)
            # tr_tag 행(태그 표시 행)을 제외한 실제 포스팅 행만 선택
            rows = frame.locator("#toplistWrapper tbody tr:not(.tr_tag)").all()
            self.logger.info(f"목록 테이블에서 {len(rows)}개 포스팅 행 발견.")

            for row in rows:
                try:
                    date_el = row.locator("td.date span.date")
                    if date_el.count() == 0:
                        continue
                    date_text = date_el.first.inner_text(timeout=3000).strip()
                    # "2026. 4. 6." 형식 파싱
                    m = re.search(
                        r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", date_text
                    )
                    if not m:
                        continue
                    post_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if start_dt <= post_date <= end_dt:
                        count += 1
                        self.logger.info(f"범위 내 포스팅 발견: {date_text}")
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"포스팅 목록 탐색 실패: {e}")

        self.logger.info(f"포스팅 수 집계 완료: {count}건")
        return count

    def _get_views(self, page, start_date: str, end_date: str) -> int:
        """관리자 통계 페이지에서 해당 주의 '전체' 조회수를 가져온다.

        흐름: admin 통계 페이지 접속 → a[data-nclk="weekly"] 클릭
              → 테이블 tbody tr 순회 → th[scope="row"] 텍스트로 해당 주 행 매칭
              → 첫 번째 td (전체 열) 숫자 반환

        테이블 날짜 형식 예: "03.30. ~ 04.05."
        start_date 2026-03-30 → "03.30.", end_date 2026-04-05 → "04.05."

        Args:
            page: Playwright Page 객체.
            start_date: 조회 시작일 "YYYY-MM-DD".
            end_date: 조회 종료일 "YYYY-MM-DD".

        Returns:
            주간 조회수 정수. 실패 시 0.
        """
        # admin shell의 #statmain iframe을 거치지 않고 컨텐츠 URL에 직접 접속
        # → iframe 동기화 문제 없음, 세션 쿠키가 blog.stat.naver.com에도 적용되면 동작
        url = f"https://blog.stat.naver.com/blog/visit/cv?blogId={self.blog_id}"
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except PlaywrightTimeout:
            self.logger.warning("통계 페이지 로딩 타임아웃, 계속 진행합니다.")

        self.logger.info(f"통계 페이지 현재 URL: {page.url}")

        try:
            # 주간 버튼 클릭
            weekly_btn = page.locator('a[data-nclk="weekly"]')
            weekly_btn.wait_for(state="visible", timeout=15000)
            weekly_btn.click()
            self.logger.info("주간 통계 버튼 클릭.")

            # 클릭 후 stats 테이블 행 대기
            # 주의: 페이지에 React datepicker가 있어 "table tbody tr" 을 쓰면
            #       datepicker의 숨겨진 <tr class="react-datepicker__week"> 를 먼저 잡음.
            # stats 테이블 행만 갖는 고유 셀렉터: th[scope="row"] (datepicker에는 없음)
            page.locator("th[scope='row']").first.wait_for(state="visible", timeout=15000)

            # 해당 주차 행 매칭 레이블 생성
            # 예: start_date=2026-03-30 → "03.30.", end_date=2026-04-05 → "04.05."
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_label = start_dt.strftime("%m.%d.")  # "03.30."
            end_label = end_dt.strftime("%m.%d.")      # "04.05."
            target_range = f"{start_label} ~ {end_label}"
            self.logger.info(f"조회수 테이블에서 '{target_range}' 행 탐색.")

            # th[scope="row"] 를 가진 행만 순회 (stats 테이블 행만 해당)
            rows = page.locator("tr:has(th[scope='row'])").all()
            self.logger.info(f"통계 테이블에서 {len(rows)}개 행 발견.")

            for row in rows:
                try:
                    th = row.locator("th[scope='row']")
                    th_text = th.inner_text(timeout=3000).strip()
                    if target_range in th_text:
                        # 첫 번째 td = '전체' 열
                        td = row.locator("td").first
                        views_text = td.inner_text(timeout=3000).strip()
                        view_count = int(re.sub(r"[^0-9]", "", views_text))
                        self.logger.info(
                            f"'{th_text}' 행 매칭 — 전체 조회수: {view_count}"
                        )
                        return view_count
                except Exception:
                    continue

            # 매칭 실패 시 — 실제 테이블 내용을 로그에 남겨 디버깅 지원
            self.logger.error(f"테이블에서 '{target_range}'에 해당하는 행을 찾지 못했습니다.")
            try:
                all_th = page.locator("th[scope='row']").all()
                actual_ranges = [th.inner_text(timeout=1000).strip() for th in all_th]
                self.logger.error(f"테이블에 있는 기간 목록: {actual_ranges}")
            except Exception:
                pass
            page.screenshot(path="debug_stats_error.png")
            return 0

        except Exception as e:
            self.logger.error(f"조회수 수집 실패: {e}")
            page.screenshot(path="debug_stats_error.png")
            return 0
