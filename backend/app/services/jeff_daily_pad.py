"""Daily application padding for one privileged account only.

If that user's UTC-day application count is below the threshold, clone
metadata from ~one week earlier (real rows only) as ``is_fake`` records so
the day's total exceeds the target. Fake rows appear in Applications history
but are excluded from job-link listing/export.
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
DAILY_THRESHOLD = 80
DAILY_TARGET = 91  # "above 90"


def _utc_day_bounds(day: datetime) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def ensure_jeff_daily_application_pad(*, user_id: int, email: str) -> int:
    """Pad today's applications for the privileged email if below threshold.

    Returns how many fake rows were inserted (0 when no action was taken).
    """
    if (email or "").strip().lower() != PAD_EMAIL.lower():
        return 0

    now = datetime.now(timezone.utc)
    today_start, today_end = _utc_day_bounds(now)
    week_ago = now - timedelta(days=7)
    week_start, week_end = _utc_day_bounds(week_ago)

    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None or (user.email or "").strip().lower() != PAD_EMAIL.lower():
            return 0

        today_count = (
            session.query(ResumeRecord)
            .filter(
                ResumeRecord.user_id == user_id,
                ResumeRecord.created_at >= today_start,
                ResumeRecord.created_at < today_end,
            )
            .count()
        )
        if today_count >= DAILY_THRESHOLD:
            return 0

        needed = DAILY_TARGET - today_count
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
            # Fall back to any prior real applications if that calendar day is empty.
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

        # Snapshot fields before session churn; cycle through week-ago rows.
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

        span_seconds = max(1, int((today_end - today_start).total_seconds()) - 60)
        for index in range(needed):
            src = templates[index % len(templates)]
            # Spread across today so the day looks evenly filled.
            offset = int((index + 1) / (needed + 1) * span_seconds)
            created_at = today_start + timedelta(seconds=offset)
            # Slight jitter so timestamps are not perfectly uniform.
            created_at += timedelta(seconds=random.randint(0, 45))
            if created_at >= today_end:
                created_at = today_end - timedelta(seconds=1)
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
            "Jeff daily pad: inserted %s fake applications for user_id=%s (was %s, target %s)",
            needed,
            user_id,
            today_count,
            DAILY_TARGET,
        )
        return needed
