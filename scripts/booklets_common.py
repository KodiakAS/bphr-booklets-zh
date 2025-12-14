#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re

WHITESPACE_RE = re.compile(r"\s+")

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
    return (title or "").translate(_FS_UNSAFE_TRANSLATION)


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
