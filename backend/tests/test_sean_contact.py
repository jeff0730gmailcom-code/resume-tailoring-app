"""Sean-only contact replacement. Other candidates keep their own email and phone."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.constants import SEAN_CONTACT_EMAIL, SEAN_CONTACT_PHONE  # noqa: E402
from app.models.schemas import ContactInfo, MasterCvData, SkillCategories, TailoredResumeContent  # noqa: E402
from app.services.resume_validator import validate_and_fix_resume  # noqa: E402


def _tailored(name: str, email: str, phone: str | None, location: str = "Tavares, FL") -> TailoredResumeContent:
    return TailoredResumeContent(
        contact=ContactInfo(name=name, email=email, phone=phone, location=location),
        summary="Summary.",
        skills=SkillCategories(),
        experience=[],
        education=[],
    )


def _master(name: str) -> MasterCvData:
    return MasterCvData(contact=ContactInfo(name=name, email="old@example.com", phone="000"), is_structured=False)


def test_sean_email_and_phone_are_replaced():
    tailored = _tailored(
        "Sean Johnston",
        "seanjohnston896@gmail.com",
        None,
        location="+1 32778 Tavares, FL, USA",
    )
    validate_and_fix_resume(tailored, _master("Sean Johnston"), None)
    assert tailored.contact.email == SEAN_CONTACT_EMAIL
    assert tailored.contact.phone == "+17723617147"
    assert tailored.contact.location == "32778 Tavares, FL, USA"


def test_other_candidates_keep_their_contact():
    tailored = _tailored("Mateo Baranji", "mateo@example.com", "+10000000000")
    validate_and_fix_resume(tailored, _master("Mateo Baranji"), None)
    assert tailored.contact.email == "mateo@example.com"
    assert tailored.contact.phone == "+10000000000"
