#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re

WHITESPACE_RE = re.compile(r"\s+")

# Normalize various Unicode dash characters to ASCII hyphen to avoid
# near-duplicate titles caused by typography differences.
_DASH_TRANSLATION = str.maketrans(
    {
        "–": "-",  # en dash
        "—": "-",  # em dash
        "‑": "-",  # non-breaking hyphen
        "−": "-",  # minus sign
        "―": "-",  # horizontal bar
    }
)

# Cross-platform filesystem-unsafe characters (esp. Windows) that may appear
# in product titles/subtitles on the store site.
_FS_UNSAFE_TRANSLATION = str.maketrans(
    {
        "/": "／",
        "\\": "＼",
        ":": "：",
        "*": "＊",
        "?": "？",
        '"': "＂",
        "<": "＜",
        ">": "＞",
        "|": "｜",
    }
)


def sanitize_title_for_fs(title: str) -> str:
    return (title or "").translate(_DASH_TRANSLATION).translate(_FS_UNSAFE_TRANSLATION)


_MEDIA_UNIT_RE = re.compile(r"(?i)(\d)\s+(CD|SACD|DVD|LP)\b")
_MEDIA_PAREN_RE = re.compile(r"(?i)\b(CD|SACD|DVD|LP)\s+\(")


def normalize_title_for_display(title: str) -> str:
    """Normalize a title for display in Markdown.

    Goal: avoid cosmetic inconsistencies caused by scraping/hand edits, e.g.
    - "4 CD" vs "4CD"
    - "CD (Hybrid-SACD)" vs "CD(Hybrid-SACD)"
    - extra spaces around + / ／

    This does NOT aim to be a perfect official-title formatter; it only
    removes common noisy spacing.
    """

    t = sanitize_title_for_fs(title)
    t = WHITESPACE_RE.sub(" ", t).strip()

    # Tighten common separators.
    t = re.sub(r"\s*\+\s*", "+", t)
    t = re.sub(r"\s*／\s*", "／", t)

    # Tighten common Chinese patterns: "2 蓝光" -> "2蓝光".
    t = re.sub(r"(\d)\s+([\u4e00-\u9fff])", r"\1\2", t)

    # Tighten media count patterns.
    t = _MEDIA_UNIT_RE.sub(r"\1\2", t)
    t = _MEDIA_PAREN_RE.sub(lambda m: f"{m.group(1)}(", t)

    return t


def normalize_title_for_dir(title: str) -> str:
    """Normalize a title to a safe folder key.

    - Replaces filesystem-unsafe chars (Windows).
    - Removes whitespace to keep folder names compact.

    Note: This is used both for deriving directory names from titles and for
    computing a stable matching key from existing folder names.
    """

    title = sanitize_title_for_fs(title)
    return WHITESPACE_RE.sub("", title).strip()


def md_link_escape_path(path: str) -> str:
    """Escape characters that can break Markdown links.

    Keep non-ASCII characters as-is for readability and GitHub compatibility,
    but URL-encode characters like parentheses/spaces that can terminate the link.
    """

    return (path or "").replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def get_local_status_by_normalized_title(booklets_dir: str) -> dict[str, tuple[bool, bool, str]]:
    """Return map: normalized_title -> (has_booklet_pdf, has_translation_md, folder_name)."""

    status: dict[str, tuple[bool, bool, str]] = {}

    if not booklets_dir or not os.path.isdir(booklets_dir):
        return status

    for folder_name in os.listdir(booklets_dir):
        folder_path = os.path.join(booklets_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue

        norm = normalize_title_for_dir(folder_name)
        has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
        has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))

        if norm in status:
            prev_pdf, prev_zh, prev_folder = status[norm]
            merged_pdf = has_pdf or prev_pdf
            merged_zh = has_zh or prev_zh
            # Prefer a folder that actually contains something useful.
            if (has_pdf or has_zh) and not (prev_pdf or prev_zh):
                chosen_folder = folder_name
            else:
                chosen_folder = prev_folder
            status[norm] = (merged_pdf, merged_zh, chosen_folder)
        else:
            status[norm] = (has_pdf, has_zh, folder_name)

    return status


def read_purchase_link_from_source(
    booklets_dir: str,
    folder_name: str,
    *,
    require_url: bool = True,
) -> str | None:
    """Read the purchase link recorded in `booklets/<folder>/SOURCE.md`.

    - When `require_url=True` (default), only returns http(s) URLs and ignores placeholders like `待补充`.
    - When `require_url=False`, returns any non-empty value after `- 购买链接：`.
    """

    source_path = os.path.join(booklets_dir, folder_name, "SOURCE.md")
    if not os.path.isfile(source_path):
        return None
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line.startswith("- 购买链接："):
                    continue
                value = line.split("：", 1)[1].strip()
                if not value:
                    return None
                if require_url:
                    if value == "待补充":
                        return None
                    if not (value.startswith("http://") or value.startswith("https://")):
                        return None
                return value
    except Exception:
        return None
    return None


def read_official_title_from_source(booklets_dir: str, folder_name: str) -> str | None:
    """Read an optional official display title override from SOURCE.md.

    Supported keys (first match wins):
    - `- 官方标题：...`
    - `- 官方名称：...`
    - `- 标题：...`
    """

    source_path = os.path.join(booklets_dir, folder_name, "SOURCE.md")
    if not os.path.isfile(source_path):
        return None

    keys = ("- 官方标题：", "- 官方名称：", "- 标题：")
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                for k in keys:
                    if line.startswith(k):
                        title = line.split("：", 1)[1].strip()
                        return title or None
    except Exception:
        return None
    return None
