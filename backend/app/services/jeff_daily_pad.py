"""Daily application padding for one privileged account only.

Time-of-day fake targets (local pad timezone, weekdays only):
- before 13:00 → 20 fakes for the day
- 13:00–16:00 → 50 fakes
- 16:00–20:00 → hold at 50
- from 20:00 → 80 fakes
- Saturday / Sunday → no padding

Fake rows are cloned from ~one week earlier (real rows only). They appear
in Applications history but are excluded from job-link listing/export.
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import defer

from app.db.models import ResumeRecord, User
from app.db.session import session_scope

logger = logging.getLogger(__name__)

# Exact account this padding applies to — no other user is affected.
PAD_EMAIL = "jeff0730gmail.com@gmail.com"


def _resolve_pad_tz():
    """Prefer Europe/Berlin; fall back to fixed UTC+2 when tzdata is missing."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Berlin")
    except Exception:  # noqa: BLE001 - ZoneInfoNotFoundError / missing tzdata on Windows
        return timezone(timedelta(hours=2))


PAD_TZ = _resolve_pad_tz()


def _pad_now() -> datetime:
    return datetime.now(PAD_TZ)


def fake_target_for_local_time(now_local: datetime) -> int | None:
    """Return today's fake-count target, or None when padding is disabled.

    None = weekend (do not add fakes).
    """
    if now_local.weekday() >= 5:  # Saturday=5, Sunday=6
        return None
    minutes = now_local.hour * 60 + now_local.minute
    if minutes < 13 * 60:  # before 1:00pm
        return 20
    if minutes < 16 * 60:  # 1:00pm to 4:00pm
        return 50
    if minutes < 20 * 60:  # 4:00pm to 8:00pm — hold afternoon tier
        return 50
    return 80  # from 8:00pm


def _local_day_bounds_utc(day_local: datetime) -> tuple[datetime, datetime]:
    """UTC [start, end) covering the local calendar day of ``day_local``."""
    local = day_local.astimezone(PAD_TZ)
    start_local = datetime(local.year, local.month, local.day, tzinfo=PAD_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def ensure_jeff_daily_application_pad(*, user_id: int, email: str) -> int:
    """Top up today's fake applications to the time-based target.

    Returns how many fake rows were inserted (0 when no action was taken).
    """
    if (email or "").strip().lower() != PAD_EMAIL.lower():
        return 0

    now_local = _pad_now()
    target = fake_target_for_local_time(now_local)
    if target is None:
        logger.info("Jeff daily pad skipped: weekend (%s)", now_local.strftime("%A"))
        return 0

    today_start, today_end = _local_day_bounds_utc(now_local)
    week_ago_local = now_local - timedelta(days=7)
    week_start, week_end = _local_day_bounds_utc(week_ago_local)

    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None or (user.email or "").strip().lower() != PAD_EMAIL.lower():
            return 0

        fake_today = (
            session.query(ResumeRecord)
            .filter(
                ResumeRecord.user_id == user_id,
                ResumeRecord.is_fake.is_(True),
                ResumeRecord.created_at >= today_start,
                ResumeRecord.created_at < today_end,
            )
            .count()
        )
        needed = target - fake_today
        if needed <= 0:
            return 0

        sources = (
            session.query(ResumeRecord)
            .options(defer(ResumeRecord.cv_pdf))
            .filter(
                ResumeRecord.user_id == user_id,
                ResumeRecord.is_fake.is_(False),
                ResumeRecord.created_at >= week_start,
                ResumeRecord.created_at < week_end,
            )
            .order_by(ResumeRecord.id.desc())
            .all()
        )
        if not sources:
            sources = (
                session.query(ResumeRecord)
                .options(defer(ResumeRecord.cv_pdf))
                .filter(
                    ResumeRecord.user_id == user_id,
                    ResumeRecord.is_fake.is_(False),
                    ResumeRecord.created_at < today_start,
                )
                .order_by(ResumeRecord.id.desc())
                .limit(50)
                .all()
            )
        if not sources:
            logger.warning(
                "Jeff daily pad skipped: no source history for user_id=%s (need %s more)",
                user_id,
                needed,
            )
            return 0

        templates = [
            {
                "template_id": row.template_id,
                "candidate_name": row.candidate_name,
                "main_stack": row.main_stack,
                "company_name": row.company_name,
                "job_link": getattr(row, "job_link", "") or "",
                "generated_filename": row.generated_filename,
            }
            for row in sources
        ]

        # Spread new fakes across the local day so far (not the whole day),
        # so morning pads don't get timestamps after "now".
        now_utc = now_local.astimezone(timezone.utc)
        span_seconds = max(1, int((now_utc - today_start).total_seconds()) - 60)
        for index in range(needed):
            src = templates[index % len(templates)]
            offset = int((index + 1) / (needed + 1) * span_seconds)
            created_at = today_start + timedelta(seconds=offset)
            created_at += timedelta(seconds=random.randint(0, 45))
            if created_at >= now_utc:
                created_at = now_utc - timedelta(seconds=random.randint(1, 30))
            if created_at < today_start:
                created_at = today_start + timedelta(seconds=1)
            session.add(
                ResumeRecord(
                    file_id=f"fake-{uuid.uuid4().hex}",
                    template_id=src["template_id"],
                    candidate_name=src["candidate_name"],
                    main_stack=src["main_stack"],
                    company_name=src["company_name"],
                    job_link=src["job_link"],
                    generated_filename=src["generated_filename"],
                    cv_pdf=None,
                    cv_saved=False,
                    is_fake=True,
                    created_at=created_at,
                    user_id=user_id,
                )
            )

        logger.info(
            "Jeff daily pad: inserted %s fake applications for user_id=%s "
            "(had %s fakes, target %s at %s)",
            needed,
            user_id,
            fake_today,
            target,
            now_local.strftime("%H:%M %A"),
        )
        return needed
