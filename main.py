"""
Weekly Report Automation - CLI Entry Point
"""

import argparse
import logging
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
        logging.FileHandler("automation.log", encoding="utf-8")
    ]
)

def main():
    parser = argparse.ArgumentParser(description="Weekly Marketing Report Automation")
    parser.add_argument("--date", type=str, help="대상 주차 월요일 날짜 (YYYY-MM-DD). 생략 시 지난주 자동 계산.")
    parser.add_argument("--dry-run", action="store_true", help="Monday.com에 쓰지 않고 수집 테스트만 수행")
    
    args = parser.parse_args()

    # 1. 설정 로드
    config = load_config()
    
    # 2. 오케스트레이터 실행
    orch = Orchestrator(config)
    
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print("에러: 날짜 형식이 잘못되었습니다 (YYYY-MM-DD 필요)")
            return

    orch.run(target_monday=target_date, dry_run=args.dry_run)

if __name__ == "__main__":
    main()