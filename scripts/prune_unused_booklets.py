#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Prune unused placeholder folders under booklets/.

After BOOKLETS.md de-duplicates editions (CD/Blu-ray/vinyl), old placeholder
folders may become unused. This script removes booklet folders that:
- are NOT referenced by current BOOKLETS.md title list (by normalized folder name), AND
- do NOT contain any real work product (booklet.pdf or booklet_zh.md).

By default it runs in dry-run mode.

Usage:
  python3 scripts/prune_unused_booklets.py          # dry-run
  python3 scripts/prune_unused_booklets.py --apply # actually delete
"""

from __future__ import annotations

import argparse
import os
import re
import shutil

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


TITLE_RE = re.compile(r"^- (?!\[)(?P<title>.+?)\s*$")


def read_keep_norms() -> set[str]:
    keep: set[str] = set()
    with open(BOOKLETS_MD, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = TITLE_RE.match(line)
            if not m:
                continue
            title = m.group("title").strip()
            if not title:
                continue
            keep.add(normalize_title_for_dir(title))
    return keep


def has_real_files(folder_path: str) -> bool:
    return any(
        os.path.isfile(os.path.join(folder_path, name))
        for name in ("booklet.pdf", "booklet_zh.md")
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete folders")
    args = ap.parse_args()

    if not os.path.isdir(BOOKLETS_DIR):
        print("No booklets/ directory.")
        return 0

    keep_norms = read_keep_norms()

    removed: list[str] = []
    kept_real: list[str] = []
    kept_listed: list[str] = []

    for name in sorted(os.listdir(BOOKLETS_DIR)):
        if name.startswith("."):
            continue
        path = os.path.join(BOOKLETS_DIR, name)
        if not os.path.isdir(path):
            continue

        if has_real_files(path):
            kept_real.append(name)
            continue

        norm = normalize_title_for_dir(name)
        if norm in keep_norms:
            kept_listed.append(name)
            continue

        removed.append(name)
        if args.apply:
            shutil.rmtree(path)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Kept (has booklet.pdf/booklet_zh.md): {len(kept_real)}")
    print(f"Kept (still listed in BOOKLETS.md): {len(kept_listed)}")
    print(f"To remove: {len(removed)}")
    for n in removed[:50]:
        print(f"- {n}")
    if len(removed) > 50:
        print(f"... ({len(removed)-50} more)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
