# get_refresh_token.py
import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

# .env 파일 로드
load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
SCOPES = ["https://www.googleapis.com/auth/adwords"]

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("에러: .env 파일에서 GOOGLE_ADS_CLIENT_ID 또는 GOOGLE_ADS_CLIENT_SECRET을 찾을 수 없습니다.")
        return

    print(f"사용 중인 Client ID: {CLIENT_ID[:10]}...") # 앞부분 일부 출력해서 확인용

    try:
        flow = InstalledAppFlow.from_client_config(
            {
                "web" if ".apps.googleusercontent.com" in CLIENT_ID else "installed": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
        )

        # 브라우저 열기
        credentials = flow.run_local_server(port=0)

        print("\n" + "="*50)
        print("인증 성공!")
        print(f"새로운 REFRESH_TOKEN: {credentials.refresh_token}")
        print("="*50)
        print("\n이 값을 .env의 GOOGLE_ADS_REFRESH_TOKEN에 넣으세요.")
        
    except Exception as e:
        print(f"\n오류 발생: {e}")
        print("\n[체크리스트]")
        print("1. .env 파일에 Client ID와 Secret 끝에 공백(스페이스)이 있는지 확인하세요.")
        print("2. Google Cloud의 '클라이언트' 메뉴에서 ID가 삭제되지 않았는지 확인하세요.")

if __name__ == "__main__":
    main()