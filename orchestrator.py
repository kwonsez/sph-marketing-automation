"""
중앙 실행 로직 (Orchestrator)
============================
1. 날짜 계산 -> 2. 데이터 수집 -> 3. 중복 체크 -> 4. Monday.com 기록 -> 5. 이메일 알림
"""

import logging
from datetime import datetime
from collectors.ga4 import GA4Collector
from collectors.google_ads import GoogleAdsCollector
from collectors.naver_ads import NaverAdsCollector
from collectors.naver_blog import NaverBlogCollector
from collectors.monday_lead import MondayLeadCollector
from collectors.base import NaverBlogError
from writers.monday_writer import MondayWriter
from notifiers.gmail_notifier import GmailNotifier
from utils import week_calc

class Orchestrator:
    def __init__(self, config):
        self.logger = logging.getLogger("orchestrator")
        self.config = config
        
        # 부품 초기화
        self.writer = MondayWriter(config.monday)
        self.notifier = GmailNotifier(config.gmail)
        
        # 수집기 리스트
        self.collectors = [
            GA4Collector(config.ga4),
            GoogleAdsCollector(config.google_ads),
            NaverAdsCollector(config.naver_ads),
            MondayLeadCollector(config.monday),
            NaverBlogCollector(config.naver_blog)
        ]

    def run(self, target_monday: datetime = None, dry_run: bool = False):
        """전체 자동화 프로세스 실행"""
        # 1. 날짜 설정 (전주 월~일)
        last_mon, last_sun = week_calc.get_last_week_range(target_monday)
        start_str = week_calc.format_start_date(last_mon)
        end_str = week_calc.format_start_date(last_sun) # 일요일도 YYYY-MM-DD 형식
        
        week_name = week_calc.build_item_name(last_mon, last_sun)
        self.logger.info(f"🚀 {week_name} 리포트 자동화 시작")

        all_data = {}
        failed_collectors = []

        # 2. 데이터 수집
        for col in self.collectors:
            try:
                self.logger.info(f"[{col.name}] 수집 중...")
                result = col.collect(start_str, end_str)
                all_data.update(result)
            except NaverBlogError as e:
                # 네이버 블로그는 실패해도 계속 진행 (정책)
                self.logger.warning(f"네이버 블로그 수집 실패 (계속 진행): {e}")
                all_data.update({"n_blog_posts": 0, "n_blog_views": 0})
                failed_collectors.append(col.name)
            except Exception as e:
                # 필수 수집기 실패 시 중단 및 이메일 알림
                self.logger.error(f"필수 수집기({col.name}) 실패: {e}")
                self.notifier.notify_failure(week_name, f"{col.name} 수집 중 치명적 오류: {e}")
                return

        # 3. 건너뛰기 모드 (Dry Run)
        if dry_run:
            d = all_data
            self.logger.info(
                f"✨ Dry Run 완료 [{week_name}]\n"
                f"  ├ GA4          WAU {d.get('wau', '-'):>6,}  |  신청문의 {d.get('contact_users', '-'):>4,}\n"
                f"  ├ Google Ads   노출 {d.get('g_impressions', '-'):>6,}  |  클릭 {d.get('g_clicks', '-'):>4,}  |  비용 {d.get('g_cost', '-'):>7,}원\n"
                f"  ├ Naver Ads    노출 {d.get('n_impressions', '-'):>6,}  |  클릭 {d.get('n_clicks', '-'):>4,}  |  비용 {d.get('n_cost', '-'):>7,}원\n"
                f"  ├ Lead Gen     {d.get('lead_gen', '-')}건\n"
                f"  └ Naver Blog   포스팅 {d.get('n_blog_posts', '-')}건  |  조회수 {d.get('n_blog_views', '-'):,}"
            )
            return

        try:
            # 4. Monday.com 기록 (동일 주차 아이템 있으면 덮어쓰기, 없으면 신규)
            result = self.writer.write(last_mon, last_sun, all_data)
            item_id = result["item_id"]
            was_update = result["was_update"]

            # 5. 성공 알림 발송
            self.notifier.notify_success(week_name, all_data, was_update=was_update)
            mode = "업데이트" if was_update else "신규 작성"
            self.logger.info(f"✅ 모든 작업이 성공적으로 완료되었습니다 ({mode}, ID: {item_id})")

        except Exception as e:
            self.logger.error(f"Monday.com 기록 중 오류: {e}")
            self.notifier.notify_failure(week_name, f"Monday.com 기록 실패: {e}")