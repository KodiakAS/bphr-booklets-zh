#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Update BOOKLETS.md by inlining local jump links on completed checklist lines.

Goal:
- Update checklist marks/links based on local filesystem state.
- Keep non-checklist sections intact (header + any following `## ...` sections).
- Merge any local/pinned releases (from `booklets/*/SOURCE.md`) into the main list so
  they won't be lost by automated updates; legacy `## 手工条目` section is removed.
- Re-sort release entries to match the documented ordering rule:
    中文翻译已完成 > booklet 已收集 > 其他；
    同一优先级内按制品标题首字母（首字符）排序。
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
    normalize_title_for_display,
    read_official_title_from_source,
    read_purchase_link_from_source,
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

LEADING_TITLE_TRIM_CHARS = " \t\r\n\u3000\"'“”‘’《》()[]【】{}·•—–-:：/\\"

PDF_CHECK_RE = re.compile(r"^\s*- \[(?P<mark>[ xX])\] booklet 已收集\b")
ZH_CHECK_RE = re.compile(r"^\s*- \[(?P<mark>[ xX])\] 中文翻译已完成\b")
PURCHASE_LINE_RE = re.compile(r"^\s*- 购买链接：(?P<url>.+?)\s*$")
MANUAL_SECTION_RE = re.compile(r"^##\s*手工条目\s*$")
STORE_PARAM = "___store=rec_zh"


def _decode_md_folder(md_folder: str) -> str:
    # md_link_escape_path uses percent-encoding for some characters.
    return urllib.parse.unquote(md_folder)


