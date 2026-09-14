"""Each uploaded template keeps its own matched Jinja layout."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.template_registry import (  # noqa: E402
    _layout_jinja_source,
    detect_layout_slug,
    install_uploaded_jinja_layout,
    resolve_render_layout_slug,
)


@pytest.mark.parametrize(
    "hints, expected",
    [
        (("Dejan Pavlovic.pdf", "Dejan Pavlovic"), "dejan"),
        (("Dejan.pdf", "Dejan"), "dejan"),
        (("Quang Dang Resume.pdf", "Quang Dang Resume"), "quang"),
        (("Mateo_CV.pdf", "Mateo"), "mateo"),
        (("Nemanja sample.docx", "Nemanja"), "nemanja"),
        (("Marek_template.pdf", "Marek"), "marek"),
        (("My custom sample.pdf", "My custom sample"), ""),
    ],
)
def test_detect_layout_slug_word_boundary(hints, expected):
    assert detect_layout_slug(*hints) == expected


def test_resolve_render_layout_slug_uploads_use_own_file():
    """Uploads always resolve to '' so render uses the per-folder Jinja copy."""
    for layout in ("uploaded", "dejan", "quang", "mateo", ""):
        template = SimpleNamespace(
            source_path="/tmp/user_templates/1/u1-abc/source.pdf",
            is_builtin=False,
            layout_slug=layout,
            slug="u1-abc",
        )
        assert resolve_render_layout_slug(template) == ""


def test_resolve_render_layout_slug_builtin_uses_slug():
    template = SimpleNamespace(
        source_path=None,
        is_builtin=True,
        layout_slug="quang",
        slug="quang",
    )
    from app.services.template_registry import list_jinja_layout_slugs

    if "quang" in list_jinja_layout_slugs():
        assert resolve_render_layout_slug(template) == "quang"


def test_install_copies_distinct_layouts(tmp_path: Path):
    dejan_dir = tmp_path / "dejan_upload"
    quang_dir = tmp_path / "quang_upload"
    install_uploaded_jinja_layout(dejan_dir, "dejan")
    install_uploaded_jinja_layout(quang_dir, "quang")
    dejan_text = (dejan_dir / "template.html.jinja2").read_text(encoding="utf-8")
    quang_text = (quang_dir / "template.html.jinja2").read_text(encoding="utf-8")
    assert dejan_text != quang_text
    assert "#3a9d51" in dejan_text or "accent-bar" in dejan_text
    assert "#3a738c" in quang_text or "text-align: center" in quang_text
    assert _layout_jinja_source("dejan").name == "template.html.jinja2"
