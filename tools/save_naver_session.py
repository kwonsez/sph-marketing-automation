# tools/save_naver_session.py
from playwright.sync_api import sync_playwright

def save_session():
    with sync_playwright() as p:
        # headless=False로 브라우저를 실제로 띄웁니다.
        browser = p.chromium.launch(headless=False)
        # 세션 정보를 저장할 컨텍스트 생성
        context = browser.new_context()
        page = context.new_page()
        
        print("네이버 로그인 페이지로 이동합니다...")
        page.goto("https://nid.naver.com/nidlogin.login")
        
        print("직접 로그인을 완료하고 2단계 인증까지 마쳐주세요.")
        print("로그인이 완료되어 블로그 홈 화면이 보이면 이 터미널에서 Enter를 누르세요.")
        input()
        
        # 세션 상태 저장
        context.storage_state(path="naver_session.json")
        print("세션 정보가 'naver_session.json'에 저장되었습니다.")
        browser.close()

if __name__ == "__main__":
    save_session()