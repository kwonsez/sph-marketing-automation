"""
Weekly Report Automation - CLI Entry Point
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from config import load_config
from orchestrator import Orchestrator

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("automation.log", encoding="utf-8"),
    ],
)


def main():
    parser = argparse.ArgumentParser(description="Weekly Marketing Report Automation")
    parser.add_argument("--date", type=str, help="대상 주차 월요일 날짜 (YYYY-MM-DD). 생략 시 지난주 자동 계산.")
    parser.add_argument("--dry-run", action="store_true", help="Monday.com에 쓰지 않고 수집 테스트만 수행")
    parser.add_argument(
        "--report",
        choices=["sph", "biviz", "all"],
        default="all",
        help="처리할 리포트. sph / biviz / all (기본 all = 두 리포트 순차 실행)",
    )

    args = parser.parse_args()
    log = logging.getLogger("main")

    # BIVIZ 환경변수가 모두 설정되어 있는지 사전 확인.
    # GitHub Actions 등에서 BIVIZ 변수가 아직 추가되지 않은 경우, all 실행 시
    # SPH까지 같이 실패하지 않도록 BIVIZ를 자동 비활성화한다.
    biviz_available = bool(os.getenv("MONDAY_BIVIZ_BOARD_ID")) and bool(
        os.getenv("BIVIZ_GA4_PROPERTY_ID")
    )

    # 1. 설정 로드 — 검증 스킵 그룹 결정
    skip_groups: list[str] = []
    if args.report == "sph" or (args.report == "all" and not biviz_available):
        skip_groups = ["BIVIZ Monday.com", "BIVIZ GA4"]
        if args.report == "all" and not biviz_available:
            log.warning(
                "BIVIZ 환경변수가 설정되지 않아 BIVIZ 리포트는 스킵됩니다. "
                "(MONDAY_BIVIZ_BOARD_ID, BIVIZ_GA4_PROPERTY_ID 등 추가 필요)"
            )
    config = load_config(skip_groups=skip_groups)

    # 2. 대상 날짜 파싱
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print("에러: 날짜 형식이 잘못되었습니다 (YYYY-MM-DD 필요)")
            return

    # 3. 처리할 프로필 결정
    if args.report == "all":
        profiles = [config.sph]
        if biviz_available:
            profiles.append(config.biviz)
    else:
        profiles = [config.get_profile(args.report)]

    # 4. 각 프로필 순차 실행 (한쪽 실패해도 다른 쪽 계속)
    for profile in profiles:
        try:
            orch = Orchestrator(config, profile)
            orch.run(target_monday=target_date, dry_run=args.dry_run)
        except Exception as e:
            log.error(
                f"[{profile.name}] 리포트 실행 중 예외: {e}", exc_info=True,
            )


if __name__ == "__main__":
    main()
