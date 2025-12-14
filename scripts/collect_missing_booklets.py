#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Prepare missing booklet folders for items listed in BOOKLETS.md.

This repo treats `booklets/<title>/booklet.pdf` as the *only* input source for
translation.

Important policy:
- Berliner Philharmoniker Recordings product pages often *mention* “Digital
    Booklet/手册”, but the PDF is typically not publicly downloadable via a stable
    direct URL.
- Therefore we *do not* try to auto-download booklet PDFs.
- `booklet.pdf` must be collected by maintainers via legitimate means (e.g.
    after purchase/login) and then placed into the corresponding folder.

What this script does:
- Parse BOOKLETS.md for releases.
- For each release where “booklet 已收集” is unchecked, create
    `booklets/<normalized-title>/` and write `SOURCE.md` (purchase link + notes).

Usage:
    python3 scripts/collect_missing_booklets.py

Options:
    --limit N   Only process first N missing items
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from typing import Iterable

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


@dataclass(frozen=True)
class BookletItem:
    title: str
    has_pdf: bool
    purchase_url: str


def parse_booklets_md(lines: Iterable[str]) -> list[BookletItem]:
    items: list[BookletItem] = []

    current_title: str | None = None
    current_has_pdf: bool | None = None
    current_purchase_url: str | None = None

    def flush() -> None:
        nonlocal current_title, current_has_pdf, current_purchase_url
        if current_title and current_has_pdf is not None and current_purchase_url:
            items.append(
                BookletItem(
                    title=current_title.strip(),
                    has_pdf=current_has_pdf,
                    purchase_url=current_purchase_url.strip(),
                )
            )
        current_title = None
        current_has_pdf = None
        current_purchase_url = None

    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("- ") and not line.startswith("- ["):
            flush()
            current_title = line[2:].strip()
            continue

        if current_title is None:
            continue

        m_pdf = re.match(r"\s*- \[(?P<mark>[ xX])\] booklet 已收集\s*$", line)
        if m_pdf:
            current_has_pdf = (m_pdf.group("mark").lower() == "x")
            continue

        m_url = re.match(r"\s*- 购买链接：(?P<url>\S+)\s*$", line)
        if m_url:
            current_purchase_url = m_url.group("url")
            continue

    flush()
    return items


def write_source_md(folder_path: str, title: str, purchase_url: str, note: str) -> None:
    os.makedirs(folder_path, exist_ok=True)
    path = os.path.join(folder_path, "SOURCE.md")
    content = (
        f"# {sanitize_title_for_fs(title)}\n\n"
        f"- 购买链接：{purchase_url}\n"
        f"- 说明：{note}\n"
        "\n"
        "手动收集建议：\n"
        "- 本仓库不通过脚本自动下载 booklet 原件。\n"
        "- 如你已通过合法方式（例如购买并登录）获取到该发行物的 Digital Booklet，请将 PDF 命名为 `booklet.pdf` 并放到本目录。\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only process first N missing items")
    args = ap.parse_args()

    with open(BOOKLETS_MD, "r", encoding="utf-8") as f:
        items = parse_booklets_md(f.readlines())

    missing = [it for it in items if not it.has_pdf]
    if args.limit and args.limit > 0:
        missing = missing[: args.limit]

    if not missing:
        print("No missing booklet.pdf items found.")
        return 0

    os.makedirs(BOOKLETS_DIR, exist_ok=True)

    needs_manual = 0

    for it in missing:
        safe_title = sanitize_title_for_fs(it.title)
        folder_name = normalize_title_for_dir(it.title)
        folder_path = os.path.join(BOOKLETS_DIR, folder_name)
        pdf_path = os.path.join(folder_path, "booklet.pdf")

        if os.path.isfile(pdf_path):
            print(f"[SKIP] already exists: {folder_name}/booklet.pdf")
            continue

        os.makedirs(folder_path, exist_ok=True)

        needs_manual += 1
        write_source_md(
            folder_path,
            safe_title,
            it.purchase_url,
            note="booklet.pdf 需要维护者自行收集并放置（脚本仅生成目录与来源记录）",
        )
        print(f"[MANUAL] prepared source: {folder_name}")

    print("\nSummary:")
    print(f"- processed missing: {len(missing)}")
    print(f"- needs manual: {needs_manual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
