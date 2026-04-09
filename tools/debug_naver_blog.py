"""
네이버 블로그 수집 디버그 스크립트
===================================
실행: python tools/debug_naver_blog.py
출력: debug_*.png 스크린샷 + debug_*.html 파일
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright

BLOG_ID = os.getenv("NAVER_BLOG_ID", "")  # .env에서 자동 로드되거나 직접 입력
SESSION = "naver_session.json"

if not BLOG_ID:
    from dotenv import load_dotenv
    load_dotenv()
    BLOG_ID = os.getenv("NAVER_BLOG_ID", "")

assert BLOG_ID, "NAVER_BLOG_ID 환경변수를 설정하세요."
assert os.path.exists(SESSION), f"{SESSION} 파일이 없습니다."

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # 눈으로 확인하려면 headless=False
    context = browser.new_context(
        storage_state=SESSION,
        viewport={"width": 1280, "height": 1024},
    )
    page = context.new_page()

    # ── 1. 블로그 메인 ────────────────────────────────────────────
    print("=== [1] 블로그 메인 접속 ===")
    page.goto(f"https://blog.naver.com/{BLOG_ID}")
    page.wait_for_load_state("networkidle", timeout=30000)
    page.screenshot(path="debug_blog_main.png", full_page=True)
    print("  → debug_blog_main.png 저장")

    # iframe 존재 여부
    frame_el = page.query_selector("#mainFrame")
    print(f"  → #mainFrame iframe 존재: {frame_el is not None}")

    if frame_el:
        frame = page.frame_locator("#mainFrame")

        # toplistSpanBlind 버튼
        btn = frame.locator("#toplistSpanBlind")
        try:
            btn.wait_for(state="visible", timeout=8000)
            print(f"  → #toplistSpanBlind 텍스트: {btn.inner_text()!r}")
            btn.click()
            page.wait_for_timeout(2000)
            page.screenshot(path="debug_blog_after_click.png", full_page=True)
            print("  → 클릭 후 debug_blog_after_click.png 저장")
        except Exception as e:
            print(f"  → #toplistSpanBlind 오류: {e}")

        # iframe 내부 HTML 저장
        try:
            frame_content = page.frames[1].content() if len(page.frames) > 1 else ""
            with open("debug_iframe_content.html", "w", encoding="utf-8") as f:
                f.write(frame_content)
            print("  → debug_iframe_content.html 저장 (iframe 전체 HTML)")
        except Exception as e:
            print(f"  → iframe HTML 저장 실패: {e}")

        # tr[id^='topListRow'] 개수
        try:
            rows = frame.locator("tr[id^='topListRow']").all()
            print(f"  → tr[id^='topListRow'] 행 수: {len(rows)}")
            if rows:
                print(f"     첫 번째 행 HTML: {rows[0].inner_html()[:300]}")
        except Exception as e:
            print(f"  → 행 탐색 오류: {e}")

    # ── 2. admin 통계 페이지 ──────────────────────────────────────
    print("\n=== [2] admin 통계 페이지 접속 ===")
    page.goto(f"https://admin.blog.naver.com/{BLOG_ID}/stat/visit_pv")
    page.wait_for_load_state("networkidle", timeout=30000)
    page.screenshot(path="debug_admin_stat.png", full_page=True)
    print(f"  → 현재 URL: {page.url}")
    print("  → debug_admin_stat.png 저장")

    # iframe 존재 여부 (admin도 iframe 구조일 수 있음)
    admin_frames = page.frames
    print(f"  → 현재 프레임 수: {len(admin_frames)}")
    for i, f in enumerate(admin_frames):
        print(f"     frame[{i}] url: {f.url}")

    # a[data-nclk="weekly"] 탐색 — page + 모든 frame
    found = False
    for i, f in enumerate(admin_frames):
        els = f.query_selector_all('a[data-nclk="weekly"]')
        if els:
            print(f"  → frame[{i}]에서 a[data-nclk='weekly'] {len(els)}개 발견!")
            found = True
    if not found:
        print("  → a[data-nclk='weekly']를 어느 프레임에서도 찾지 못했습니다.")

    # admin 페이지 전체 HTML 저장
    with open("debug_admin_stat.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("  → debug_admin_stat.html 저장 (admin 페이지 HTML)")

    browser.close()

print("\n완료. debug_*.png / debug_*.html 파일을 확인하세요.")
