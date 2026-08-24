"""Remove extraction glyphs that print as a broken square (□).

Word and PDF bullets often survive as Private Use Area characters
(e.g. U+F0B7 from Wingdings) or geometric squares. Resume template fonts
do not include those glyphs, so Chromium draws a tofu box. Strip the junk
from CV content only — wording and layout stay the same aside from
dropping the glyph and any leftover empty separators.
"""
from __future__ import annotations

import re

_BROKEN_CHAR_RE = re.compile(
    r"["
    r"\ufffd\ufffc\ufeff"  # replacement, object replacement, BOM
    r"\u25a0-\u25ff"  # geometric shapes: □ ■ ▪ ▫ ● ○ …
    r"\u2b1b\u2b1c"  # large black/white squares
    r"\ue000-\uf8ff"  # Private Use Area (Word Symbol/Wingdings bullets)
    r"]+"
)
_CONTROL_EXCEPT_WHITESPACE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_PIPE_RE = re.compile(r"(?:\s*\|\s*){2,}")
_EDGE_SEP_RE = re.compile(r"(?:^(?:\s*[|\u2022•]\s*)+)|(?:(?:\s*[|\u2022•]\s*)+$)")


def strip_broken_characters(text: str) -> str:
    """Drop tofu/replacement/dingbat glyphs and tidy dangling '|' separators."""
    if not text:
        return ""
    cleaned = _BROKEN_CHAR_RE.sub("", text)
    cleaned = _CONTROL_EXCEPT_WHITESPACE.sub("", cleaned)
    cleaned = _MULTI_PIPE_RE.sub(" | ", cleaned)
    cleaned = _EDGE_SEP_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_broken_from_tree(value):
    """Walk strings in a nested dict/list (e.g. model_dump()) and clean each."""
    if isinstance(value, str):
        return strip_broken_characters(value)
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            cleaned = strip_broken_from_tree(item)
            if cleaned == "":
                continue
            cleaned_items.append(cleaned)
        return cleaned_items
    if isinstance(value, dict):
        return {key: strip_broken_from_tree(item) for key, item in value.items()}
    return value
