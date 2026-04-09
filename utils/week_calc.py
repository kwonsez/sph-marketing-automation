"""
주차 및 날짜 계산 유틸리티
=========================
모든 날짜/주차 관련 로직을 담당한다.
기준점: 2026-03-30(월) = 117주차
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# 기준점: 이 월요일이 117주차
BASE_MONDAY = datetime(2026, 3, 30, tzinfo=KST)
BASE_WEEK_NUM = 117


def get_last_week_range(reference_date: datetime = None) -> tuple[datetime, datetime]:
    """전주 월요일~일요일 날짜 범위를 반환한다.

    Args:
        reference_date: 기준 날짜. None이면 오늘(KST) 기준.

    Returns:
        (전주 월요일, 전주 일요일) tuple. 둘 다 KST aware datetime.
    """
    today = reference_date or datetime.now(KST)
    # 이번주 월요일 구하기 (weekday: 월=0, 일=6)
    this_monday = today - timedelta(days=today.weekday())
    # 전주 월~일
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)
    return last_monday.replace(hour=0, minute=0, second=0, microsecond=0), \
           last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)


def calc_week_number(monday_date: datetime) -> int:
    """주어진 월요일 날짜의 주차 번호를 계산한다.

    Args:
        monday_date: 해당 주의 월요일 날짜.

    Returns:
        주차 번호 (정수). 예: 117
    """
    # 기준점과의 주 차이 계산
    base = BASE_MONDAY.replace(tzinfo=None) if monday_date.tzinfo is None else BASE_MONDAY
    diff_days = (monday_date - base).days
    diff_weeks = diff_days // 7
    return BASE_WEEK_NUM + diff_weeks


def get_primary_month(monday_date: datetime, sunday_date: datetime) -> int:
    """해당 주(월~일)에서 더 많은 날이 속한 달을 반환한다.

    Args:
        monday_date: 해당 주 월요일.
        sunday_date: 해당 주 일요일.

    Returns:
        월 숫자 (1~12). 예: 4 (4월)
    """
    days_per_month = {}
    for i in range(7):
        d = monday_date + timedelta(days=i)
        m = d.month
        days_per_month[m] = days_per_month.get(m, 0) + 1
    return max(days_per_month, key=days_per_month.get)


def get_week_of_month(monday_date: datetime, primary_month: int) -> int:
    """해당 달에서 몇 번째 주인지 계산한다.

    해당 월의 1일이 속한 주를 1주차로 하고,
    이후 월요일 기준으로 주차를 카운트한다.

    Args:
        monday_date: 해당 주 월요일.
        primary_month: 기준 달.

    Returns:
        주차 순서 (1, 2, 3, 4, 5)
    """
    year = monday_date.year
    # primary_month가 monday_date의 달과 다를 수 있음
    # (예: 3/30 월요일인데 primary_month가 4월)
    if monday_date.month != primary_month:
        # 월요일이 이전 달에 속하면, primary_month 기준 1주차
        return 1

    # 해당 월 1일의 월요일 찾기
    first_of_month = monday_date.replace(day=1)
    # 1일이 속한 주의 월요일
    first_monday = first_of_month - timedelta(days=first_of_month.weekday())
    if first_monday.month != primary_month and first_monday < first_of_month:
        first_monday = first_monday  # 이전 달 월요일이라도 1주차

    diff = (monday_date - first_monday).days // 7 + 1
    return diff


def build_item_name(monday_date: datetime, sunday_date: datetime) -> str:
    """Monday.com 아이템명을 생성한다.

    Args:
        monday_date: 해당 주 월요일.
        sunday_date: 해당 주 일요일.

    Returns:
        아이템명 문자열. 예: "4월 1주차 (3/30~4/05) 117주차"
    """
    primary_month = get_primary_month(monday_date, sunday_date)
    week_of_month = get_week_of_month(monday_date, primary_month)
    week_num = calc_week_number(monday_date)

    # 날짜 포맷: M/DD (앞에 0 없이 월, 일은 0-padded)
    start_str = f"{monday_date.month}/{monday_date.day:02d}"
    end_str = f"{sunday_date.month}/{sunday_date.day:02d}"

    return f"{primary_month}월 {week_of_month}주차 ({start_str}~{end_str}) {week_num}주차"


def build_group_name(monday_date: datetime, sunday_date: datetime) -> str:
    """Monday.com 그룹명을 생성한다.

    Args:
        monday_date: 해당 주 월요일.
        sunday_date: 해당 주 일요일.

    Returns:
        그룹명 문자열. 예: "2026 4월 주간 KPI"
    """
    primary_month = get_primary_month(monday_date, sunday_date)
    # 연도는 primary_month 기준
    year = monday_date.year
    if monday_date.month != primary_month and primary_month == 1 and monday_date.month == 12:
        year += 1  # 12월 말 → 1월 그룹인 경우
    elif monday_date.month != primary_month and primary_month == 12 and monday_date.month == 1:
        year -= 1  # 1월 초 → 12월 그룹인 경우

    return f"{year} {primary_month}월 주간 KPI"


def format_start_date(monday_date: datetime) -> str:
    """Monday.com Date 컬럼용 날짜 문자열을 반환한다.

    Args:
        monday_date: 해당 주 월요일.

    Returns:
        "YYYY-MM-DD" 형식 문자열.
    """
    return monday_date.strftime("%Y-%m-%d")


def compare_values(current: float, previous: float, allow_same: bool = True) -> str | None:
    """전주대비 라벨(UP/Down/SAME)을 결정한다.

    Args:
        current: 이번 주 값.
        previous: 전주 값.
        allow_same: SAME 라벨 허용 여부. False면 동일 시 "UP" 반환.

    Returns:
        "UP", "Down", "SAME" 중 하나. 비교 불가 시 None.
    """
    if current is None or previous is None:
        return None
    if current > previous:
        return "UP"
    elif current < previous:
        return "Down"
    else:
        return "SAME" if allow_same else "UP"


# ============================================================
# 검증용: 직접 실행하면 테스트 출력
# ============================================================
if __name__ == "__main__":
    # 117주차 테스트
    mon = datetime(2026, 3, 30, tzinfo=KST)
    sun = datetime(2026, 4, 5, tzinfo=KST)
    print(f"아이템명: {build_item_name(mon, sun)}")
    print(f"그룹명:  {build_group_name(mon, sun)}")
    print(f"주차:    {calc_week_number(mon)}")
    print(f"시작일:  {format_start_date(mon)}")
    print()

    # 116주차 테스트
    mon2 = datetime(2026, 3, 23, tzinfo=KST)
    sun2 = datetime(2026, 3, 29, tzinfo=KST)
    print(f"아이템명: {build_item_name(mon2, sun2)}")
    print(f"그룹명:  {build_group_name(mon2, sun2)}")
    print(f"주차:    {calc_week_number(mon2)}")
    print()

    # 전주 범위 테스트 (오늘 기준)
    last_mon, last_sun = get_last_week_range()
    print(f"전주 범위: {last_mon.date()} ~ {last_sun.date()}")
    print(f"아이템명: {build_item_name(last_mon, last_sun)}")

    # compare_values 테스트
    print()
    print(f"전주대비 (100 vs 90): {compare_values(100, 90)}")
    print(f"전주대비 (90 vs 100): {compare_values(90, 100)}")
    print(f"전주대비 (100 vs 100): {compare_values(100, 100)}")
    print(f"전주대비 (100 vs 100, no same): {compare_values(100, 100, allow_same=False)}")
