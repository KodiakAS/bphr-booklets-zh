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
import urllib.parse

from booklets_common import (
    get_local_status_by_normalized_title,
    md_link_escape_path,
    normalize_title_for_dir,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKLETS_MD = os.path.join(REPO_ROOT, "BOOKLETS.md")
BOOKLETS_DIR = os.path.join(REPO_ROOT, "booklets")


TITLE_RE = re.compile(r"^- (?!\[)(?P<title>.+?)\s*$")
# Match the whole line and keep only the leading checklist text.
# This makes the updater idempotent even when existing suffix contains nested parentheses
# from Markdown links.
PDF_LINE_RE = re.compile(r"^(?P<indent>\s*)- \[[ xX]\] booklet 已收集.*$")
ZH_LINE_RE = re.compile(r"^(?P<indent>\s*)- \[[ xX]\] 中文翻译已完成.*$")
LEGACY_EXTRA_RE = re.compile(r"^\s*- (目录：|原文：|译文：).*$")

# Extract folder name from existing directory links, if present.
DIR_LINK_RE = re.compile(r"\[目录\]\(booklets/(?P<folder>[^)]+)/\)")

MANUAL_EXPLANATION_TITLE_PREFIXES = (
    "本章节会在重新生成清单时被保留",
    "该章节用于维护",
)


def main() -> int:
    local_status = get_local_status_by_normalized_title(BOOKLETS_DIR)

    with open(BOOKLETS_MD, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out: list[str] = []
    current_norm: str | None = None
    current_folder: str | None = None
    current_has_pdf = False
    current_has_zh = False

    def _decode_folder(md_folder: str) -> str:
        # md_link_escape_path uses percent-encoding for some characters.
        return urllib.parse.unquote(md_folder)

    def _folder_status(folder: str) -> tuple[bool, bool]:
        folder_path = os.path.join(BOOKLETS_DIR, folder)
        has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
        has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))
        return has_pdf, has_zh

    for raw in lines:
        line = raw.rstrip("\n")

        m_title = TITLE_RE.match(line)
        if m_title:
            title = m_title.group("title").strip()
            if any(title.startswith(p) for p in MANUAL_EXPLANATION_TITLE_PREFIXES):
                out.append(raw)
                continue
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
            indent = m_pdf.group("indent")
            folder = current_folder
            if not folder:
                m_dir = DIR_LINK_RE.search(line)
                if m_dir:
                    folder = _decode_folder(m_dir.group("folder"))
                    current_folder = folder
            if folder:
                current_has_pdf, current_has_zh = _folder_status(folder)

            mark = "x" if current_has_pdf else " "
            prefix = f"{indent}- [{mark}] booklet 已收集"
            if current_has_pdf and current_folder:
                folder_md = md_link_escape_path(current_folder)
                suffix = (
                    f" ([目录](booklets/{folder_md}/) · "
                    f"[booklet.pdf](booklets/{folder_md}/booklet.pdf))"
                )
            else:
                suffix = ""
            out.append(prefix + suffix + "\n")
            continue

        m_zh = ZH_LINE_RE.match(line)
        if m_zh:
            indent = m_zh.group("indent")
            folder = current_folder
            if not folder:
                m_dir = DIR_LINK_RE.search(line)
                if m_dir:
                    folder = _decode_folder(m_dir.group("folder"))
                    current_folder = folder
            if folder:
                current_has_pdf, current_has_zh = _folder_status(folder)

            mark = "x" if current_has_zh else " "
            prefix = f"{indent}- [{mark}] 中文翻译已完成"
            if current_has_zh and current_folder:
                folder_md = md_link_escape_path(current_folder)
                suffix = (
                    f" ([目录](booklets/{folder_md}/) · "
                    f"[booklet_zh.md](booklets/{folder_md}/booklet_zh.md))"
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
