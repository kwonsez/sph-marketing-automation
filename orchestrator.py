"""
중앙 실행 로직 (Orchestrator)
============================
1. 날짜 계산 -> 2. 데이터 수집 -> 3. Monday.com 기록 (upsert) -> 4. 이메일 알림

ReportProfile을 받아 SPH/BIVIZ 등 여러 리포트를 동일한 흐름으로 처리한다.
프로필별로 사용하는 collector(광고/블로그)와 컬럼 매핑이 다르다.
"""

import logging
from datetime import datetime

from collectors.ga4 import GA4Collector
from collectors.google_ads import GoogleAdsCollector
from collectors.naver_ads import NaverAdsCollector
from collectors.naver_blog import NaverBlogCollector
from collectors.monday_lead import MondayLeadCollector
from collectors.base import NaverBlogError
from config import AppConfig, ReportProfile
from notifiers.gmail_notifier import GmailNotifier
from utils import week_calc
from writers.monday_writer import MondayWriter


class Orchestrator:
    def __init__(self, app_config: AppConfig, profile: ReportProfile):
        self.logger = logging.getLogger(f"orchestrator.{profile.name.lower()}")
        self.profile = profile
        self.app_config = app_config

        # 부품 초기화
        self.writer = MondayWriter(profile.monday)
        self.notifier = GmailNotifier(app_config.gmail)

        # 수집기 리스트 — 프로필 설정에 따라 동적 구성
        self.collectors = [
            GA4Collector(profile.ga4),
            MondayLeadCollector(profile.monday),
        ]
        if profile.use_google_ads:
            self.collectors.append(GoogleAdsCollector(app_config.google_ads))
        if profile.use_naver_ads:
            self.collectors.append(NaverAdsCollector(app_config.naver_ads))
        if profile.use_naver_blog:
            self.collectors.append(NaverBlogCollector(app_config.naver_blog))

    def run(self, target_monday: datetime = None, dry_run: bool = False):
        """전체 자동화 프로세스 실행"""
        # 1. 날짜 설정 (전주 월~일)
        last_mon, last_sun = week_calc.get_last_week_range(target_monday)
        start_str = week_calc.format_start_date(last_mon)
        end_str = week_calc.format_start_date(last_sun)

        week_name = week_calc.build_item_name(last_mon, last_sun)
        tag = f"[{self.profile.name}]"
        self.logger.info(f"🚀 {tag} {week_name} 리포트 자동화 시작")

        all_data = {}

        # 2. 데이터 수집
        for col in self.collectors:
            try:
                self.logger.info(f"{tag} [{col.name}] 수집 중...")
                result = col.collect(start_str, end_str)
                all_data.update(result)
            except NaverBlogError as e:
                # 네이버 블로그는 실패해도 계속 진행 (정책)
                self.logger.warning(f"{tag} 네이버 블로그 수집 실패 (계속 진행): {e}")
                all_data.update({"n_blog_posts": 0, "n_blog_views": 0})
            except Exception as e:
                # 필수 수집기 실패 시 중단 및 이메일 알림
                self.logger.error(f"{tag} 필수 수집기({col.name}) 실패: {e}")
                self.notifier.notify_failure(
                    f"{tag} {week_name}", f"{col.name} 수집 중 치명적 오류: {e}",
                )
                return

        # 3. 건너뛰기 모드 (Dry Run)
        if dry_run:
            self._log_dry_run_summary(week_name, all_data)
            return

        try:
            # 4. Monday.com 기록 (동일 주차 아이템 있으면 덮어쓰기, 없으면 신규)
            result = self.writer.write(last_mon, last_sun, all_data)
            item_id = result["item_id"]
            was_update = result["was_update"]

            # 5. 성공 알림 발송 (프로필명 prefix 추가)
            self.notifier.notify_success(
                f"{tag} {week_name}", all_data, was_update=was_update,
            )
            mode = "업데이트" if was_update else "신규 작성"
            self.logger.info(
                f"✅ {tag} 모든 작업이 성공적으로 완료되었습니다 ({mode}, ID: {item_id})"
            )

        except Exception as e:
            self.logger.error(f"{tag} Monday.com 기록 중 오류: {e}")
            self.notifier.notify_failure(
                f"{tag} {week_name}", f"Monday.com 기록 실패: {e}",
            )

    def _log_dry_run_summary(self, week_name: str, d: dict):
        """Dry-run 요약을 로그로 출력한다. 프로필이 사용하는 데이터만 포함."""
        tag = f"[{self.profile.name}]"
        lines = [f"✨ {tag} Dry Run 완료 [{week_name}]"]

        wau = d.get("wau", "-")
        contact = d.get("contact_users", "-")
        wau_s = f"{wau:>6,}" if isinstance(wau, int) else str(wau)
        contact_s = f"{contact:>4,}" if isinstance(contact, int) else str(contact)
        lines.append(f"  ├ GA4          WAU {wau_s}  |  신청문의 {contact_s}")

        if self.profile.use_google_ads:
            lines.append(
                f"  ├ Google Ads   노출 {d.get('g_impressions', '-'):>6,}  |  "
                f"클릭 {d.get('g_clicks', '-'):>4,}  |  비용 {d.get('g_cost', '-'):>7,}원"
            )
        if self.profile.use_naver_ads:
            lines.append(
                f"  ├ Naver Ads    노출 {d.get('n_impressions', '-'):>6,}  |  "
                f"클릭 {d.get('n_clicks', '-'):>4,}  |  비용 {d.get('n_cost', '-'):>7,}원"
            )

        lines.append(f"  ├ Lead Gen     {d.get('lead_gen', '-')}건")

        if self.profile.use_naver_blog:
            views = d.get("n_blog_views", "-")
            views_s = f"{views:,}" if isinstance(views, int) else str(views)
            lines.append(
                f"  └ Naver Blog   포스팅 {d.get('n_blog_posts', '-')}건  |  조회수 {views_s}"
            )

        self.logger.info("\n".join(lines))
