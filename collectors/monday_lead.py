"""
Monday.com Lead Gen 수집기
==========================
7개 리드 보드에서 해당 주에 생성된 아이템 수를 합산한다.

최적화 전략:
  1차) query_params rules로 서버단 날짜 필터링 (creation_log 컬럼 활용)
  2차) 1차 실패 시 → 최신순 내림차순 정렬 + 조기 종료
      (start_date 이전 아이템 발견 시 이후 페이지 API 호출 생략)

방어:
  - 모든 API 호출 간 time.sleep(1) (complexity rate limit)
  - creation_log 컬럼 ID는 보드별 캐시
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from collectors.base import BaseCollector, CollectorError
from config import MondayConfig

KST = ZoneInfo("Asia/Seoul")
MONDAY_API_URL = "https://api.monday.com/v2"


class MondayLeadCollector(BaseCollector):
    """7개 리드 보드의 주간 아이템 생성수를 합산한다."""

    name = "monday_lead"

    def __init__(self, config: MondayConfig):
        super().__init__()
        self.api_token = config.api_token
        self.board_ids = config.lead_board_ids
        self._creation_col_cache: dict[str, str | None] = {}

    def collect(self, start_date: str, end_date: str) -> dict:
        """리드 데이터를 수집한다.

        Args:
            start_date: 시작일 "YYYY-MM-DD" (월요일).
            end_date: 종료일 "YYYY-MM-DD" (일요일).

        Returns:
            {"lead_gen": int}
        """
        self._validate_dates(start_date, end_date)

        total = 0
        for i, board_id in enumerate(self.board_ids):
            if i > 0:
                time.sleep(1)  # 보드 간 rate limit
            count = self._count_items_in_range(board_id, start_date, end_date)
            self.logger.info(f"  보드 {board_id}: {count}건")
            total += count

        self.logger.info(
            f"Lead Gen 합산: {total}건 ({len(self.board_ids)}개 보드)"
        )
        return {"lead_gen": total}

    # ----------------------------------------------------------
    # API 호출
    # ----------------------------------------------------------

    def _api_call(self, query: str, variables: dict = None) -> dict:
        """Monday.com GraphQL API를 호출한다."""
        headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
        }
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = requests.post(MONDAY_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            raise CollectorError(f"Monday.com API 에러: {data['errors']}")
        return data

    # ----------------------------------------------------------
    # creation_log 컬럼 탐색 (보드별 1회, 캐시)
    # ----------------------------------------------------------

    def _get_creation_col(self, board_id: str) -> str | None:
        """보드의 creation_log 타입 컬럼 ID를 조회한다."""
        if board_id in self._creation_col_cache:
            return self._creation_col_cache[board_id]

        query = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                columns { id type }
            }
        }
        """
        data = self._api_call(query, {"boardId": [board_id]})
        col_id = None
        for col in data["data"]["boards"][0]["columns"]:
            if col["type"] == "creation_log":
                col_id = col["id"]
                break

        self._creation_col_cache[board_id] = col_id
        return col_id

    # ----------------------------------------------------------
    # 전략 분기
    # ----------------------------------------------------------

    def _count_items_in_range(
        self, board_id: str, start_date: str, end_date: str,
    ) -> int:
        """한 보드에서 기간 내 생성된 아이템 수를 센다.

        1차: API query_params rules 서버단 필터링
        2차: 최신순 정렬 + Early Exit
        """
        creation_col = self._get_creation_col(board_id)
        time.sleep(1)

        # 1차: 서버단 필터링
        if creation_col:
            try:
                count = self._count_with_api_filter(
                    board_id, start_date, end_date, creation_col,
                )
                self.logger.debug(f"보드 {board_id}: API 필터링 성공")
                return count
            except Exception as e:
                self.logger.info(
                    f"보드 {board_id}: API 필터링 실패 ({e}), Early Exit 전환"
                )
                time.sleep(1)

        # 2차: Early Exit
        return self._count_with_early_exit(
            board_id, start_date, end_date, creation_col,
        )

    # ----------------------------------------------------------
    # Strategy 1: API 필터링
    # ----------------------------------------------------------

    def _count_with_api_filter(
        self,
        board_id: str,
        start_date: str,
        end_date: str,
        creation_col: str,
    ) -> int:
        """서버단 query_params rules로 필터링하여 카운트한다.

        서버에서 날짜 범위에 맞는 아이템만 반환하므로
        반환된 아이템 수 = 카운트. Python 필터 불필요.
        """
        query = """
        query ($boardId: [ID!], $qp: ItemsQuery) {
            boards(ids: $boardId) {
                items_page(limit: 500, query_params: $qp) {
                    cursor
                    items { id }
                }
            }
        }
        """
        qp = {
            "rules": [{
                "column_id": creation_col,
                "compare_value": [start_date, end_date],
            }],
        }

        data = self._api_call(query, {"boardId": [board_id], "qp": qp})
        page = data["data"]["boards"][0]["items_page"]
        count = len(page["items"])
        cursor = page.get("cursor")

        while cursor:
            time.sleep(1)
            next_q = """
            query ($cursor: String!) {
                next_items_page(limit: 500, cursor: $cursor) {
                    cursor
                    items { id }
                }
            }
            """
            data = self._api_call(next_q, {"cursor": cursor})
            page = data["data"]["next_items_page"]
            count += len(page["items"])
            cursor = page.get("cursor")

        return count

    # ----------------------------------------------------------
    # Strategy 2: 최신순 정렬 + Early Exit
    # ----------------------------------------------------------

    def _count_with_early_exit(
        self,
        board_id: str,
        start_date: str,
        end_date: str,
        creation_col: str | None,
    ) -> int:
        """최신순 정렬 후 start_date 이전 아이템 발견 시 조기 종료한다.

        creation_col이 있으면 내림차순 정렬하여 조기 종료 가능.
        없으면 전체 순회 (fallback).
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=KST)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=KST,
        )

        ordered = creation_col is not None

        # 첫 페이지
        if ordered:
            query = """
            query ($boardId: [ID!], $qp: ItemsQuery) {
                boards(ids: $boardId) {
                    items_page(limit: 100, query_params: $qp) {
                        cursor
                        items { created_at }
                    }
                }
            }
            """
            qp = {"order_by": {"column_id": creation_col, "direction": "desc"}}
            variables = {"boardId": [board_id], "qp": qp}
        else:
            query = """
            query ($boardId: [ID!]) {
                boards(ids: $boardId) {
                    items_page(limit: 100) {
                        cursor
                        items { created_at }
                    }
                }
            }
            """
            variables = {"boardId": [board_id]}

        data = self._api_call(query, variables)
        page = data["data"]["boards"][0]["items_page"]
        count, should_stop = self._process_page(
            page["items"], start_dt, end_dt, ordered,
        )
        cursor = page.get("cursor")

        # 후속 페이지
        while cursor and not should_stop:
            time.sleep(1)
            next_q = """
            query ($cursor: String!) {
                next_items_page(limit: 100, cursor: $cursor) {
                    cursor
                    items { created_at }
                }
            }
            """
            data = self._api_call(next_q, {"cursor": cursor})
            page = data["data"]["next_items_page"]
            page_count, should_stop = self._process_page(
                page["items"], start_dt, end_dt, ordered,
            )
            count += page_count
            cursor = page.get("cursor")

        return count

    def _process_page(
        self,
        items: list[dict],
        start_dt: datetime,
        end_dt: datetime,
        ordered: bool,
    ) -> tuple[int, bool]:
        """아이템을 카운트하고 조기 종료 여부를 판단한다.

        Args:
            items: 아이템 리스트.
            start_dt: 시작 KST datetime.
            end_dt: 종료 KST datetime.
            ordered: True면 created_at 내림차순 (조기 종료 가능).

        Returns:
            (기간 내 아이템 수, 조기종료 여부) tuple.
        """
        count = 0
        for item in items:
            created_kst = datetime.fromisoformat(
                item["created_at"].replace("Z", "+00:00")
            ).astimezone(KST)

            if start_dt <= created_kst <= end_dt:
                count += 1
            elif created_kst < start_dt and ordered:
                # 내림차순이므로 이후 아이템은 모두 더 오래됨 → 즉시 중단
                return count, True

        return count, False
