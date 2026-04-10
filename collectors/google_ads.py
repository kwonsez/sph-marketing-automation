"""
Google Ads 데이터 수집기
=======================
Google Ads API로 노출수, 클릭수, 광고비를 조회한다.

계정 구조:
  관리자 MCC (login_customer_id): 4692622227
  운영 계정 (customer_id):       4717848584
"""
"""
Google Ads 데이터 수집기 (최종 운영 버전)
=======================================
승인된 Basic Access 토큰을 사용하여 실제 데이터를 수집한다.
"""

from google.ads.googleads.client import GoogleAdsClient
from collectors.base import BaseCollector, CollectorError
from config import GoogleAdsConfig

class GoogleAdsCollector(BaseCollector):
    name = "google_ads"

    def __init__(self, config: GoogleAdsConfig):
        super().__init__()
        # 하이픈 제거 및 문자열 변환
        self.customer_id = str(config.customer_id).replace("-", "")
        self.login_customer_id = str(config.login_customer_id).replace("-", "")

        self.client = GoogleAdsClient.load_from_dict({
            "developer_token": config.developer_token,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": config.refresh_token,
            #"login_customer_id": self.login_customer_id,
            "use_proto_plus": True,
        })

    def collect(self, start_date: str, end_date: str) -> dict:
        self._validate_dates(start_date, end_date)
        
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
            self.logger.info(f"Google Ads 실제 데이터 수집 성공: 노출={impressions}, 클릭={clicks}, 비용={cost_krw}")
            
            return {
                "g_impressions": impressions,
                "g_clicks": clicks,
                "g_cost": cost_krw,
            }
        except Exception as e:
            self.logger.error(f"Google Ads API 호출 실패: {e}")
            raise CollectorError(f"Google Ads 수집 실패: {e}")