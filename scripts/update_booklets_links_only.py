#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Update BOOKLETS.md by inlining local jump links on completed checklist lines.

Goal:
- Keep the existing BOOKLETS.md structure.
- For lines like:
    - [x] booklet 已收集
    - [x] 中文翻译已完成
  append relative links when the corresponding local files exist:
    - [x] booklet 已收集 ([booklet.pdf](booklets/<dir>/booklet.pdf))
    - [x] 中文翻译已完成 ([booklet_zh.md](booklets/<dir>/booklet_zh.md))

- Remove legacy extra lines if present:
    - 目录：...
    - 原文：...
    - 译文：...

This script does NOT fetch the network. It only reflects local filesystem state.

Usage:
  python3 scripts/update_booklets_links_only.py
"""

from __future__ import annotations

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKLETS_MD = os.path.join(REPO_ROOT, "BOOKLETS.md")
BOOKLETS_DIR = os.path.join(REPO_ROOT, "booklets")

WHITESPACE_RE = re.compile(r"\s+")

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
    return title.translate(_FS_UNSAFE_TRANSLATION)


def normalize_title_for_dir(title: str) -> str:
    title = sanitize_title_for_fs(title)
    return WHITESPACE_RE.sub("", title).strip()


def get_local_status_by_normalized_title() -> dict[str, tuple[bool, bool, str]]:
    status: dict[str, tuple[bool, bool, str]] = {}
    if not os.path.isdir(BOOKLETS_DIR):
        return status

    for folder_name in os.listdir(BOOKLETS_DIR):
        folder_path = os.path.join(BOOKLETS_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        norm = normalize_title_for_dir(folder_name)
        has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
        has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))

        if norm in status:
            prev_pdf, prev_zh, prev_folder = status[norm]
            merged_pdf = has_pdf or prev_pdf
            merged_zh = has_zh or prev_zh
            if (has_pdf or has_zh) and not (prev_pdf or prev_zh):
                chosen_folder = folder_name
            else:
                chosen_folder = prev_folder
            status[norm] = (merged_pdf, merged_zh, chosen_folder)
        else:
            status[norm] = (has_pdf, has_zh, folder_name)

    return status


TITLE_RE = re.compile(r"^- (?!\[)(?P<title>.+?)\s*$")
# Match the whole line and keep only the leading checklist text.
# This makes the updater idempotent even when existing suffix contains nested parentheses
# from Markdown links.
PDF_LINE_RE = re.compile(r"^(\s*- \[[ xX]\] booklet 已收集).*$")
ZH_LINE_RE = re.compile(r"^(\s*- \[[ xX]\] 中文翻译已完成).*$")
LEGACY_EXTRA_RE = re.compile(r"^\s*- (目录：|原文：|译文：).*$")


def main() -> int:
    local_status = get_local_status_by_normalized_title()

    with open(BOOKLETS_MD, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out: list[str] = []
    current_norm: str | None = None
    current_folder: str | None = None
    current_has_pdf = False
    current_has_zh = False

    for raw in lines:
        line = raw.rstrip("\n")

        m_title = TITLE_RE.match(line)
        if m_title:
            title = m_title.group("title").strip()
            norm = normalize_title_for_dir(title)
            has_pdf, has_zh, folder = local_status.get(norm, (False, False, ""))
            current_norm = norm
            current_folder = folder if folder else None
            current_has_pdf = has_pdf
            current_has_zh = has_zh
            out.append(raw)
            continue

        if LEGACY_EXTRA_RE.match(line):
            # drop legacy extra lines
            continue

        m_pdf = PDF_LINE_RE.match(line)
        if m_pdf:
            prefix = m_pdf.group(1)
            if current_has_pdf and current_folder:
                suffix = (
                    f" ([目录](booklets/{current_folder}/) · "
                    f"[booklet.pdf](booklets/{current_folder}/booklet.pdf))"
                )
            else:
                suffix = ""
            out.append(prefix + suffix + "\n")
            continue

        m_zh = ZH_LINE_RE.match(line)
        if m_zh:
            prefix = m_zh.group(1)
            if current_has_zh and current_folder:
                suffix = (
                    f" ([目录](booklets/{current_folder}/) · "
                    f"[booklet_zh.md](booklets/{current_folder}/booklet_zh.md))"
                )
            else:
                suffix = ""
            out.append(prefix + suffix + "\n")
            continue

        out.append(raw)

    new_text = "".join(out)
    with open(BOOKLETS_MD, "w", encoding="utf-8") as f:
        f.write(new_text)

    print("Updated BOOKLETS.md inline links based on local files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
