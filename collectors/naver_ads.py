import base64
import hashlib
import hmac
import json
import time
import requests
from collectors.base import BaseCollector
from config import NaverAdsConfig

BASE_URL = "https://api.searchad.naver.com"

class NaverAdsCollector(BaseCollector):
    name = "naver_ads"

    def __init__(self, config: NaverAdsConfig):
        super().__init__()
        self.api_key = config.api_key
        self.secret_key = config.secret_key
        self.customer_id = str(config.customer_id)

    def collect(self, start_date: str, end_date: str) -> dict:
        self._validate_dates(start_date, end_date)

        # 1) 캠페인 ID 목록 조회
        campaigns_resp = self._get("/ncc/campaigns")
        
        # 네이버 응답 구조 처리 (리스트 또는 {"data": []})
        if isinstance(campaigns_resp, dict) and "data" in campaigns_resp:
            campaign_list = campaigns_resp["data"]
        elif isinstance(campaigns_resp, list):
            campaign_list = campaigns_resp
        else:
            self.logger.error(f"캠페인 조회 실패. API 응답: {campaigns_resp}")
            return {"n_impressions": 0, "n_clicks": 0, "n_cost": 0}

        campaign_ids = [c["nccCampaignId"] for c in campaign_list if isinstance(c, dict) and "nccCampaignId" in c]

        if not campaign_ids:
            self.logger.warning("네이버 검색광고 캠페인이 없습니다")
            return {"n_impressions": 0, "n_clicks": 0, "n_cost": 0}

        # 2) 전체 캠페인 통계 일괄 조회
        stats_resp = self._get("/stats", params={
            "ids": ",".join(campaign_ids),
            "fields": json.dumps(["impCnt", "clkCnt", "salesAmt"]),
            "timeRange": json.dumps({"since": start_date, "until": end_date}),
        })

        # 통계 응답 구조 처리 ({"data": [...]})
        if isinstance(stats_resp, dict) and "data" in stats_resp:
            stats = stats_resp["data"]
        elif isinstance(stats_resp, list):
            stats = stats_resp
        else:
            self.logger.error(f"통계 조회 실패. API 응답: {stats_resp}")
            return {"n_impressions": 0, "n_clicks": 0, "n_cost": 0}

        imp = sum(int(s.get("impCnt", 0)) for s in stats if isinstance(s, dict))
        clk = sum(int(s.get("clkCnt", 0)) for s in stats if isinstance(s, dict))
        cost = sum(int(s.get("salesAmt", 0)) for s in stats if isinstance(s, dict))

        self.logger.info(f"네이버 광고 수집 완료: 노출={imp}, 클릭={clk}, 비용={cost}")
        return {"n_impressions": imp, "n_clicks": clk, "n_cost": cost}

    def _sign(self, method: str, uri: str) -> dict:
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}.{method}.{uri}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        return {
            "X-API-KEY": self.api_key,
            "X-Customer": self.customer_id,
            "X-Timestamp": timestamp,
            "X-Signature": base64.b64encode(signature).decode("utf-8"),
        }

    def _get(self, uri: str, params: dict = None):
        headers = self._sign("GET", uri)
        resp = requests.get(f"{BASE_URL}{uri}", headers=headers, params=params)
        try:
            return resp.json()
        except:
            return {"error": "JSON_DECODE_ERROR", "text": resp.text}