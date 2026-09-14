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
        (("Dejan Pavlovic.pdf", "Dejan Pavlovic"), ""),
        (("Quang Dang Resume.pdf", "Quang Dang Resume"), "quang"),
        (("Mateo_CV.pdf", "Mateo"), "mateo"),
        (("My custom sample.pdf", "My custom sample"), ""),
    ],
)
def test_detect_layout_slug_builtins_only(hints, expected):
    assert detect_layout_slug(*hints) == expected


def test_infer_upload_layout_slug_quang_vs_dejan():
    assert infer_upload_layout_slug("Quang Dang Resume.pdf", "Quang Dang Resume") == "quang"
    assert infer_upload_layout_slug("Dejan Pavlovic.pdf", "Dejan Pavlovic") == "uploaded"
    assert (
        infer_upload_layout_slug(
            "sample.pdf",
            "sample",
            sample_text="Professional Summary\nWork Experience\nSkill",
        )
        == "quang"
    )


def test_resolve_render_layout_slug_uploads_always_own_file():
    for layout in ("uploaded", "quang", "dejan", ""):
        template = SimpleNamespace(
            source_path="/tmp/user_templates/1/u1-abc/source.pdf",
            is_builtin=False,
            layout_slug=layout,
            slug="u1-abc",
            name="Quang Dang Resume",
        )
        assert resolve_render_layout_slug(template) == ""


def test_quang_and_dejan_uploads_get_different_jinja(tmp_path: Path):
    dejan = tmp_path / "dejan_upload"
    quang = tmp_path / "quang_upload"
    install_uploaded_jinja_layout(dejan, "uploaded", force=True)
    install_uploaded_jinja_layout(quang, "quang", force=True)
    d_text = (dejan / "template.html.jinja2").read_text(encoding="utf-8")
    q_text = (quang / "template.html.jinja2").read_text(encoding="utf-8")
    assert d_text != q_text
    assert "hr.rule" in d_text or "Skills" in d_text
    assert "#3a738c" in q_text or "text-align: center" in q_text


def test_force_reinstall_can_replace_wrong_shared_starter(tmp_path: Path):
    dest = tmp_path / "quang_was_wrong"
    install_uploaded_jinja_layout(dest, "uploaded", force=True)
    before = (dest / "template.html.jinja2").read_text(encoding="utf-8")
    install_uploaded_jinja_layout(dest, "quang", force=True)
    after = (dest / "template.html.jinja2").read_text(encoding="utf-8")
    assert before != after
    assert "#3a738c" in after or "text-align: center" in after


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
            user = User(name="Test", email="t@example.com", password_hash="x", role="user", status="approved")
            s.add(user)
            s.flush()
        user_id = user.id

    dest = tmp_path / "user_templates" / str(user_id) / "u-del-test"
    dest.mkdir(parents=True)
    (dest / "source.pdf").write_bytes(b"%PDF-1.4")
    install_uploaded_jinja_layout(dest, "uploaded", force=True)
    assert (dest / "template.html.jinja2").exists()
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
