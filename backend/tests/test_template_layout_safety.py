"""Each uploaded template owns its Jinja file; selection always uses that file."""
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
    "hints",
    [
        ("Dejan Pavlovic.pdf", "Dejan Pavlovic"),
        ("Quang Dang Resume.pdf", "Quang Dang Resume"),
        ("Mateo_CV.pdf", "Mateo"),
        ("My custom sample.pdf", "My custom sample"),
    ],
)
def test_detect_layout_slug_never_remaps_uploads(hints):
    assert detect_layout_slug(*hints) == ""


def test_resolve_render_layout_slug_uploads_always_own_file():
    for layout in ("uploaded", "dejan", "quang", "mateo", ""):
        template = SimpleNamespace(
            source_path="/tmp/user_templates/1/u1-abc/source.pdf",
            is_builtin=False,
            layout_slug=layout,
            slug="u1-abc",
            name="Dejan Pavlovic",
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


def test_install_creates_own_jinja_without_overwrite(tmp_path: Path):
    dest = tmp_path / "upload_a"
    path1 = install_uploaded_jinja_layout(dest, "uploaded")
    original = path1.read_text(encoding="utf-8")
    path1.write_text(original + "\n<!-- owned by this upload -->\n", encoding="utf-8")
    path2 = install_uploaded_jinja_layout(dest, "quang")
    assert path1 == path2
    assert "owned by this upload" in path2.read_text(encoding="utf-8")
    assert _layout_jinja_source("uploaded").exists()


def test_two_uploads_get_separate_jinja_files(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    install_uploaded_jinja_layout(a, "uploaded")
    install_uploaded_jinja_layout(b, "uploaded")
    assert (a / "template.html.jinja2").exists()
    assert (b / "template.html.jinja2").exists()
    assert (a / "template.html.jinja2").resolve() != (b / "template.html.jinja2").resolve()
