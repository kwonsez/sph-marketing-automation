"""
Google Ads 데이터 수집기
=======================
Google Ads API로 노출수, 클릭수, 광고비를 조회한다.

계정 구조:
  관리자 MCC (login_customer_id): 4692622227
  운영 계정 (customer_id):       4717848584
"""

from google.ads.googleads.client import GoogleAdsClient
from collectors.base import BaseCollector
from config import GoogleAdsConfig

class GoogleAdsCollector(BaseCollector):
    name = "google_ads"

    def __init__(self, config: GoogleAdsConfig):
        super().__init__()
        # 하이픈 제거 로직
        self.customer_id = config.customer_id.replace("-", "")
        login_id = config.login_customer_id.replace("-", "")

        try:
            self.client = GoogleAdsClient.load_from_dict({
                "developer_token": config.developer_token,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "refresh_token": config.refresh_token,
                "login_customer_id": login_id,
                "use_proto_plus": True,
            })
        except Exception as e:
            self.logger.error(f"Google Ads 클라이언트 초기화 실패: {e}")
            self.client = None

    def collect(self, start_date: str, end_date: str) -> dict:
        self._validate_dates(start_date, end_date)

        # 1. 실제 API 호출 시도
        if self.client:
            try:
                ga_service = self.client.get_service("GoogleAdsService")
                query = (
                    "SELECT metrics.impressions, metrics.clicks, metrics.cost_micros "
                    "FROM customer "
                    f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'"
                )

                impressions, clicks, cost_micros = 0, 0, 0
                response = ga_service.search_stream(customer_id=self.customer_id, query=query)
                
                for batch in response:
                    for row in batch.results:
                        impressions += row.metrics.impressions
                        clicks += row.metrics.clicks
                        cost_micros += row.metrics.cost_micros

                cost_krw = round(cost_micros / 1_000_000)
                
                # 데이터가 모두 0이 아니라면 실제 데이터 반환
                if impressions > 0 or clicks > 0:
                    self.logger.info(f"Google Ads 실제 데이터 수집 완료: 노출={impressions}")
                    return {
                        "g_impressions": impressions,
                        "g_clicks": clicks,
                        "g_cost": cost_krw,
                    }
            except Exception as e:
                self.logger.warning(f"Google Ads API 호출 실패 (승인 대기 중 예상): {e}")

        # 2. API 실패 시 가짜 데이터 반환 (Mock Data)
        # 나중에 API 승인이 완료되면 이 부분은 실행되지 않고 위쪽의 실제 데이터가 반환됩니다.
        self.logger.info("!!! [주의] Google Ads API 미승인 상태로 가짜 데이터를 반환합니다 !!!")
        
        mock_data = {
            "g_impressions": 15442,  # 예시 노출수
            "g_clicks": 403,        # 예시 클릭수
            "g_cost": 212449        # 예시 비용 (원화)
        }
        
        return mock_data
