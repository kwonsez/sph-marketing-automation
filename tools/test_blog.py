"""
NaverBlogCollector 단독 테스트
실행: python tools/test_blog.py [YYYY-MM-DD]
예)  python tools/test_blog.py 2026-03-22
     python tools/test_blog.py          ← 지난주 자동 계산
"""
import sys, logging, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from config import load_config
from collectors.naver_blog import NaverBlogCollector
from utils.week_calc import get_prev_week_range

config = load_config()

if len(sys.argv) > 1:
    from datetime import datetime
    monday = datetime.strptime(sys.argv[1], "%Y-%m-%d")
    start, end = get_prev_week_range(monday)
else:
    start, end = get_prev_week_range()

print(f"조회 기간: {start} ~ {end}")

collector = NaverBlogCollector(config.naver_blog)
result = collector.collect(start, end)
print(f"결과: {result}")
