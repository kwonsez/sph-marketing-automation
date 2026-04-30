"""
Lead Gen 수집 숫자 진단 도구
============================
대시보드와 스크립트의 카운트가 다를 때, 어디서 차이가 나는지 보드별로 분해해서 보여준다.

각 보드에 대해:
  1) Strategy 1 (creation_log 서버단 필터) 카운트
  2) Strategy 2 (Python에서 created_at 기준 필터) 카운트
  3) 모든 아이템 raw dump (created_at + 보드의 date 타입 컬럼들 값)
  4) Archived 아이템 별도 집계
  5) Sub-items 보유 아이템 표시

사용법:
  python tools/diagnose_lead.py --start 2026-04-20 --end 2026-04-26
  python tools/diagnose_lead.py --start 2026-04-20 --end 2026-04-26 --board-id 3126575269
"""

import argparse
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

# Windows cp949 환경에서 이모지/유니코드 출력이 깨지지 않도록 UTF-8 강제
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

KST = ZoneInfo("Asia/Seoul")
MONDAY_API_URL = "https://api.monday.com/v2"

API_TOKEN = os.getenv("MONDAY_API_TOKEN", "")
LEAD_BOARD_IDS = [
    bid.strip() for bid in os.getenv("MONDAY_LEAD_BOARD_IDS", "").split(",") if bid.strip()
]


