"""Regression: private uploads must never remap onto another person's layout."""
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
    resolve_render_layout_slug,
)


@pytest.mark.parametrize(
    "hints",
    [
        ("Dejan Pavlovic.pdf", "Dejan Pavlovic"),
        ("Quang Dang Resume.pdf", "Quang Dang Resume"),
        ("Mateo_CV.pdf", "Mateo"),
        ("Nemanja sample.docx", "Nemanja"),
        ("Marek_template.pdf", "Marek"),
        ("My_mateo_notes.pdf", "notes"),
    ],
)
def test_detect_layout_slug_never_infers_from_names(hints):
    assert detect_layout_slug(*hints) == ""


def test_resolve_render_layout_slug_uploads_always_empty():
    for layout in ("uploaded", "dejan", "quang", "mateo", "marek", "nemanja", ""):
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
    resolved = resolve_render_layout_slug(template)
    assert resolved in ("quang", "")
    # If on-disk quang layout exists, it must resolve to quang.
    from app.services.template_registry import list_jinja_layout_slugs

    if "quang" in list_jinja_layout_slugs():
        assert resolved == "quang"
