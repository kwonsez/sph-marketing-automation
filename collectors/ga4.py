"""
GA4 데이터 수집기
================
Google Analytics Data API v1beta로
WAU(totalUsers)와 /contact 페이지 사용자(activeUsers)를 조회한다.

인증: 서비스 계정 JSON 키 (GOOGLE_APPLICATION_CREDENTIALS)
"""

import os

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    Metric,
    RunReportRequest,
)

from collectors.base import BaseCollector
from config import GA4Config


class GA4Collector(BaseCollector):
    """GA4에서 WAU와 /contact 페이지 사용자수를 수집한다."""

    name = "ga4"

    def __init__(self, config: GA4Config):
        super().__init__()
        self.property_id = config.property_id
        # 서비스 계정 키 경로를 환경변수로 설정 (라이브러리가 자동 참조)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config.credentials_path
        self.client = BetaAnalyticsDataClient()

    def collect(self, start_date: str, end_date: str) -> dict:
        """GA4 데이터를 수집한다.

        Args:
            start_date: 시작일 "YYYY-MM-DD".
            end_date: 종료일 "YYYY-MM-DD".

        Returns:
            {"wau": int, "contact_users": int}
        """
        self._validate_dates(start_date, end_date)

        wau = self._get_wau(start_date, end_date)
        contact_users = self._get_contact_users(start_date, end_date)

        self.logger.info(f"GA4 수집 완료: WAU={wau}, 신청문의={contact_users}")
        return {"wau": wau, "contact_users": contact_users}

    def _get_wau(self, start_date: str, end_date: str) -> int:
        """주간 활성 사용자 수(totalUsers)를 조회한다."""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[Metric(name="totalUsers")],
        )
        response = self.client.run_report(request)
        if response.rows:
            return int(response.rows[0].metric_values[0].value)
        return 0

    def _get_contact_users(self, start_date: str, end_date: str) -> int:
        """/contact 페이지 활성 사용자 수(activeUsers)를 조회한다."""
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[Metric(name="activeUsers")],
            dimensions=[Dimension(name="pagePath")],
            dimension_filter=FilterExpression(
                filter=Filter(
                    field_name="pagePath",
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.CONTAINS,
                        value="/contact",
                    ),
                ),
            ),
        )
        response = self.client.run_report(request)
        # /contact 포함 경로가 여러 개일 수 있으므로 합산
        return sum(int(row.metric_values[0].value) for row in response.rows)
