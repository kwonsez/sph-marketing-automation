"""
Collector 추상 기반 클래스
=========================
모든 collector는 이 클래스를 상속한다.
collect()가 반환하는 dict의 키는 config.MondayConfig의
col_* 속성명에서 col_ 접두사를 뺀 것이다.

예: col_wau → "wau", col_g_clicks → "g_clicks"
Writer에서: column_id = getattr(config.monday, f"col_{key}")
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime


class CollectorError(Exception):
    """collector 공통 에러"""


class NaverBlogError(CollectorError):
    """네이버 블로그 전용 에러.
    orchestrator가 이 에러만 별도 처리하여
    나머지 데이터로 Monday.com 작성을 계속한다.
    """


class BaseCollector(ABC):
    """모든 데이터 수집기의 추상 기반 클래스.

    서브클래스는 반드시 name 클래스 속성과 collect() 메서드를 구현해야 한다.
    """

    name: str = ""

    def __init__(self):
        self.logger = logging.getLogger(f"collectors.{self.name}")

    @abstractmethod
    def collect(self, start_date: str, end_date: str) -> dict:
        """데이터를 수집한다.

        Args:
            start_date: 시작일 "YYYY-MM-DD".
            end_date: 종료일 "YYYY-MM-DD".

        Returns:
            {"필드명": 값} 딕셔너리.
        """

    def _validate_dates(self, start_date: str, end_date: str):
        """날짜 형식(YYYY-MM-DD)을 검증한다. 잘못되면 즉시 에러."""
        for d in (start_date, end_date):
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                raise CollectorError(f"날짜 형식 오류: {d!r} (YYYY-MM-DD 필요)")
