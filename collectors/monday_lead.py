"""
Monday.com Lead Gen 수집기
==========================
7개 리드 보드에서 해당 주에 생성된 아이템 수를 합산한다.

카운트 기준 (보드별로 다를 수 있음):
  - 기본: 아이템의 created_at (생성 시각, 보드의 creation_log 컬럼 표시값과 동일)
  - BOARD_FILTER_COLUMN_OVERRIDES에 등록된 보드: 지정한 date 컬럼의 값

성능:
  - creation_log 컬럼이 있는 보드는 그 컬럼으로 내림차순 정렬한 뒤
    start_date 이전 아이템 만나는 즉시 페이지네이션 중단 (Early Exit)
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

# 보드별 카운트 기준 컬럼 오버라이드.
# 키: 보드 ID, 값: 해당 보드에서 사용할 컬럼 ID.
# 미지정 보드는 자동 탐색한 creation_log 컬럼 사용 (기본).
# 컬럼 ID는 `python tools/diagnose_lead.py --start <월> --end <일>` 출력의
# [보드 날짜 컬럼 목록]에서 확인 가능.
BOARD_FILTER_COLUMN_OVERRIDES: dict[str, str] = {
    "6680201428": "date4",  # [LI] 구글 인바운드 리드 → "날짜" (date 타입)
    "3812729444": "date4",  # [BIVIZ] 태블로 TRIAL → "날짜" (date 타입)
}


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

        분기:
          - 보드가 BOARD_FILTER_COLUMN_OVERRIDES에 등록 → 지정된 date 컬럼 값으로 비교
          - 그렇지 않음 → 아이템의 created_at 필드로 비교 (creation_log 컬럼 표시값과 동일)

        Monday API의 query_params 서버단 필터(creation_log 대상)는 일관성이 떨어져
        사용하지 않는다. 모든 경로에서 Python에서 직접 비교한다.
        """
        override_col = BOARD_FILTER_COLUMN_OVERRIDES.get(board_id)

        if override_col:
            return self._count_by_column_value(
                board_id, start_date, end_date, override_col,
            )

        # creation_log 자동 탐색 (있으면 정렬용으로만 사용 → Early Exit 가능)
        creation_col = self._get_creation_col(board_id)
        time.sleep(1)

        return self._count_with_early_exit(
            board_id, start_date, end_date, creation_col,
        )

    # ----------------------------------------------------------
    # 오버라이드 컬럼 값 직접 비교 (date 타입)
    # ----------------------------------------------------------

    def _count_by_column_value(
        self,
        board_id: str,
        start_date: str,
        end_date: str,
        column_id: str,
    ) -> int:
        """지정한 컬럼의 값을 Python에서 직접 비교하여 카운트한다.

        date 타입 컬럼(사용자 입력 날짜)에 대한 폴백 경로.
        해당 컬럼 값이 비어있는 아이템은 카운트되지 않는다.
        """
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()

        first_q = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                items_page(limit: 200) {
                    cursor
                    items { column_values { id text } }
                }
            }
        }
        """
        data = self._api_call(first_q, {"boardId": [board_id]})
        page = data["data"]["boards"][0]["items_page"]
        count = self._count_items_with_date_in_range(
            page["items"], column_id, start_d, end_d,
        )
        cursor = page.get("cursor")

        while cursor:
            time.sleep(1)
            next_q = """
            query ($cursor: String!) {
                next_items_page(limit: 200, cursor: $cursor) {
                    cursor
                    items { column_values { id text } }
                }
            }
            """
            data = self._api_call(next_q, {"cursor": cursor})
            page = data["data"]["next_items_page"]
            count += self._count_items_with_date_in_range(
                page["items"], column_id, start_d, end_d,
            )
            cursor = page.get("cursor")

        return count

    @staticmethod
    def _count_items_with_date_in_range(
        items: list[dict], column_id: str, start_d, end_d,
    ) -> int:
        """아이템 리스트에서 column_id의 값이 [start_d, end_d] 범위 안인 개수를 센다."""
        count = 0
        for item in items:
            for cv in item.get("column_values", []):
                if cv.get("id") != column_id:
                    continue
                text = cv.get("text") or ""
                if not text:
                    break
                try:
                    d = datetime.strptime(text[:10], "%Y-%m-%d").date()
                except ValueError:
                    break
                if start_d <= d <= end_d:
                    count += 1
                break
        return count

    # ----------------------------------------------------------
    # created_at 기준 카운트 (최신순 정렬 + Early Exit)
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
