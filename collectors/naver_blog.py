"""
네이버 블로그 데이터 수집기
===========================
1. 포스팅 수: #mainFrame iframe → #toplistSpanBlind 버튼으로 목록 펼침
             → #toplistWrapper tbody tr 날짜 비교 카운트
2. 조회수: blog.stat.naver.com 직접 접속 → 주간 버튼 클릭
           → th[scope="row"] 기간 매칭 → 전체 td 값 반환
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
        """#mainFrame iframe 내 목록 테이블에서 해당 기간의 포스팅 수를 센다.

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

        # page.wait_for_load_state()는 바깥 페이지 기준 → iframe은 아직 로딩 중일 수 있음
        # mainFrame iframe 자체의 networkidle을 명시적으로 대기
        try:
            page.wait_for_selector("#mainFrame", timeout=15000)
            main_frame_obj = next(
                (f for f in page.frames if self.blog_id in f.url and f.url != url),
                None,
            )
            if main_frame_obj:
                main_frame_obj.wait_for_load_state("networkidle", timeout=15000)
                self.logger.debug(f"mainFrame 로딩 완료: {main_frame_obj.url}")
        except PlaywrightTimeout:
            self.logger.warning("mainFrame 로딩 타임아웃, 계속 진행합니다.")
        except Exception as e:
            self.logger.warning(f"mainFrame 대기 중 오류 (무시): {e}")

        frame = page.frame_locator("#mainFrame")

        # 목록열기 상태면 클릭하여 테이블 펼침
        # 실제 HTML: <span class="txt" id="toplistSpanBlind">목록열기</span>
        try:
            list_btn = frame.locator("#toplistSpanBlind")
            list_btn.wait_for(state="visible", timeout=10000)
            if "열기" in list_btn.inner_text(timeout=5000):
                list_btn.click()
                page.wait_for_timeout(1500)
        except PlaywrightTimeout:
            self.logger.warning("#toplistSpanBlind을 찾을 수 없습니다. 목록 테이블 직접 탐색합니다.")
        except Exception as e:
            self.logger.warning(f"목록 버튼 처리 중 오류 (무시): {e}")

        # #toplistWrapper tbody에서 포스팅 행(tr_tag 제외) 순회
        # 날짜: <td class="date"><span class="date pcol2">2026. 4. 6.</span>
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        count = 0

        try:
            frame.locator("#toplistWrapper").wait_for(state="visible", timeout=8000)
            rows = frame.locator("#toplistWrapper tbody tr:not(.tr_tag)").all()
            self.logger.debug(f"목록 테이블 {len(rows)}개 행 탐색.")

            for row in rows:
                try:
                    date_el = row.locator("td.date span.date")
                    if date_el.count() == 0:
                        continue
                    date_text = date_el.first.inner_text(timeout=3000).strip()
                    m = re.search(
                        r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", date_text
                    )
                    if not m:
                        continue
                    post_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if start_dt <= post_date <= end_dt:
                        count += 1
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"포스팅 목록 탐색 실패: {e}")

        self.logger.info(f"포스팅 수: {count}건 ({start_date} ~ {end_date})")
        return count

    def _get_views(self, page, start_date: str, end_date: str) -> int:
        """admin 통계 페이지에서 해당 주의 '전체' 조회수를 가져온다.

        blog.stat.naver.com 직접 접속으로 iframe 동기화 문제를 우회한다.
        테이블 날짜 형식: "03.30. ~ 04.05."

        Args:
            page: Playwright Page 객체.
            start_date: 조회 시작일 "YYYY-MM-DD".
            end_date: 조회 종료일 "YYYY-MM-DD".

        Returns:
            주간 조회수 정수. 실패 시 0.
        """
        url = f"https://blog.stat.naver.com/blog/visit/cv?blogId={self.blog_id}"
        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except PlaywrightTimeout:
            self.logger.warning("통계 페이지 로딩 타임아웃, 계속 진행합니다.")

        try:
            weekly_btn = page.locator('a[data-nclk="weekly"]')
            weekly_btn.wait_for(state="visible", timeout=15000)
            weekly_btn.click()

            # stats 테이블 고유 셀렉터: th[scope="row"]
            # (React datepicker의 <tr class="react-datepicker__week">와 구분)
            page.locator("th[scope='row']").first.wait_for(state="visible", timeout=15000)

            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            target_range = f"{start_dt.strftime('%m.%d.')} ~ {end_dt.strftime('%m.%d.')}"

            for row in page.locator("tr:has(th[scope='row'])").all():
                try:
                    th = row.locator("th[scope='row']")
                    if target_range in th.inner_text(timeout=3000).strip():
                        views_text = row.locator("td").first.inner_text(timeout=3000).strip()
                        view_count = int(re.sub(r"[^0-9]", "", views_text))
                        self.logger.info(f"조회수: {view_count}건 ({target_range})")
                        return view_count
                except Exception:
                    continue

            self.logger.error(f"조회수 테이블에서 '{target_range}' 행을 찾지 못했습니다.")
            try:
                actual = [th.inner_text(timeout=1000).strip()
                          for th in page.locator("th[scope='row']").all()]
                self.logger.error(f"테이블 기간 목록: {actual}")
            except Exception:
                pass
            page.screenshot(path="debug_stats_error.png")
            return 0

        except Exception as e:
            self.logger.error(f"조회수 수집 실패: {e}")
            page.screenshot(path="debug_stats_error.png")
            return 0
