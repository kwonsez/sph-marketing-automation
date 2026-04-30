"""
Gmail 알림 발송기
================
성공, 실패, 중복 상황에 따라 이메일을 발송한다.
smtplib와 Gmail 앱 비밀번호를 사용한다.
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import GmailConfig

class GmailNotifier:
    def __init__(self, config: GmailConfig):
        self.logger = logging.getLogger("notifier.gmail")
        self.sender = config.sender
        self.password = config.app_password
        self.recipients = config.recipients

    def _send_email(self, subject: str, html_content: str):
        """SMTP를 통해 이메일을 실제로 발송한다. 수신자가 여러 명이면 모두에게 발송한다."""
        if not self.sender or not self.password:
            self.logger.warning("Gmail 설정이 누락되어 알림을 보낼 수 없습니다.")
            return
        if not self.recipients:
            self.logger.warning("Gmail 수신자가 설정되지 않아 알림을 보낼 수 없습니다.")
            return

        msg = MIMEMultipart()
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.sender, self.password)
                server.send_message(msg, to_addrs=self.recipients)
            self.logger.info(f"이메일 발송 완료 ({len(self.recipients)}명): {subject}")
        except Exception as e:
            self.logger.error(f"이메일 발송 실패: {e}")

    def notify_success(self, week_name: str, data: dict, was_update: bool = False):
        """성공 알림을 보낸다.

        Args:
            week_name: 대상 주차 이름.
            data: 입력된 데이터 딕셔너리.
            was_update: True면 기존 아이템 덮어쓰기, False면 신규 생성.
        """
        if was_update:
            subject = f"🔄 [업데이트] {week_name} 마케팅 리포트 덮어쓰기 완료"
        else:
            subject = f"✅ [성공] {week_name} 마케팅 리포트 자동화 완료"
        
        rows = ""
        for key, value in data.items():
            # 숫자인 경우 콤마 포맷팅, 아닌 경우 그대로 출력
            val_str = f"{value:,}" if isinstance(value, (int, float)) else str(value)
            rows += f"<tr><td style='padding:8px; border:1px solid #ddd;'>{key}</td>"
            rows += f"<td style='padding:8px; border:1px solid #ddd;'>{val_str}</td></tr>"

        html = f"""
        <html>
        <body>
            <h2>📊 {week_name} 리포트 작성 완료</h2>
            <p>Monday.com 보드에 데이터가 성공적으로 기록되었습니다.</p>
            <table style='border-collapse: collapse; width: 100%; max-width: 400px;'>
                <thead>
                    <tr style='background-color: #f2f2f2;'>
                        <th style='padding:8px; border:1px solid #ddd;'>항목</th>
                        <th style='padding:8px; border:1px solid #ddd;'>수치</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            <p><a href="https://sph-marketing.monday.com/boards/1901011628">보드 바로가기</a></p>
        </body>
        </html>
        """
        self._send_email(subject, html)

    def notify_failure(self, week_name: str, error_msg: str):
        """실패 알림을 보낸다."""
        subject = f"❌ [실패] {week_name} 마케팅 리포트 자동화 오류"
        html = f"""
        <html>
        <body>
            <h2 style='color: red;'>⚠️ 리포트 작성 중 오류 발생</h2>
            <p><b>대상 주차:</b> {week_name}</p>
            <p><b>에러 내용:</b> {error_msg}</p>
            <p>로그를 확인하여 조치가 필요합니다.</p>
        </body>
        </html>
        """
        self._send_email(subject, html)

    def notify_combined(self, results: list[dict]):
        """여러 프로필 결과를 한 통의 메일로 발송한다.

        Args:
            results: Orchestrator.run()이 반환한 결과 dict 리스트.
                     각 dict는 profile_name, week_name, success, data, item_id,
                     was_update, error 키를 가진다.
        """
        if not results:
            self.logger.warning("발송할 결과가 없습니다.")
            return

        week_name = results[0].get("week_name", "?")
        all_success = all(r["success"] for r in results)
        any_success = any(r["success"] for r in results)

        if all_success:
            prefix = "✅ [성공]"
            heading = "리포트 작성 완료"
            color = "#2e7d32"
        elif any_success:
            prefix = "⚠️ [일부 실패]"
            heading = "일부 리포트 작성 실패"
            color = "#ef6c00"
        else:
            prefix = "❌ [실패]"
            heading = "리포트 작성 실패"
            color = "#c62828"

        subject = f"{prefix} {week_name} 마케팅 리포트 자동화"

        sections = ""
        for r in results:
            sections += self._render_profile_section(r)

        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
            <h2 style="color: {color};">📊 {heading}</h2>
            <p><b>대상 주차:</b> {week_name}</p>
            {sections}
        </body>
        </html>
        """
        self._send_email(subject, html)

    def _render_profile_section(self, r: dict) -> str:
        """단일 프로필 결과를 HTML 섹션으로 렌더링한다."""
        profile = r.get("profile_name", "?")
        if r["success"]:
            mode = "🔄 업데이트" if r.get("was_update") else "✅ 신규 작성"
            item_id = r.get("item_id", "")
            id_text = f" (ID: {item_id})" if item_id else ""
            status_html = f"<span style='color:#2e7d32;'>{mode}{id_text}</span>"

            data = r.get("data") or {}
            rows = ""
            for key, value in data.items():
                val_str = f"{value:,}" if isinstance(value, (int, float)) else str(value)
                rows += (
                    f"<tr><td style='padding:6px 10px; border:1px solid #ddd;'>{key}</td>"
                    f"<td style='padding:6px 10px; border:1px solid #ddd;'>{val_str}</td></tr>"
                )
            table = (
                "<table style='border-collapse: collapse; margin-top:8px;'>"
                "<thead><tr style='background:#f5f5f5;'>"
                "<th style='padding:6px 10px; border:1px solid #ddd;'>항목</th>"
                "<th style='padding:6px 10px; border:1px solid #ddd;'>수치</th>"
                f"</tr></thead><tbody>{rows}</tbody></table>"
            )
        else:
            status_html = "<span style='color:#c62828;'>❌ 실패</span>"
            err = r.get("error") or "알 수 없는 에러"
            table = f"<p style='color:#c62828; margin-top:6px;'><b>에러:</b> {err}</p>"

        return f"""
        <div style="margin: 20px 0; padding: 12px; border-left: 3px solid #999;">
            <h3 style="margin: 0 0 8px 0;">[{profile}] {status_html}</h3>
            {table}
        </div>
        """

    def notify_duplicate(self, week_name: str):
        """중복 생성 알림을 보낸다."""
        subject = f"⚠️ [중복] {week_name} 리포트 중복 생성 알림"
        html = f"""
        <html>
        <body>
            <h2 style='color: orange;'>ℹ️ 중복 데이터 감지</h2>
            <p><b>대상 주차:</b> {week_name}</p>
            <p>해당 주차의 아이템이 이미 보드에 존재합니다.</p>
            <p>새로운 아이템이 추가로 생성되었으니, 보드에서 확인 후 필요 없는 항목은 삭제해 주세요.</p>
            <p><a href="https://sph-marketing.monday.com/boards/1901011628">보드 바로가기</a></p>
        </body>
        </html>
        """
        self._send_email(subject, html)