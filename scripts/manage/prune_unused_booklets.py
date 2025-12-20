#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Prune unused placeholder folders under booklets/.

After BOOKLETS.md de-duplicates editions (CD/Blu-ray/vinyl), old placeholder
folders may become unused. This script removes booklet folders that:
- are NOT referenced by current BOOKLETS.md title list (by normalized folder name), AND
- do NOT contain any real work product (booklet.pdf or booklet_zh.md).

By default it runs in dry-run mode.

Usage:
  python3 -m scripts.manage.prune_unused_booklets          # dry-run
  python3 -m scripts.manage.prune_unused_booklets --apply # actually delete
"""

from __future__ import annotations

import argparse
import os
import shutil

from .common import (
    BOOKLETS_DIR_PATH,
    BOOKLETS_MD_PATH,
    extract_booklets_md_title_line,
    normalize_title_for_dir,
)

BOOKLETS_MD = BOOKLETS_MD_PATH
BOOKLETS_DIR = BOOKLETS_DIR_PATH


def read_keep_norms() -> set[str]:
    keep: set[str] = set()
    with open(BOOKLETS_MD, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            title = extract_booklets_md_title_line(line)
            if not title:
                continue
            keep.add(normalize_title_for_dir(title))
    return keep


def has_real_files(folder_path: str) -> bool:
    return any(
        os.path.isfile(os.path.join(folder_path, name))
        for name in ("booklet.pdf", "booklet_zh.md", "MANUAL_KEEP")
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
