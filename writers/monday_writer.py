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
    # MondayConfig의 컬럼 필드명 → 보드에 보이는 컬럼명.
    # 컬럼 ID 검증 실패 메시지를 사람이 읽을 수 있게 만들기 위한 매핑이다.
    COLUMN_FIELD_LABELS = {
        "col_start_date": "시작날짜",
        "col_lead_gen": "Lead Gen",
        "col_wau": "WAU",
        "col_contact_users": "신청문의 페이지 사용자",
        "col_g_impressions": "G노출수",
        "col_g_clicks": "G클릭수",
        "col_g_cost": "G광고비",
        "col_wow_conversion": "전주대비",
        "col_wow_gctr": "전주대비(GCTR)",
        "col_n_impressions": "N노출수",
        "col_n_clicks": "N클릭수",
        "col_n_cost": "N광고비",
        "col_wow_nctr": "전주대비(NCTR)",
        "col_n_blog_posts": "Naver 포스팅수",
        "col_n_blog_views": "N블로그 조회수",
        "col_wow_naver": "N전주대비",
    }

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
        self._columns_cache: list[dict] | None = None

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

    def find_item_by_start_date(self, start_date: str) -> str | None:
        """시작날짜 컬럼 값으로 해당 주 아이템을 찾아 ID를 반환한다. 없으면 None.

        아이템명은 보드에서 수동으로 바뀔 수 있으므로 이름 대신
        시작날짜(date) 컬럼으로 매칭한다. 이름이 바뀌어도 upsert와
        전주대비 계산이 항상 동작한다.

        2개 이상 중복 존재 시: 가장 ID가 큰 (=가장 최근 생성된) 아이템을 반환한다.
        나머지 중복 아이템은 사용자가 수동으로 정리해야 한다.

        Args:
            start_date: 해당 주 월요일 "YYYY-MM-DD".
        """
        query = """
        query ($boardId: [ID!], $colId: [String!]) {
            boards(ids: $boardId) {
                items_page (limit: 100) {
                    cursor
                    items { id column_values (ids: $colId) { text } }
                }
            }
        }
        """
        next_q = """
        query ($cursor: String!, $colId: [String!]) {
            next_items_page (limit: 100, cursor: $cursor) {
                cursor
                items { id column_values (ids: $colId) { text } }
            }
        }
        """
        col_id = [self.config.col_start_date]

        matches: list[str] = []
        data = self._execute_query(query, {"boardId": [self.board_id], "colId": col_id})
        page = data["data"]["boards"][0]["items_page"]
        while True:
            for it in page["items"]:
                if any(c["text"] == start_date for c in it["column_values"]):
                    matches.append(it["id"])
            cursor = page.get("cursor")
            if not cursor:
                break
            data = self._execute_query(next_q, {"cursor": cursor, "colId": col_id})
            page = data["data"]["next_items_page"]

        if not matches:
            return None
        if len(matches) > 1:
            self.logger.warning(
                f"시작날짜 {start_date} 아이템 {len(matches)}개 발견. "
                f"가장 최근 ID를 업데이트하고 나머지는 보존합니다. "
                f"수동 정리 필요: {matches}"
            )
        # ID가 큰 것 = 가장 최근 생성
        return max(matches, key=lambda x: int(x))

    def get_previous_week_values(self, prev_start_date: str) -> dict:
        """전주 아이템을 시작날짜로 찾아 비교에 필요한 값들을 가져온다.

        Args:
            prev_start_date: 전주 월요일 "YYYY-MM-DD".

        Returns:
            {컬럼ID: 숫자값} 딕셔너리. 전주 아이템이 없으면 빈 dict.
        """
        item_id = self.find_item_by_start_date(prev_start_date)
        if not item_id:
            self.logger.warning(
                f"전주({prev_start_date}) 아이템을 찾지 못했습니다. "
                f"전주대비 라벨은 빈 칸으로 남깁니다."
            )
            return {}

        query = """
        query ($itemId: [ID!]) {
            items (ids: $itemId) {
                column_values { id text }
            }
        }
        """
        data = self._execute_query(query, {"itemId": [item_id]})
        items = data["data"]["items"]

        prev_data = {}
        if items:
            for cv in items[0]["column_values"]:
                # 텍스트 값을 숫자로 변환하여 저장
                val = cv["text"].replace(",", "") if cv["text"] else "0"
                try:
                    prev_data[cv["id"]] = float(val)
                except ValueError:
                    prev_data[cv["id"]] = 0
        return prev_data

    def get_board_columns(self) -> list[dict]:
        """보드의 컬럼 목록을 조회한다. 실행당 1회만 호출하고 이후 캐시를 쓴다.

        Returns:
            [{"id": str, "type": str, "title": str, "settings_str": str}, ...]
        """
        if self._columns_cache is not None:
            return self._columns_cache

        query = """
        query ($boardId: [ID!]) {
            boards(ids: $boardId) {
                columns { id title type settings_str }
            }
        }
        """
        data = self._execute_query(query, {"boardId": [self.board_id]})
        self._columns_cache = data["data"]["boards"][0]["columns"]
        return self._columns_cache

    def validate_column_ids(self) -> None:
        """설정된 컬럼 ID가 실제 보드에 존재하는지 기록 전에 확인한다.

        Monday API는 column_values에 보드에 없는 컬럼 ID가 들어오면
        에러 없이 그 키만 조용히 버린다. 그래서 오타나 값 끝의 개행 하나로
        특정 컬럼만 매주 빈칸으로 기록되어도 로그·메일 어디에도 흔적이 남지 않는다.
        (실제로 MONDAY_COL_WAU = "__\r\n" 때문에 WAU가 계속 누락된 적이 있다.)
        기록 전에 미리 대조해 즉시 실패시킨다.

        Raises:
            ValueError: 보드에 없는 컬럼 ID가 설정된 경우.
        """
        board_column_ids = {c["id"] for c in self.get_board_columns()}

        invalid = []
        for field_name, label in self.COLUMN_FIELD_LABELS.items():
            col_id = getattr(self.config, field_name, "")
            # 빈 값은 "이 프로필에서 사용 안 함"이라는 의도된 설정이므로 통과.
            if col_id and col_id not in board_column_ids:
                invalid.append(f"{label} ({field_name}) → {col_id!r}")

        if invalid:
            raise ValueError(
                f"보드({self.board_id})에 존재하지 않는 컬럼 ID가 설정되어 있습니다. "
                f"이대로 기록하면 해당 값이 조용히 누락됩니다:\n  - "
                + "\n  - ".join(invalid)
            )

    def verify_written_values(self, item_id: str, cv: dict) -> list[str]:
        """기록 직후 아이템을 다시 읽어 의도한 값이 실제로 저장됐는지 대조한다.

        Args:
            item_id: 방금 생성/업데이트한 아이템 ID.
            cv: 기록에 사용한 {컬럼ID: 값} 딕셔너리.

        Returns:
            불일치 항목 설명 리스트. 비어 있으면 모두 정상 저장됨.
        """
        query = """
        query ($itemId: [ID!]) {
            items (ids: $itemId) {
                column_values { id text }
            }
        }
        """
        data = self._execute_query(query, {"itemId": [item_id]})
        items = data["data"]["items"]
        if not items:
            return [f"아이템 {item_id}을(를) 다시 조회하지 못했습니다."]

        actual = {c["id"]: (c["text"] or "") for c in items[0]["column_values"]}
        titles = {c["id"]: c["title"] for c in self.get_board_columns()}

        mismatches = []
        for col_id, expected in cv.items():
            name = titles.get(col_id, col_id)
            stored = actual.get(col_id)

            if stored is None:
                mismatches.append(f"{name}({col_id}): 보드에 없는 컬럼 — 기록되지 않음")
                continue

            if isinstance(expected, dict):
                # date는 {"date": "..."}, status는 {"label": "..."} 형태
                want = str(expected.get("label") or expected.get("date") or "")
                if stored != want:
                    mismatches.append(f"{name}({col_id}): 기대 {want!r} / 실제 {stored!r}")
                continue

            try:
                ok = float(stored.replace(",", "")) == float(expected)
            except ValueError:
                ok = False
            if not ok:
                mismatches.append(f"{name}({col_id}): 기대 {expected!r} / 실제 {stored!r}")

        return mismatches

    def get_status_label_maps(self) -> dict:
        """보드의 status(color) 컬럼별 실제 라벨 맵을 조회한다.

        Status 컬럼은 보드마다/컬럼마다 라벨 대소문자가 다르다
        (예: 전환율 컬럼은 "SAME", N전주대비 컬럼은 "Same").
        계산된 라벨("UP"/"Down"/"SAME")을 보드의 실제 라벨에 맞추기 위해
        {컬럼ID: {소문자라벨: 실제라벨}} 형태의 맵을 만든다.

        Returns:
            dict — { col_id: { lower_label: actual_label } }
        """
        columns = self.get_board_columns()

        label_maps: dict = {}
        for c in columns:
            if c["type"] not in ("status", "color"):
                continue
            try:
                settings = json.loads(c["settings_str"] or "{}")
            except (ValueError, TypeError):
                continue
            labels = settings.get("labels", {})
            # labels: {"0": "Down", "1": "UP", "2": "Same"}
            label_maps[c["id"]] = {
                str(v).lower(): str(v) for v in labels.values() if v
            }
        return label_maps

    def _normalize_status_labels(self, cv: dict, label_maps: dict) -> None:
        """cv 안의 status 라벨 값을 보드 실제 라벨(대소문자)에 맞춰 보정한다.

        보드에 없는 라벨이면 그대로 두어 API 에러로 드러나게 한다.
        cv를 제자리(in-place)에서 수정한다.
        """
        for col_id, value in cv.items():
            if not (isinstance(value, dict) and "label" in value):
                continue
            col_map = label_maps.get(col_id)
            if not col_map:
                continue
            actual = col_map.get(str(value["label"]).lower())
            if actual:
                value["label"] = actual

    def write(self, monday_date: datetime, sunday_date: datetime, collected_data: dict):
        """데이터를 Monday.com에 최종 작성한다."""
        item_name = week_calc.build_item_name(monday_date, sunday_date)
        group_title = week_calc.build_group_name(monday_date, sunday_date)

        # 0. 컬럼 ID 사전 검증 — 잘못된 ID는 기록 시 조용히 무시되므로 먼저 막는다
        self.validate_column_ids()

        # 1. 그룹 확보
        group_id = self.get_or_create_group(group_title)
        
        # 2. 전주 데이터 조회 (WoW 계산용) — 시작날짜로 매칭 (이름 변경에 무관)
        prev_monday = monday_date - week_calc.timedelta(days=7)
        prev_values = self.get_previous_week_values(
            week_calc.format_start_date(prev_monday)
        )
        
        # 3. 컬럼 값 매핑 준비
        # collected_data에 키가 있고, config에 컬럼 ID가 비어있지 않을 때만 입력한다.
        # 이로써 BIVIZ 같은 축소 리포트도 동일 writer로 처리 가능.
        col = self.config
        cv = {}

        # 시작날짜는 항상 입력
        cv[col.col_start_date] = {"date": week_calc.format_start_date(monday_date)}

        # (data_key, 컬럼 ID) 페어로 일괄 처리
        numeric_fields = [
            ("lead_gen", col.col_lead_gen),
            ("wau", col.col_wau),
            ("contact_users", col.col_contact_users),
            ("g_impressions", col.col_g_impressions),
            ("g_clicks", col.col_g_clicks),
            ("g_cost", col.col_g_cost),
            ("n_impressions", col.col_n_impressions),
            ("n_clicks", col.col_n_clicks),
            ("n_cost", col.col_n_cost),
            ("n_blog_posts", col.col_n_blog_posts),
            ("n_blog_views", col.col_n_blog_views),
        ]
        for data_key, col_id in numeric_fields:
            if data_key in collected_data and col_id:
                cv[col_id] = collected_data[data_key]

        # 4. 전주대비(WoW) 라벨 계산 — 필요한 데이터/컬럼 모두 있을 때만
        # 전환율 비교 (신청문의 / WAU)
        if "contact_users" in collected_data and "wau" in collected_data and col.col_wow_conversion:
            curr_wau = collected_data["wau"]
            curr_conv = collected_data["contact_users"] / curr_wau if curr_wau > 0 else 0
            prev_wau = prev_values.get(col.col_wau, 0)
            prev_conv = prev_values.get(col.col_contact_users, 0) / prev_wau if prev_wau > 0 else 0
            label_conv = week_calc.compare_values(curr_conv, prev_conv)
            if label_conv:
                cv[col.col_wow_conversion] = {"label": label_conv}

        # GCTR 비교 (G클릭 / G노출)
        if "g_clicks" in collected_data and "g_impressions" in collected_data and col.col_wow_gctr:
            curr_imp = collected_data["g_impressions"]
            curr_gctr = collected_data["g_clicks"] / curr_imp if curr_imp > 0 else 0
            prev_imp = prev_values.get(col.col_g_impressions, 0)
            prev_gctr = prev_values.get(col.col_g_clicks, 0) / prev_imp if prev_imp > 0 else 0
            label_gctr = week_calc.compare_values(curr_gctr, prev_gctr, allow_same=False)
            if label_gctr:
                cv[col.col_wow_gctr] = {"label": label_gctr}

        # NCTR 비교 (N클릭 / N노출)
        if "n_clicks" in collected_data and "n_impressions" in collected_data and col.col_wow_nctr:
            curr_imp = collected_data["n_impressions"]
            curr_nctr = collected_data["n_clicks"] / curr_imp if curr_imp > 0 else 0
            prev_imp = prev_values.get(col.col_n_impressions, 0)
            prev_nctr = prev_values.get(col.col_n_clicks, 0) / prev_imp if prev_imp > 0 else 0
            label_nctr = week_calc.compare_values(curr_nctr, prev_nctr)
            if label_nctr:
                cv[col.col_wow_nctr] = {"label": label_nctr}

        # 블로그 조회수 비교
        if "n_blog_views" in collected_data and col.col_wow_naver:
            label_blog = week_calc.compare_values(
                collected_data["n_blog_views"],
                prev_values.get(col.col_n_blog_views),
            )
            if label_blog:
                cv[col.col_wow_naver] = {"label": label_blog}

        # 4-1. status 라벨을 보드 실제 라벨(대소문자)에 맞춰 보정
        label_maps = self.get_status_label_maps()
        self._normalize_status_labels(cv, label_maps)

        # 5. 동일 시작날짜 아이템 검색 → 있으면 업데이트, 없으면 생성
        # (이름이 수동으로 바뀌어도 같은 주 아이템을 정확히 찾는다)
        existing_id = self.find_item_by_start_date(
            week_calc.format_start_date(monday_date)
        )

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
            self._assert_written(updated_id, cv)
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
        self._assert_written(new_id, cv)
        self.logger.info(f"신규 작성 완료! 아이템 ID: {new_id}")
        return {"item_id": new_id, "was_update": False}

    def _assert_written(self, item_id: str, cv: dict) -> None:
        """기록 결과를 검증하고, 불일치가 있으면 예외를 발생시킨다.

        Args:
            item_id: 검증할 아이템 ID.
            cv: 기록에 사용한 {컬럼ID: 값} 딕셔너리.

        Raises:
            Exception: 의도한 값과 실제 저장값이 다른 경우.
                       (orchestrator가 잡아 실패 메일을 발송한다)
        """
        mismatches = self.verify_written_values(item_id, cv)
        if not mismatches:
            self.logger.info(f"기록 값 검증 통과 — {len(cv)}개 컬럼 모두 일치")
            return

        for m in mismatches:
            self.logger.error(f"기록 값 불일치: {m}")
        raise Exception(
            f"Monday 기록 후 값 검증 실패 (아이템 {item_id}, {len(mismatches)}건): "
            + " | ".join(mismatches)
        )