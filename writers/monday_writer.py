"""
Monday.com 리포트 작성기
=======================
수집된 데이터를 Monday.com 보드에 작성한다.
전주 데이터를 조회하여 WoW(전주대비) 라벨을 자동으로 계산한다.
"""

import json
import logging
import time
import requests
from datetime import datetime
from config import MondayConfig
from utils import week_calc

MONDAY_API_URL = "https://api.monday.com/v2"

class MondayWriter:
    def __init__(self, config: MondayConfig):
        self.logger = logging.getLogger("writer.monday")
        self.api_token = config.api_token
        self.board_id = config.weekly_board_id
        self.config = config
        self.headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "API-Version": "2023-10"
        }

    def _execute_query(self, query: str, variables: dict = None) -> dict:
        """Monday.com API 실행 헬퍼"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        response = requests.post(MONDAY_API_URL, headers=self.headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            self.logger.error(f"Monday API 에러: {data['errors']}")
            raise Exception(f"Monday API 에러: {data['errors']}")
        
        time.sleep(1)  # Rate limit 방지
        return data

    def get_or_create_group(self, group_title: str) -> str:
        """그룹이 존재하면 ID를 반환하고, 없으면 생성한다."""
        query = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                groups { id title }
            }
        }
        """
        data = self._execute_query(query, {"boardId": [self.board_id]})
        groups = data["data"]["boards"][0]["groups"]
        
        for g in groups:
            if g["title"] == group_title:
                return g["id"]
        
        # 그룹 생성
        self.logger.info(f"새 그룹 생성 중: {group_title}")
        create_query = """
        mutation ($boardId: ID!, $groupTitle: String!) {
            create_group (board_id: $boardId, group_name: $groupTitle) { id }
        }
        """
        res = self._execute_query(create_query, {"boardId": self.board_id, "groupTitle": group_title})
        return res["data"]["create_group"]["id"]

    def find_item_by_name(self, item_name: str) -> str | None:
        """보드에서 동일 이름 아이템을 찾아 ID를 반환한다. 없으면 None.

        2개 이상 중복 존재 시: 가장 ID가 큰 (=가장 최근 생성된) 아이템을 반환한다.
        나머지 중복 아이템은 사용자가 수동으로 정리해야 한다.
        """
        query = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                items_page (limit: 100) {
                    cursor
                    items { id name }
                }
            }
        }
        """
        next_q = """
        query ($cursor: String!) {
            next_items_page (limit: 100, cursor: $cursor) {
                cursor
                items { id name }
            }
        }
        """

        matches: list[str] = []
        data = self._execute_query(query, {"boardId": [self.board_id]})
        page = data["data"]["boards"][0]["items_page"]
        while True:
            for it in page["items"]:
                if it["name"] == item_name:
                    matches.append(it["id"])
            cursor = page.get("cursor")
            if not cursor:
                break
            data = self._execute_query(next_q, {"cursor": cursor})
            page = data["data"]["next_items_page"]

        if not matches:
            return None
        if len(matches) > 1:
            self.logger.warning(
                f"동일 이름 아이템 {len(matches)}개 발견 ({item_name}). "
                f"가장 최근 ID를 업데이트하고 나머지는 보존합니다. "
                f"수동 정리 필요: {matches}"
            )
        # ID가 큰 것 = 가장 최근 생성
        return max(matches, key=lambda x: int(x))

    def get_previous_week_values(self, prev_item_name: str) -> dict:
        """전주 아이템을 찾아 비교에 필요한 값들을 가져온다."""
        query = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                items_page (limit: 100) {
                    items {
                        name
                        column_values {
                            id
                            text
                            value
                        }
                    }
                }
            }
        }
        """
        data = self._execute_query(query, {"boardId": [self.board_id]})
        items = data["data"]["boards"][0]["items_page"]["items"]
        
        prev_data = {}
        for item in items:
            if item["name"] == prev_item_name:
                for cv in item["column_values"]:
                    # 텍스트 값을 숫자로 변환하여 저장
                    val = cv["text"].replace(",", "") if cv["text"] else "0"
                    try:
                        prev_data[cv["id"]] = float(val)
                    except ValueError:
                        prev_data[cv["id"]] = 0
                break
        return prev_data

    def write(self, monday_date: datetime, sunday_date: datetime, collected_data: dict):
        """데이터를 Monday.com에 최종 작성한다."""
        item_name = week_calc.build_item_name(monday_date, sunday_date)
        group_title = week_calc.build_group_name(monday_date, sunday_date)
        
        # 1. 그룹 확보
        group_id = self.get_or_create_group(group_title)
        
        # 2. 전주 데이터 조회 (WoW 계산용)
        prev_monday = monday_date - week_calc.timedelta(days=7)
        prev_sunday = sunday_date - week_calc.timedelta(days=7)
        prev_item_name = week_calc.build_item_name(prev_monday, prev_sunday)
        prev_values = self.get_previous_week_values(prev_item_name)
        
        # 3. 컬럼 값 매핑 준비
        col = self.config
        cv = {}
        
        # 기본 수치 입력
        cv[col.col_start_date] = {"date": week_calc.format_start_date(monday_date)}
        cv[col.col_lead_gen] = collected_data.get("lead_gen", 0)
        cv[col.col_wau] = collected_data.get("wau", 0)
        cv[col.col_contact_users] = collected_data.get("contact_users", 0)
        cv[col.col_g_impressions] = collected_data.get("g_impressions", 0)
        cv[col.col_g_clicks] = collected_data.get("g_clicks", 0)
        cv[col.col_g_cost] = collected_data.get("g_cost", 0)
        cv[col.col_n_impressions] = collected_data.get("n_impressions", 0)
        cv[col.col_n_clicks] = collected_data.get("n_clicks", 0)
        cv[col.col_n_cost] = collected_data.get("n_cost", 0)
        cv[col.col_n_blog_posts] = collected_data.get("n_blog_posts", 0)
        cv[col.col_n_blog_views] = collected_data.get("n_blog_views", 0)

        # 4. 전주대비(WoW) 라벨 계산
        # 전환율 비교 (신청문의 / WAU)
        curr_conv = cv[col.col_contact_users] / cv[col.col_wau] if cv[col.col_wau] > 0 else 0
        prev_conv = prev_values.get(col.col_contact_users, 0) / prev_values.get(col.col_wau, 1) if prev_values.get(col.col_wau, 0) > 0 else 0
        label_conv = week_calc.compare_values(curr_conv, prev_conv)
        if label_conv: cv[col.col_wow_conversion] = {"label": label_conv}

        # GCTR 비교 (G클릭 / G노출)
        curr_gctr = cv[col.col_g_clicks] / cv[col.col_g_impressions] if cv[col.col_g_impressions] > 0 else 0
        prev_gctr = prev_values.get(col.col_g_clicks, 0) / prev_values.get(col.col_g_impressions, 1) if prev_values.get(col.col_g_impressions, 0) > 0 else 0
        label_gctr = week_calc.compare_values(curr_gctr, prev_gctr, allow_same=False) # 동일 시 UP
        if label_gctr: cv[col.col_wow_gctr] = {"label": label_gctr}

        # NCTR 비교 (N클릭 / N노출)
        curr_nctr = cv[col.col_n_clicks] / cv[col.col_n_impressions] if cv[col.col_n_impressions] > 0 else 0
        prev_nctr = prev_values.get(col.col_n_clicks, 0) / prev_values.get(col.col_n_impressions, 1) if prev_values.get(col.col_n_impressions, 0) > 0 else 0
        label_nctr = week_calc.compare_values(curr_nctr, prev_nctr)
        if label_nctr: cv[col.col_wow_nctr] = {"label": label_nctr}

        # 블로그 조회수 비교
        label_blog = week_calc.compare_values(cv[col.col_n_blog_views], prev_values.get(col.col_n_blog_views))
        if label_blog: cv[col.col_wow_naver] = {"label": label_blog}

        # 5. 동일 이름 아이템 검색 → 있으면 업데이트, 없으면 생성
        existing_id = self.find_item_by_name(item_name)

        if existing_id:
            self.logger.info(f"기존 아이템 발견 (ID: {existing_id}). 컬럼 값 업데이트 중: {item_name}")
            update_query = """
            mutation ($boardId: ID!, $itemId: ID!, $columnValues: JSON!) {
                change_multiple_column_values (
                    board_id: $boardId,
                    item_id: $itemId,
                    column_values: $columnValues
                ) { id }
            }
            """
            variables = {
                "boardId": self.board_id,
                "itemId": existing_id,
                "columnValues": json.dumps(cv),
            }
            res = self._execute_query(update_query, variables)
            updated_id = res["data"]["change_multiple_column_values"]["id"]
            self.logger.info(f"업데이트 완료! 아이템 ID: {updated_id}")
            return {"item_id": updated_id, "was_update": True}

        self.logger.info(f"신규 아이템 생성 중: {item_name}")
        create_item_query = """
        mutation ($boardId: ID!, $groupId: String!, $itemName: String!, $columnValues: JSON!) {
            create_item (
                board_id: $boardId,
                group_id: $groupId,
                item_name: $itemName,
                column_values: $columnValues
            ) { id }
        }
        """
        variables = {
            "boardId": self.board_id,
            "groupId": group_id,
            "itemName": item_name,
            "columnValues": json.dumps(cv)
        }

        res = self._execute_query(create_item_query, variables)
        new_id = res["data"]["create_item"]["id"]
        self.logger.info(f"신규 작성 완료! 아이템 ID: {new_id}")
        return {"item_id": new_id, "was_update": False}