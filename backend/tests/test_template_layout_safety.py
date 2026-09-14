"""Each uploaded template gets its own Jinja file with distinct starter content."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.template_registry import (  # noqa: E402
    detect_layout_slug,
    infer_upload_layout_slug,
    install_uploaded_jinja_layout,
    resolve_render_layout_slug,
)


@pytest.mark.parametrize(
    "hints, expected",
    [
        (("goran python.pdf", "goran python"), "goran"),
        (("aleksandra python.pdf", "aleksandra python"), "aleksandra"),
        (("Quang Dang Resume.pdf", "Quang Dang Resume"), "quang"),
        (("Mateo_CV.pdf", "Mateo"), "mateo"),
        (("Dejan Pavlovic.pdf", "Dejan Pavlovic"), "dejan"),
        (("My custom sample.pdf", "My custom sample"), ""),
    ],
)
def test_detect_layout_slug_all_on_disk_layouts(hints, expected):
    assert detect_layout_slug(*hints) == expected


def test_infer_goran_and_aleksandra_not_dejan_uploaded():
    assert infer_upload_layout_slug("goran python.pdf", "goran python") == "goran"
    assert infer_upload_layout_slug("aleksandra python.pdf", "aleksandra python") == "aleksandra"
    # Black/white Dejan master CV must not get green dejan
    assert (
        infer_upload_layout_slug(
            "Dejan Pavlovic.pdf",
            "Dejan Pavlovic",
            sample_text="Summary\nSkills & Abilities\nExperience\nStaff | Tech Lead",
        )
        == "uploaded"
    )


def test_resolve_render_layout_slug_uploads_always_own_file():
    for layout in ("uploaded", "goran", "aleksandra", "dejan", "quang", ""):
        template = SimpleNamespace(
            source_path="/tmp/user_templates/1/u1-abc/source.pdf",
            is_builtin=False,
            layout_slug=layout,
            slug="u1-abc",
            name="goran python",
        )
        assert resolve_render_layout_slug(template) == ""


def test_goran_aleksandra_dejan_uploads_get_different_jinja(tmp_path: Path):
    dejan = tmp_path / "dejan_upload"
    goran = tmp_path / "goran_upload"
    aleks = tmp_path / "aleks_upload"
    install_uploaded_jinja_layout(dejan, "uploaded", force=True)
    install_uploaded_jinja_layout(goran, "goran", force=True)
    install_uploaded_jinja_layout(aleks, "aleksandra", force=True)
    d = (dejan / "template.html.jinja2").read_text(encoding="utf-8")
    g = (goran / "template.html.jinja2").read_text(encoding="utf-8")
    a = (aleks / "template.html.jinja2").read_text(encoding="utf-8")
    assert len({d, g, a}) == 3
    assert "Georgia" in g or "#3d6d78" in g
    assert "#2f6b3a" in a or "text-transform: uppercase" in a


def test_delete_user_template_removes_folder_and_jinja(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.db.session import init_db, session_scope
    from app.db.models import ResumeTemplate, User
    from app.services import template_registry as reg

    init_db()
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(reg, "static_dir", lambda: static)
    monkeypatch.setattr(reg, "user_templates_root", lambda: tmp_path / "user_templates")

    with session_scope() as s:
        user = s.query(User).first()
        if user is None:
            user = User(
                name="Test",
                email="t-del@example.com",
                password_hash="x",
                role="user",
                is_approved=True,
            )
            s.add(user)
            s.flush()
        user_id = user.id

    dest = tmp_path / "user_templates" / str(user_id) / "u-del-test"
    dest.mkdir(parents=True)
    (dest / "source.pdf").write_bytes(b"%PDF-1.4")
    install_uploaded_jinja_layout(dest, "uploaded", force=True)
    thumb = static / "template_previews"
    thumb.mkdir(parents=True)
    (thumb / "u-del-test.png").write_bytes(b"png")

    with session_scope() as s:
        s.add(
            ResumeTemplate(
                slug="u-del-test",
                name="To Delete",
                description="x",
                thumbnail_path="template_previews/u-del-test.png",
                is_active=True,
                user_id=user_id,
                is_builtin=False,
                source_path=str((dest / "source.pdf").resolve()),
                layout_slug="uploaded",
                is_default=False,
            )
        )

    reg.delete_user_template(user_id=user_id, slug="u-del-test")
    assert not dest.exists()
    assert not (thumb / "u-del-test.png").exists()
    with session_scope() as s:
        assert s.query(ResumeTemplate).filter_by(slug="u-del-test").one_or_none() is None