def _add_store_param(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if STORE_PARAM in url:
        return url
    if "?" in url:
        return url + "&" + STORE_PARAM
    return url + "?" + STORE_PARAM


def _stable_url_key(url: str) -> str:
    return _add_store_param((url or "").strip())


def _strip_blank_lines(lines: list[str]) -> list[str]:
    out = list(lines)
    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()
    return out


def _build_release_block(
    *,
    display_title: str,
    purchase_url: str,
    folder_name: str | None,
    has_pdf: bool,
    has_zh: bool,
) -> list[str]:
    pdf_box = "x" if has_pdf else " "
    zh_box = "x" if has_zh else " "

    lines: list[str] = [f"- {display_title}\n"]

    pdf_link = ""
    zh_link = ""
    if folder_name:
        folder_md = md_link_escape_path(folder_name)
        if has_pdf:
            pdf_link = f" ([目录](booklets/{folder_md}/) · [booklet.pdf](booklets/{folder_md}/booklet.pdf))"
        if has_zh:
            zh_link = f" ([目录](booklets/{folder_md}/) · [booklet_zh.md](booklets/{folder_md}/booklet_zh.md))"

    lines.append(f"  - [{pdf_box}] booklet 已收集{pdf_link}\n")
    lines.append(f"  - [{zh_box}] 中文翻译已完成{zh_link}\n")
    lines.append(f"  - 购买链接：{purchase_url}\n")
    return lines


def _extract_manual_section(suffix: list[str]) -> tuple[list[str], list[str]]:
    """Remove legacy `## 手工条目` section from suffix and return its body lines."""

    start = None
    for i, raw in enumerate(suffix):
        if MANUAL_SECTION_RE.match(raw.rstrip("\n")):
            start = i
            break
    if start is None:
        return suffix, []

    end = len(suffix)
    for j in range(start + 1, len(suffix)):
        if suffix[j].startswith("## "):
            end = j
            break

    manual_body = _strip_blank_lines(suffix[start + 1 : end])
    suffix_wo = suffix[:start] + suffix[end:]
    return suffix_wo, manual_body


def _collect_existing_keys(blocks: list[list[str]]) -> tuple[set[str], set[str], set[str]]:
    existing_norms: set[str] = set()
    existing_url_keys: set[str] = set()
    existing_folders: set[str] = set()

    for block in blocks:
        if not _is_release_block(block):
            continue

        title_line = block[0].rstrip("\n")
        m = TITLE_RE.match(title_line)
        title = m.group("title").strip() if m else title_line.lstrip("- ").strip()
        existing_norms.add(normalize_title_for_dir(title))

        for raw in block:
            line = raw.rstrip("\n")
            m_url = PURCHASE_LINE_RE.match(line)
            if m_url:
                url = m_url.group("url").strip()
                if url.startswith("http://") or url.startswith("https://"):
                    existing_url_keys.add(_stable_url_key(url))
            m_dir = DIR_LINK_RE.search(line)
            if m_dir:
                existing_folders.add(_decode_md_folder(m_dir.group("folder")))

    return existing_norms, existing_url_keys, existing_folders


def _merge_pinned_local_entries(text: str, booklets_dir: str) -> str:
    """Merge local/pinned releases into the main release checklist region."""

    lines = text.splitlines(keepends=True)

    start = None
    for i in range(len(lines)):
        if _is_release_block_start(lines, i):
            start = i
            break
    if start is None:
        return text

    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    prefix = lines[:start]
    body = list(lines[start:end])
    suffix = list(lines[end:])

    suffix, manual_body = _extract_manual_section(suffix)

    # Keep a clean body: no trailing blank lines before adding entries, then ensure a
    # single blank line before the first `##` section.
    while body and body[-1].strip() == "":
        body.pop()
    if manual_body:
        body.extend(manual_body)

    # Parse blocks from body to collect existing keys.
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in body:
        if raw.startswith("- "):
            if current:
                blocks.append(current)
            current = [raw]
            continue
        if not current:
            prefix.append(raw)
            continue
        current.append(raw)
    if current:
        blocks.append(current)

    existing_norms, existing_url_keys, existing_folders = _collect_existing_keys(blocks)

    # Scan local SOURCE.md pinned links and optional official titles.
    url_key_to_folder: dict[str, str] = {}
    folder_to_official: dict[str, str] = {}
    if os.path.isdir(booklets_dir):
        for folder in sorted(os.listdir(booklets_dir)):
            folder_path = os.path.join(booklets_dir, folder)
            if not os.path.isdir(folder_path):
                continue
            official_title = read_official_title_from_source(booklets_dir, folder)
            if official_title:
                folder_to_official[folder] = official_title
            purchase = read_purchase_link_from_source(booklets_dir, folder, require_url=True)
            if not purchase:
                continue
            url_key = _stable_url_key(purchase)
            if url_key not in url_key_to_folder:
                url_key_to_folder[url_key] = folder

    # Build blocks to add: pinned-by-SOURCE first, then local-only (collected/translated).
    to_add: list[str] = []

    for url_key, folder in sorted(url_key_to_folder.items(), key=lambda x: x[0]):
        if url_key in existing_url_keys:
            continue
        if folder in existing_folders:
            continue

        folder_path = os.path.join(booklets_dir, folder)
        has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
        has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))

        official_title = folder_to_official.get(folder)
        display_title = normalize_title_for_display((official_title or folder).strip())
        norm = normalize_title_for_dir(display_title)
        if norm in existing_norms:
            continue

        purchase = read_purchase_link_from_source(booklets_dir, folder, require_url=True)
        url_display = _add_store_param(purchase) if purchase else "待补充"

        block_lines = _build_release_block(
            display_title=display_title,
            purchase_url=url_display,
            folder_name=folder,
            has_pdf=has_pdf,
            has_zh=has_zh,
        )
        to_add.extend(block_lines)
        existing_norms.add(norm)
        existing_folders.add(folder)
        if purchase:
            existing_url_keys.add(url_key)

    if os.path.isdir(booklets_dir):
        for folder in sorted(os.listdir(booklets_dir)):
            folder_path = os.path.join(booklets_dir, folder)
            if not os.path.isdir(folder_path):
                continue

            has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
            has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))
            if not (has_pdf or has_zh):
                continue

            if folder in existing_folders:
                continue

            official_title = read_official_title_from_source(booklets_dir, folder)
            display_title = normalize_title_for_display((official_title or folder).strip())
            norm = normalize_title_for_dir(display_title)
            if norm in existing_norms:
                continue

            purchase = read_purchase_link_from_source(booklets_dir, folder, require_url=True)
            if purchase and _stable_url_key(purchase) in existing_url_keys:
                continue

            block_lines = _build_release_block(
                display_title=display_title,
                purchase_url=_add_store_param(purchase) if purchase else "待补充",
                folder_name=folder,
                has_pdf=has_pdf,
                has_zh=has_zh,
            )
            to_add.extend(block_lines)
            existing_norms.add(norm)
            existing_folders.add(folder)
            if purchase:
                existing_url_keys.add(_stable_url_key(purchase))

    if to_add:
        body.extend(to_add)

    if suffix and suffix[0].startswith("## "):
        # Ensure a single blank line before the first `##` section.
        while body and body[-1].strip() == "":
            body.pop()
        body.append("\n")

    merged = "".join(prefix + body + suffix)
    return merged


