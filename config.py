"""
환경변수 로드 및 검증
====================
스크립트 시작 시 필요한 환경변수가 모두 설정되었는지 확인한다.
누락된 변수가 있으면 즉시 에러를 발생시킨다.
"""

import os
import sys
import logging
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# 필수 환경변수 정의
# ============================================================

REQUIRED_ENV_GROUPS = {
    "Monday.com 기본": [
        "MONDAY_API_TOKEN",
        "MONDAY_WEEKLY_BOARD_ID",
        "MONDAY_LEAD_BOARD_IDS",
    ],
    "Monday.com 컬럼 매핑": [
        "MONDAY_COL_START_DATE",
        "MONDAY_COL_LEAD_GEN",
        "MONDAY_COL_WAU",
        "MONDAY_COL_CONTACT_USERS",
        "MONDAY_COL_G_IMPRESSIONS",
        "MONDAY_COL_G_CLICKS",
        "MONDAY_COL_G_COST",
        "MONDAY_COL_WOW_CONVERSION",
        "MONDAY_COL_WOW_GCTR",
        "MONDAY_COL_N_IMPRESSIONS",
        "MONDAY_COL_N_CLICKS",
        "MONDAY_COL_N_COST",
        "MONDAY_COL_WOW_NCTR",
        "MONDAY_COL_N_BLOG_POSTS",
        "MONDAY_COL_N_BLOG_VIEWS",
        "MONDAY_COL_WOW_NAVER",
    ],
    "BIVIZ Monday.com": [
        "MONDAY_BIVIZ_BOARD_ID",
        "MONDAY_BIVIZ_LEAD_BOARD_IDS",
        "MONDAY_BIVIZ_COL_START_DATE",
        "MONDAY_BIVIZ_COL_LEAD_GEN",
        "MONDAY_BIVIZ_COL_WAU",
        "MONDAY_BIVIZ_COL_CONTACT_USERS",
        "MONDAY_BIVIZ_COL_WOW_CONVERSION",
    ],
    "GA4": [
        "GA4_PROPERTY_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ],
    "BIVIZ GA4": [
        "BIVIZ_GA4_PROPERTY_ID",
        "BIVIZ_CONTACT_PATH",
    ],
    "Google Ads": [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        "GOOGLE_ADS_CUSTOMER_ID",
    ],
    "네이버 검색광고": [
        "NAVER_ADS_API_KEY",
        "NAVER_ADS_SECRET_KEY",
        "NAVER_ADS_CUSTOMER_ID",
    ],
    "네이버 블로그": [
        "NAVER_LOGIN_ID",
        "NAVER_LOGIN_PW",
        "NAVER_BLOG_ID",
    ],
    "Gmail 알림": [
        "GMAIL_SENDER",
        "GMAIL_APP_PASSWORD",
        "GMAIL_RECIPIENT",
    ],
}


# ============================================================
# Config 데이터 클래스
# ============================================================

@dataclass
class MondayConfig:
    """Monday.com 관련 설정"""
    api_token: str = ""
    weekly_board_id: str = ""
    lead_board_ids: list[str] = field(default_factory=list)
    # 컬럼 ID 매핑
    col_start_date: str = ""
    col_lead_gen: str = ""
    col_wau: str = ""
    col_contact_users: str = ""
    col_g_impressions: str = ""
    col_g_clicks: str = ""
    col_g_cost: str = ""
    col_wow_conversion: str = ""
    col_wow_gctr: str = ""
    col_n_impressions: str = ""
    col_n_clicks: str = ""
    col_n_cost: str = ""
    col_wow_nctr: str = ""
    col_n_blog_posts: str = ""
    col_n_blog_views: str = ""
    col_wow_naver: str = ""


@dataclass
class GA4Config:
    """GA4 관련 설정"""
    property_id: str = ""
    credentials_path: str = ""
    contact_path: str = "/contact"


@dataclass
class GoogleAdsConfig:
    """Google Ads 관련 설정"""
    developer_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    login_customer_id: str = ""
    customer_id: str = ""


@dataclass
class NaverAdsConfig:
    """네이버 검색광고 관련 설정"""
    api_key: str = ""
    secret_key: str = ""
    customer_id: str = ""


@dataclass
class NaverBlogConfig:
    """네이버 블로그 관련 설정"""
    login_id: str = ""
    login_pw: str = ""
    blog_id: str = ""


@dataclass
class GmailConfig:
    """Gmail 알림 관련 설정"""
    sender: str = ""
    app_password: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class ReportProfile:
    """단일 리포트(SPH 또는 BIVIZ)에 필요한 보드/GA4/사용 collector 설정 묶음"""
    name: str  # 로그/메일 제목에 표시 ("SPH" 또는 "BIVIZ")
    monday: MondayConfig = field(default_factory=MondayConfig)
    ga4: GA4Config = field(default_factory=GA4Config)
    use_google_ads: bool = False
    use_naver_ads: bool = False
    use_naver_blog: bool = False


@dataclass
class AppConfig:
    """전체 애플리케이션 설정을 담는 최상위 설정 클래스"""
    sph: ReportProfile = field(default_factory=lambda: ReportProfile(name="SPH"))
    biviz: ReportProfile = field(default_factory=lambda: ReportProfile(name="BIVIZ"))
    google_ads: GoogleAdsConfig = field(default_factory=GoogleAdsConfig)
    naver_ads: NaverAdsConfig = field(default_factory=NaverAdsConfig)
    naver_blog: NaverBlogConfig = field(default_factory=NaverBlogConfig)
    gmail: GmailConfig = field(default_factory=GmailConfig)

    def get_profile(self, name: str) -> ReportProfile:
        """이름으로 프로필 반환. 'sph' 또는 'biviz'."""
        if name.lower() == "biviz":
            return self.biviz
        return self.sph


# ============================================================
# 환경변수 검증 및 로드
# ============================================================

def validate_env_vars(skip_groups: list[str] = None) -> list[str]:
    """환경변수 누락 여부를 검증한다.

    Args:
        skip_groups: 검증을 건너뛸 그룹명 리스트.
                     예: ["네이버 블로그"] → --local-blog 아닐 때 스킵 가능

    Returns:
        누락된 환경변수 이름 리스트. 비어있으면 모두 정상.
    """
    skip = set(skip_groups or [])
    missing = []

    for group_name, var_names in REQUIRED_ENV_GROUPS.items():
        if group_name in skip:
            continue
        for var in var_names:
            if not os.getenv(var):
                missing.append(f"  [{group_name}] {var}")

    return missing


def load_config(skip_groups: list[str] = None) -> AppConfig:
    """환경변수를 검증하고, AppConfig 객체로 로드한다.

    Args:
        skip_groups: 검증을 건너뛸 그룹명 리스트.

    Returns:
        AppConfig 인스턴스.

    Raises:
        SystemExit: 필수 환경변수가 누락된 경우.
    """
    missing = validate_env_vars(skip_groups)
    if missing:
        logger.error("필수 환경변수가 누락되었습니다:")
        for m in missing:
            logger.error(m)
        logger.error("")
        logger.error(".env.example 파일을 참고하여 .env 파일을 작성하세요.")
        sys.exit(1)

    # MONDAY_LEAD_BOARD_IDS: 콤마 구분 문자열 → 리스트
    lead_ids_raw = os.getenv("MONDAY_LEAD_BOARD_IDS", "")
    lead_board_ids = [bid.strip() for bid in lead_ids_raw.split(",") if bid.strip()]

    biviz_lead_ids_raw = os.getenv("MONDAY_BIVIZ_LEAD_BOARD_IDS", "")
    biviz_lead_board_ids = [bid.strip() for bid in biviz_lead_ids_raw.split(",") if bid.strip()]

    # GMAIL_RECIPIENT: 콤마 구분 문자열 → 리스트 (여러 명에게 발송 가능)
    recipients_raw = os.getenv("GMAIL_RECIPIENT", "")
    gmail_recipients = [addr.strip() for addr in recipients_raw.split(",") if addr.strip()]

    api_token = os.getenv("MONDAY_API_TOKEN", "")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    sph_profile = ReportProfile(
        name="SPH",
        monday=MondayConfig(
            api_token=api_token,
            weekly_board_id=os.getenv("MONDAY_WEEKLY_BOARD_ID", ""),
            lead_board_ids=lead_board_ids,
            col_start_date=os.getenv("MONDAY_COL_START_DATE", ""),
            col_lead_gen=os.getenv("MONDAY_COL_LEAD_GEN", ""),
            col_wau=os.getenv("MONDAY_COL_WAU", ""),
            col_contact_users=os.getenv("MONDAY_COL_CONTACT_USERS", ""),
            col_g_impressions=os.getenv("MONDAY_COL_G_IMPRESSIONS", ""),
            col_g_clicks=os.getenv("MONDAY_COL_G_CLICKS", ""),
            col_g_cost=os.getenv("MONDAY_COL_G_COST", ""),
            col_wow_conversion=os.getenv("MONDAY_COL_WOW_CONVERSION", ""),
            col_wow_gctr=os.getenv("MONDAY_COL_WOW_GCTR", ""),
            col_n_impressions=os.getenv("MONDAY_COL_N_IMPRESSIONS", ""),
            col_n_clicks=os.getenv("MONDAY_COL_N_CLICKS", ""),
            col_n_cost=os.getenv("MONDAY_COL_N_COST", ""),
            col_wow_nctr=os.getenv("MONDAY_COL_WOW_NCTR", ""),
            col_n_blog_posts=os.getenv("MONDAY_COL_N_BLOG_POSTS", ""),
            col_n_blog_views=os.getenv("MONDAY_COL_N_BLOG_VIEWS", ""),
            col_wow_naver=os.getenv("MONDAY_COL_WOW_NAVER", ""),
        ),
        ga4=GA4Config(
            property_id=os.getenv("GA4_PROPERTY_ID", ""),
            credentials_path=credentials_path,
            contact_path=os.getenv("CONTACT_PATH", "/contact"),
        ),
        use_google_ads=True,
        use_naver_ads=True,
        use_naver_blog=True,
    )

    biviz_profile = ReportProfile(
        name="BIVIZ",
        monday=MondayConfig(
            api_token=api_token,
            weekly_board_id=os.getenv("MONDAY_BIVIZ_BOARD_ID", ""),
            lead_board_ids=biviz_lead_board_ids,
            col_start_date=os.getenv("MONDAY_BIVIZ_COL_START_DATE", ""),
            col_lead_gen=os.getenv("MONDAY_BIVIZ_COL_LEAD_GEN", ""),
            col_wau=os.getenv("MONDAY_BIVIZ_COL_WAU", ""),
            col_contact_users=os.getenv("MONDAY_BIVIZ_COL_CONTACT_USERS", ""),
            col_wow_conversion=os.getenv("MONDAY_BIVIZ_COL_WOW_CONVERSION", ""),
            # 광고/블로그 컬럼은 BIVIZ에서 사용 안 함 → 빈 문자열 유지
        ),
        ga4=GA4Config(
            property_id=os.getenv("BIVIZ_GA4_PROPERTY_ID", ""),
            credentials_path=credentials_path,
            contact_path=os.getenv("BIVIZ_CONTACT_PATH", "/contact"),
        ),
        use_google_ads=False,
        use_naver_ads=False,
        use_naver_blog=False,
    )

    config = AppConfig(
        sph=sph_profile,
        biviz=biviz_profile,
        google_ads=GoogleAdsConfig(
            developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            client_id=os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
            login_customer_id=os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
            customer_id=os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
        ),
        naver_ads=NaverAdsConfig(
            api_key=os.getenv("NAVER_ADS_API_KEY", ""),
            secret_key=os.getenv("NAVER_ADS_SECRET_KEY", ""),
            customer_id=os.getenv("NAVER_ADS_CUSTOMER_ID", ""),
        ),
        naver_blog=NaverBlogConfig(
            login_id=os.getenv("NAVER_LOGIN_ID", ""),
            login_pw=os.getenv("NAVER_LOGIN_PW", ""),
            blog_id=os.getenv("NAVER_BLOG_ID", ""),
        ),
        gmail=GmailConfig(
            sender=os.getenv("GMAIL_SENDER", ""),
            app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
            recipients=gmail_recipients,
        ),
    )

    logger.info("환경변수 로드 완료")
    return config


# ============================================================
# 직접 실행 시 검증 테스트
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("환경변수 검증 중...")
    missing = validate_env_vars()
    if missing:
        print(f"\n누락된 환경변수 {len(missing)}개:")
        for m in missing:
            print(m)
    else:
        print("모든 환경변수가 설정되어 있습니다.")
        config = load_config()
        print(f"  [SPH]   Monday 보드: {config.sph.monday.weekly_board_id}, "
              f"Lead 보드 {len(config.sph.monday.lead_board_ids)}개, "
              f"GA4 {config.sph.ga4.property_id}")
        print(f"  [BIVIZ] Monday 보드: {config.biviz.monday.weekly_board_id}, "
              f"Lead 보드 {len(config.biviz.monday.lead_board_ids)}개, "
              f"GA4 {config.biviz.ga4.property_id}")
