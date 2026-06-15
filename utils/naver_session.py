"""네이버 세션 상태 점검 유틸리티
===============================
네이버 로그인 세션(naver_session.json)의 만료 임박 여부를 판단한다.

세션 쿠키(NID_SES)는 '로그인 상태 유지' 여부에 따라
  - 고정 만료일이 있을 수도 있고(예: 발급 후 30일),
  - 만료일이 없는 순수 세션 쿠키일 수도 있다.
두 경우를 모두 처리한다:
  - 고정 만료일 있음 → 만료일까지 남은 일수로 판단
  - 고정 만료일 없음 → 파일 수정 시각(=발급 시점) 기준 경과일로 추정
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
logger = logging.getLogger("naver_session")

REFRESH_HINT = "`python tools/save_naver_session.py`로 세션을 재발급하세요."


@dataclass
class SessionHealth:
    """세션 상태 점검 결과.

    Attributes:
        status: "ok" | "warn" | "expired" | "missing"
        message: 사람이 읽을 안내 문구.
        days_left: 고정 만료일 기준 남은 일수. 만료일이 없으면 None.
    """

    status: str
    message: str
    days_left: int | None

    @property
    def needs_attention(self) -> bool:
        """경고/만료/없음 등 조치가 필요한 상태인지 여부."""
        return self.status != "ok"


def check_session_health(
    session_path: str = "naver_session.json",
    warn_days: int = 7,
    max_age_days: int = 25,
) -> SessionHealth:
    """네이버 세션 파일의 만료 임박 여부를 점검한다.

    Args:
        session_path: 세션 파일 경로.
        warn_days: 고정 만료일 기준, 만료까지 이 일수 이하로 남으면 경고.
        max_age_days: 만료일 없는 세션 쿠키일 때, 발급 후 이 일수 이상 경과하면 경고.

    Returns:
        SessionHealth(status, message, days_left)
    """
    if not os.path.exists(session_path):
        return SessionHealth(
            "missing",
            f"네이버 세션 파일이 없습니다. {REFRESH_HINT}",
            None,
        )

    now = datetime.now(KST)
    try:
        with open(session_path, encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError) as e:
        return SessionHealth("missing", f"세션 파일을 읽을 수 없습니다: {e}", None)

    cookies = data.get("cookies", [])
    target = next((c for c in cookies if c.get("name") == "NID_SES"), None)

    if target is None:
        return SessionHealth(
            "expired",
            f"세션 쿠키(NID_SES)가 없습니다. {REFRESH_HINT}",
            None,
        )

    expires = target.get("expires", -1)

    # 1) 고정 만료일이 있는 경우 — 남은 일수로 판단
    if expires and expires > 0:
        exp_dt = datetime.fromtimestamp(expires, KST)
        days_left = (exp_dt - now).days
        if days_left < 0:
            return SessionHealth(
                "expired",
                f"네이버 세션이 만료되었습니다 ({exp_dt:%Y-%m-%d}). {REFRESH_HINT}",
                days_left,
            )
        if days_left <= warn_days:
            return SessionHealth(
                "warn",
                f"네이버 세션이 약 {days_left}일 후 만료됩니다 ({exp_dt:%Y-%m-%d}). "
                f"미리 {REFRESH_HINT}",
                days_left,
            )
        return SessionHealth(
            "ok",
            f"세션 유효 (만료 {exp_dt:%Y-%m-%d}, 약 {days_left}일 남음).",
            days_left,
        )

    # 2) 만료일 없는 세션 쿠키 — 발급 후 경과일로 추정 (네이버 세션 약 30일)
    issued = datetime.fromtimestamp(os.path.getmtime(session_path), KST)
    age_days = (now - issued).days
    if age_days >= max_age_days:
        return SessionHealth(
            "warn",
            f"네이버 세션 발급 후 약 {age_days}일 경과 (약 30일 후 만료 추정). "
            f"곧 만료될 수 있으니 미리 {REFRESH_HINT}",
            None,
        )
    return SessionHealth("ok", f"세션 유효 (발급 후 약 {age_days}일).", None)