def api_call(query: str, variables: dict = None) -> dict:
    """Monday.com API 호출."""
    headers = {"Authorization": API_TOKEN, "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(MONDAY_API_URL, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"API 에러: {data['errors']}")
    return data


def get_board_info(board_id: str) -> dict:
    """보드의 이름과 컬럼 메타데이터를 조회한다."""
    query = """
    query ($boardId: [ID!]) {
        boards(ids: $boardId) {
            name
            columns { id title type }
        }
    }
    """
    data = api_call(query, {"boardId": [board_id]})
    return data["data"]["boards"][0]


def fetch_all_items(board_id: str, include_archived: bool = False) -> list[dict]:
    """보드의 모든 아이템을 페이지네이션으로 수집한다.

    column_values는 모든 컬럼을 가져온다. 호출자가 Python에서 필터링한다.
    """
    query = """
    query ($boardId: [ID!]) {
        boards(ids: $boardId) {
            items_page(limit: 200) {
                cursor
                items {
                    id
                    name
                    created_at
                    state
                    subitems { id }
                    column_values { id text value }
                }
            }
        }
    }
    """
    items: list[dict] = []
    data = api_call(query, {"boardId": [board_id]})
    page = data["data"]["boards"][0]["items_page"]
    items.extend(page["items"])
    cursor = page.get("cursor")

    while cursor:
        time.sleep(1)
        next_q = """
        query ($cursor: String!) {
            next_items_page(limit: 200, cursor: $cursor) {
                cursor
                items {
                    id
                    name
                    created_at
                    state
                    subitems { id }
                    column_values { id text value }
                }
            }
        }
        """
        data = api_call(next_q, {"cursor": cursor})
        page = data["data"]["next_items_page"]
        items.extend(page["items"])
        cursor = page.get("cursor")

    if not include_archived:
        items = [it for it in items if it.get("state") == "active"]
    return items


def count_with_api_filter(board_id: str, start: str, end: str, creation_col: str) -> int:
    """Strategy 1: 서버단 필터링 카운트."""
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
    qp = {"rules": [{"column_id": creation_col, "compare_value": [start, end]}]}
    data = api_call(query, {"boardId": [board_id], "qp": qp})
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
        data = api_call(next_q, {"cursor": cursor})
        page = data["data"]["next_items_page"]
        count += len(page["items"])
        cursor = page.get("cursor")
    return count


def diagnose_board(board_id: str, start: str, end: str):
    """한 보드를 분석한다."""
    info = get_board_info(board_id)
    print("=" * 78)
    print(f"📋 [{board_id}] {info['name']}")
    print("=" * 78)

    # 컬럼 분류
    creation_col = None
    date_cols = []  # 사용자가 손으로 채울 수 있는 date 컬럼들
    for col in info["columns"]:
        if col["type"] == "creation_log":
            creation_col = col["id"]
        if col["type"] in ("date", "creation_log"):
            date_cols.append(col)

    print("\n[보드 날짜 컬럼 목록]")
    for c in date_cols:
        marker = " ← 스크립트가 사용 중" if c["id"] == creation_col else ""
        print(f"  • {c['id']:30s}  type={c['type']:14s}  title={c['title']}{marker}")

    # 범위 파싱
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=KST)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=KST,
    )

    # Strategy 1
    s1 = "(creation_log 컬럼 없음)"
    if creation_col:
        try:
            time.sleep(1)
            s1 = count_with_api_filter(board_id, start, end, creation_col)
        except Exception as e:
            s1 = f"실패: {e}"

    # 모든 아이템 + Strategy 2 (Python 필터)
    time.sleep(1)
    active_items = fetch_all_items(board_id, include_archived=False)
    time.sleep(1)
    all_items = fetch_all_items(board_id, include_archived=True)
    archived_items = [it for it in all_items if it.get("state") != "active"]

    in_range_active = []
    in_range_archived = []
    for it in active_items:
        created = datetime.fromisoformat(
            it["created_at"].replace("Z", "+00:00")
        ).astimezone(KST)
        if start_dt <= created <= end_dt:
            in_range_active.append((it, created))
    for it in archived_items:
        created = datetime.fromisoformat(
            it["created_at"].replace("Z", "+00:00")
        ).astimezone(KST)
        if start_dt <= created <= end_dt:
            in_range_archived.append((it, created))

    print(f"\n[카운트 결과] (기간: {start} ~ {end})")
    print(f"  Strategy 1 (서버단 creation_log 필터):    {s1}")
    print(f"  Strategy 2 (created_at, active만):        {len(in_range_active)}")
    print(f"  + Archived 추가 시:                       {len(in_range_active) + len(in_range_archived)}")

    date_col_id_set = {c["id"] for c in date_cols}
    if in_range_active:
        print(f"\n[active 아이템 상세 ({len(in_range_active)}건)]")
        for it, created in in_range_active:
            sub_n = len(it.get("subitems") or [])
            sub_marker = f"  [sub-items {sub_n}개]" if sub_n else ""
            print(f"  - {created.strftime('%Y-%m-%d %H:%M KST')}  {it['name'][:40]}{sub_marker}")
            # 날짜 컬럼들의 값만 출력 (대시보드 위젯 필터 추정용)
            for cv in it.get("column_values", []):
                if cv.get("id") in date_col_id_set and cv.get("text"):
                    print(f"      L  {cv['id']:25s} = {cv['text']}")

    if in_range_archived:
        print(f"\n[archived 아이템 (대시보드에 따라 카운트될 수 있음, {len(in_range_archived)}건)]")
        for it, created in in_range_archived:
            print(f"  - {created.strftime('%Y-%m-%d %H:%M KST')}  {it['name'][:40]}  [state={it.get('state')}]")

    # 사용자 date 컬럼 기준 카운트도 시도 (대시보드가 이 기준일 가능성)
    user_date_cols = [c for c in date_cols if c["type"] == "date"]
    if user_date_cols:
        print(f"\n[참고: 사용자 입력 date 컬럼 기준 카운트]")
        for col in user_date_cols:
            cnt = 0
            for it in active_items:
                for cv in it.get("column_values", []):
                    if cv.get("id") == col["id"] and cv.get("text"):
                        try:
                            d = datetime.strptime(cv["text"][:10], "%Y-%m-%d").replace(tzinfo=KST)
                            if start_dt <= d <= end_dt:
                                cnt += 1
                        except ValueError:
                            pass
                        break
            print(f"  • '{col['title']}' ({col['id']}) 기준: {cnt}건")
    print()


def main():
    parser = argparse.ArgumentParser(description="Lead Gen 카운트 불일치 진단")
    parser.add_argument("--start", required=True, help="시작일 YYYY-MM-DD (월요일)")
    parser.add_argument("--end", required=True, help="종료일 YYYY-MM-DD (일요일)")
    parser.add_argument("--board-id", help="특정 보드만 진단. 생략 시 7개 전체")
    args = parser.parse_args()

    if not API_TOKEN:
        print("❌ MONDAY_API_TOKEN 환경변수가 비어있습니다.", file=sys.stderr)
        sys.exit(1)

    targets = [args.board_id] if args.board_id else LEAD_BOARD_IDS
    if not targets:
        print("❌ 진단할 보드가 없습니다.", file=sys.stderr)
        sys.exit(1)

    for bid in targets:
        try:
            diagnose_board(bid, args.start, args.end)
        except Exception as e:
            print(f"⚠️  [{bid}] 진단 실패: {e}\n")
        time.sleep(1)


if __name__ == "__main__":
    main()
