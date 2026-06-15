"""네이버 블로그 통계 페이지 접근 진단 스크립트 (1회성).

세션 만료 vs URL 변경 여부를 가린다.
- 세션 유효성: 네이버 메인에서 로그인 상태 확인
- 통계 페이지: 이동 후 최종 URL / 타이틀 / 에러문구 확인
"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import load_config

cfg = load_config(skip_groups=["BIVIZ Monday.com", "BIVIZ GA4"])
blog_id = cfg.naver_blog.blog_id
session_path = "naver_session.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=session_path,
                                  viewport={"width": 1280, "height": 1024})
    page = context.new_page()

    # 1) 로그인 상태 확인
    page.goto("https://www.naver.com", timeout=30000)
    page.wait_for_timeout(2000)
    logged_in = page.locator("a.MyView-module__link_login___HpHMW, .link_login").count() == 0
    # 로그인되어 있으면 보통 .MyView-module 로그인 버튼이 없음
    body = page.inner_text("body")[:300]
    print(f"[로그인 추정] 로그인 버튼 없음 = {logged_in}")
    print(f"[naver.com body 발췌] {body!r}")

    # 2) 통계 페이지 접근
    url = f"https://blog.stat.naver.com/blog/visit/cv?blogId={blog_id}"
    page.goto(url, timeout=30000)
    page.wait_for_timeout(3000)
    print(f"\n[통계 요청 URL] {url}")
    print(f"[최종 URL]      {page.url}")
    print(f"[타이틀]        {page.title()}")
    print(f"[본문 발췌]     {page.inner_text('body')[:300]!r}")
    print(f"[weekly 버튼 수] {page.locator('a[data-nclk=\"weekly\"]').count()}")

    # 3) creator-advisor 대안 경로 확인
    ca = "https://creator-advisor.naver.com/"
    page.goto(ca, timeout=30000)
    page.wait_for_timeout(2000)
    print(f"\n[creator-advisor 최종 URL] {page.url}")
    print(f"[creator-advisor 타이틀]   {page.title()}")

    browser.close()