def main() -> int:
    local_status = get_local_status_by_normalized_title(BOOKLETS_DIR)
    # Allow matching a title line to a local folder via `SOURCE.md` official title overrides.
    if os.path.isdir(BOOKLETS_DIR):
        for folder_name in os.listdir(BOOKLETS_DIR):
            folder_path = os.path.join(BOOKLETS_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue
            official_title = read_official_title_from_source(BOOKLETS_DIR, folder_name)
            if not official_title:
                continue
            norm = normalize_title_for_dir(official_title)
            if norm in local_status:
                continue
            has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
            has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))
            local_status[norm] = (has_pdf, has_zh, folder_name)

    with open(BOOKLETS_MD, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out: list[str] = []
    current_norm: str | None = None
    current_folder: str | None = None
    current_has_pdf = False
    current_has_zh = False

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
                    folder = _decode_md_folder(m_dir.group("folder"))
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
                    folder = _decode_md_folder(m_dir.group("folder"))
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
    new_text = _merge_pinned_local_entries(new_text, BOOKLETS_DIR)
    new_text = _sort_booklets_checklist_blocks(new_text)
    with open(BOOKLETS_MD, "w", encoding="utf-8") as f:
        f.write(new_text)

    print("Updated BOOKLETS.md inline links based on local files.")
    return 0


def completion_rank(has_pdf: bool, has_zh: bool) -> int:
    """Ranking for checklist ordering.

    0: translation done
    1: booklet collected
    2: others
    """

    if has_zh:
        return 0
    if has_pdf:
        return 1
    return 2


def title_initial_key(title: str) -> tuple[str, str]:
    """Sort key for '按首字母（首字符）' ordering.

    - Trims common leading punctuation/quotes.
    - Uses A-Z for ASCII letters.
    - Uses '#' for digits.
    - Otherwise uses the first remaining character as a bucket.

    Returns: (bucket, full_title_key)
    """

    t = (title or "").strip().lstrip(LEADING_TITLE_TRIM_CHARS)
    if not t:
        return ("~", "")

    first = t[0]
    if "A" <= first <= "Z" or "a" <= first <= "z":
        bucket = first.upper()
    elif first.isdigit():
        bucket = "#"
    else:
        bucket = first

    return (bucket, t.casefold())


def _is_release_block_start(lines: list[str], idx: int) -> bool:
    if not (0 <= idx < len(lines)):
        return False
    line = lines[idx].rstrip("\n")
    m = TITLE_RE.match(line)
    if not m:
        return False
    title = m.group("title").strip()
    if any(title.startswith(p) for p in MANUAL_EXPLANATION_TITLE_PREFIXES):
        return False

    # A release entry is followed by indented checklist lines.
    j = idx + 1
    while j < len(lines):
        if lines[j].startswith("## "):
            return False
        if lines[j].strip() == "":
            j += 1
            continue
        return bool(PDF_CHECK_RE.match(lines[j].rstrip("\n")))
    return False


def _is_release_block(block: list[str]) -> bool:
    for raw in block:
        line = raw.rstrip("\n")
        if PDF_CHECK_RE.match(line):
            return True
    return False


def _block_status(block: list[str]) -> tuple[bool, bool]:
    has_pdf = False
    has_zh = False
    for raw in block:
        line = raw.rstrip("\n")
        m_pdf = PDF_CHECK_RE.match(line)
        if m_pdf:
            has_pdf = m_pdf.group("mark").strip().lower() == "x"
            continue
        m_zh = ZH_CHECK_RE.match(line)
        if m_zh:
            has_zh = m_zh.group("mark").strip().lower() == "x"
            continue
    return has_pdf, has_zh


def _block_sort_key(block: list[str]) -> tuple[int, tuple[str, str], str]:
    title_line = block[0].rstrip("\n")
    m = TITLE_RE.match(title_line)
    title = m.group("title").strip() if m else title_line.lstrip("- ").strip()
    has_pdf, has_zh = _block_status(block)
    return (
        completion_rank(has_pdf, has_zh),
        title_initial_key(title),
        normalize_title_for_dir(title),
    )


def _sort_booklets_checklist_blocks(text: str) -> str:
    """Sort release entries in BOOKLETS.md by status + title initial.

    Only reorders the main release checklist block region (the `- <title>` items),
    leaving the header and any following `## ...` sections (e.g. errors) intact.
    """

    lines = text.splitlines(keepends=True)
    start = None
    for i in range(len(lines)):
        if _is_release_block_start(lines, i):
            start = i
            break
    if start is None:
        return text

    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    prefix = lines[:start]
    body = lines[start:end]
    suffix = lines[end:]

    trailing: list[str] = []
    while body and body[-1].strip() == "":
        trailing.insert(0, body.pop())

    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in body:
        if raw.startswith("- "):
            if current:
                blocks.append(current)
            current = [raw]
            continue
        if not current:
            prefix.append(raw)
            continue
        current.append(raw)
    if current:
        blocks.append(current)

    # Avoid stray blank lines between release entries by stripping trailing blank
    # lines inside each release block (a single blank line before the first `##`
    # section is handled by `trailing`).
    for block in blocks:
        if _is_release_block(block):
            while block and block[-1].strip() == "":
                block.pop()

    sorted_blocks: list[list[str]] = []
    segment: list[list[str]] = []
    for block in blocks:
        if _is_release_block(block):
            segment.append(block)
            continue
        if segment:
            sorted_blocks.extend(sorted(segment, key=_block_sort_key))
            segment = []
        sorted_blocks.append(block)
    if segment:
        sorted_blocks.extend(sorted(segment, key=_block_sort_key))

    out_lines = prefix + [line for block in sorted_blocks for line in block] + trailing + suffix
    return "".join(out_lines)


if __name__ == "__main__":
    raise SystemExit(main())
