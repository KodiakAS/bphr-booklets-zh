#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Generate a Markdown checklist of Berliner Philharmoniker Recordings releases that include booklets.

Data source:
- Official sitemap: https://www.berliner-philharmoniker-recordings.com/sitemap.xml

Heuristics:
- Treat pages that contain a strong-tagged "Digital Booklet" or "Booklet" as having a booklet.
- Derive a Chinese directory/display name from the on-page "product-title" plus subtitle if present.
- Mark as translated when `booklets/<name>/booklet_zh.md` exists.

Local status:
- "booklet 已收集" when `booklets/<name>/booklet.pdf` exists.

Usage:
  python3 scripts/generate_booklet_checklist.py

Outputs:
- BOOKLETS.md (repo root)
"""

from __future__ import annotations

import argparse
import sys
import html as htmlmod
import datetime as dt
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

SITEMAP_URL = "https://www.berliner-philharmoniker-recordings.com/sitemap.xml"
STORE_PARAM = "___store=rec_zh"
OUTPUT_FILE = "BOOKLETS.md"

PRODUCT_TITLE_RE = re.compile(r'class="product-title"[^>]*>\s*([^<]+?)\s*</h3>', re.I)
PRODUCT_SUBTITLE_RE = re.compile(r'class="product-subtitle"[^>]*>\s*([^<]+?)\s*</p>', re.I)
SUBTITLE_LIGHT_RE = re.compile(r'class="subtitle\s+light"[^>]*>\s*([^<]+?)\s*</span>', re.I)

PRODUCT_TITLE_SUBTITLE_PAIR_RE = re.compile(
    r'<h3\s+class="product-title"[^>]*>\s*([^<]+?)\s*</h3>\s*<p\s+class="product-subtitle"[^>]*>\s*([^<]+?)\s*</p>',
    re.I,
)

BOOKLET_MARK_RE = re.compile(r"<(?:strong|b)>\s*(?:Digital\s+Booklet|Booklet|手册)\s*</(?:strong|b)>", re.I)

# Extract booklet page counts like "76 pages" or "76页" near booklet labels.
BOOKLET_PAGES_RE = re.compile(
    r"<(?:strong|b)>\s*(?:Digital\s+Booklet|数字手册|手册|Booklet)\s*</(?:strong|b)>\s*<br[^>]*>\s*[^\d]{0,40}?(\d{1,4})\s*(?:pages|页)\b",
    re.I,
)

PRICE_RE = re.compile(
    r"<span\s+class=\"price\">\s*US\$\s*&?\s*([0-9]+(?:\.[0-9]+)?)\s*</span>",
    re.I,
)

DOWNLOAD_URL_HINT_RE = re.compile(r"(?:^|/)[^/]*(?:24-bit-)?download[^/]*\.html(?:\?|$)", re.I)
PHYSICAL_HINT_RE = re.compile(r"(CD|DVD|Blu-?ray|SACD|黑胶|唱片|蓝光)")
DOWNLOAD_NAME_HINT_RE = re.compile(r"(?:\bdownload\b|24-bit|下载)", re.I)

NON_RECORDING_URL_HINT_RE = re.compile(
    r"(?:^|/)(?:gift-ideas|audio|video|books)\.html(?:\?|$)|(?:^|/)sbph-|thermos|flask|pen-|lamy-|dch-card|xmasticketdvd",
    re.I,
)

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
    return title.translate(_FS_UNSAFE_TRANSLATION)


def curl(url: str) -> str:
    # Avoid hanging forever on a single slow/broken page.
    base_cmd = [
        "curl",
        "-L",
        "--silent",
        "--show-error",
        "--fail",
        "--connect-timeout",
        "5",
        "--max-time",
        "12",
        url,
    ]

    def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )

    result = run(base_cmd, timeout=18)
    if result.returncode == 0:
        return result.stdout

    stderr_lines = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
    if stderr_lines and all(line == stderr_lines[0] for line in stderr_lines):
        stderr = stderr_lines[0]
    else:
        stderr = " ".join(stderr_lines).strip()

    # Don't retry hard 404s.
    if "returned error: 404" in stderr:
        raise RuntimeError(stderr or f"curl failed: {url}")

    # One targeted retry for transient TLS issues seen on this site.
    if "ssl" in stderr.lower() or "SSL_connect" in stderr:
        retry_cmd = [
            "curl",
            "-L",
            "--silent",
            "--show-error",
            "--fail",
            "--http1.1",
            "--connect-timeout",
            "10",
            "--max-time",
            "18",
            url,
        ]
        retry = run(retry_cmd, timeout=25)
        if retry.returncode == 0:
            return retry.stdout

        retry_lines = [line.strip() for line in (retry.stderr or "").splitlines() if line.strip()]
        if retry_lines and all(line == retry_lines[0] for line in retry_lines):
            stderr = retry_lines[0]
        else:
            stderr = " ".join(retry_lines).strip() or stderr

    raise RuntimeError(stderr or f"curl failed: {url}")


def clean_text(text: str) -> str:
    text = htmlmod.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title_for_dir(title: str) -> str:
    # Make titles usable as directory names across platforms.
    title = sanitize_title_for_fs(title)
    # Remove all whitespace to make the title safe/convenient as a directory name.
    return WHITESPACE_RE.sub("", title).strip()


def add_store_param(url: str) -> str:
    if STORE_PARAM in url:
        return url
    if "?" in url:
        return url + "&" + STORE_PARAM
    return url + "?" + STORE_PARAM


def should_skip_url_pre_fetch(url: str) -> bool:
    lower_url = url.lower()
    if NON_RECORDING_URL_HINT_RE.search(lower_url):
        return True
    if DOWNLOAD_URL_HINT_RE.search(lower_url):
        return True
    return False


def get_translated_names(repo_root: str) -> set[str]:
    translated: set[str] = set()
    booklets_dir = os.path.join(repo_root, "booklets")
    if not os.path.isdir(booklets_dir):
        return translated

    for name in os.listdir(booklets_dir):
        path = os.path.join(booklets_dir, name, "booklet_zh.md")
        if os.path.isfile(path):
            translated.add(name)
    return translated


def get_local_status_by_normalized_title(repo_root: str) -> dict[str, tuple[bool, bool, str]]:
    """Return map: normalized_title -> (has_booklet_pdf, has_translation_md, folder_name)."""

    status: dict[str, tuple[bool, bool, str]] = {}
    booklets_dir = os.path.join(repo_root, "booklets")
    if not os.path.isdir(booklets_dir):
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


def parse_sitemap_locs(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text.strip() for loc in root.findall(".//sm:loc", ns) if loc.text and loc.text.strip()]


ZH_DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
ZH_MONTH_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月")
EN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
EN_MONTH_MAP = {m.lower(): i + 1 for i, m in enumerate(EN_MONTHS)}
EN_DATE_RE_1 = re.compile(
    r"\b(" + "|".join(EN_MONTHS) + r")\s+(\d{1,2}),\s*(\d{4})\b",
    re.I,
)
EN_DATE_RE_2 = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(EN_MONTHS) + r")\s+(\d{4})\b",
    re.I,
)

RELEASE_KEYWORDS_RE = re.compile(
    r"发行|发布|推出|发售|上市|首发|面世|问世|特别发行|release|released|publication|published|available",
    re.I,
)


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except Exception:
        return None


def extract_first_release_date(page_html: str) -> dt.date | None:
    """Best-effort extraction of a 'first release date' from page text.

    The store does not expose a stable dedicated release-date field on the page.
    We therefore look for explicit dates that appear near release-related keywords
    in the product introduction/description.

    If nothing matches confidently, return None.
    """

    if not page_html:
        return None

    candidates: list[tuple[int, dt.date]] = []

    def consider(match_start: int, match_end: int, date: dt.date) -> None:
        window_start = max(0, match_start - 120)
        window_end = min(len(page_html), match_end + 120)
        window = page_html[window_start:window_end]
        kw = RELEASE_KEYWORDS_RE.search(window)
        if not kw:
            return
        # Score by distance from the date match to the nearest keyword occurrence.
        kw_pos = window_start + kw.start()
        score = abs(match_start - kw_pos)
        candidates.append((score, date))

    for m in ZH_DATE_RE.finditer(page_html):
        date = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if date:
            consider(m.start(), m.end(), date)

    # If we don't have a day-level match, allow YYYY年M月 and treat it as the 1st.
    if not candidates:
        for m in ZH_MONTH_RE.finditer(page_html):
            date = _safe_date(int(m.group(1)), int(m.group(2)), 1)
            if date:
                consider(m.start(), m.end(), date)

    for m in EN_DATE_RE_1.finditer(page_html):
        month = EN_MONTH_MAP.get(m.group(1).lower())
        if not month:
            continue
        date = _safe_date(int(m.group(3)), int(month), int(m.group(2)))
        if date:
            consider(m.start(), m.end(), date)

    for m in EN_DATE_RE_2.finditer(page_html):
        month = EN_MONTH_MAP.get(m.group(2).lower())
        if not month:
            continue
        date = _safe_date(int(m.group(3)), int(month), int(m.group(1)))
        if date:
            consider(m.start(), m.end(), date)

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][1]


LEADING_TITLE_TRIM_CHARS = " \t\r\n\u3000\"'“”‘’《》()[]【】{}·•—–-:：/\\"


def title_initial_key(title: str) -> tuple[str, str]:
    """Sort key for '按首字母' ordering.

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


def extract_title_subtitle_pairs(page_html: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for m in PRODUCT_TITLE_SUBTITLE_PAIR_RE.finditer(page_html):
        title = clean_text(m.group(1))
        subtitle = clean_text(m.group(2))
        if title:
            pairs.append((title, subtitle))
    return pairs


def extract_base_title(page_html: str) -> str | None:
    match = PRODUCT_TITLE_RE.search(page_html)
    if not match:
        return None
    title = clean_text(match.group(1))
    return title or None


def extract_booklet_pages(page_html: str) -> int | None:
    if not page_html:
        return None
    m = BOOKLET_PAGES_RE.search(page_html)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def extract_usd_price(page_html: str) -> float | None:
    if not page_html:
        return None
    # Many pages contain multiple variants; prefer the highest visible USD price.
    prices: list[float] = []
    for m in PRICE_RE.finditer(page_html):
        try:
            prices.append(float(m.group(1)))
        except Exception:
            continue
    return max(prices) if prices else None


def deluxe_score(url: str, display_title: str, page_html: str, price: float | None) -> tuple[int, float, int]:
    """Higher is better.

    Heuristic priority:
    - Prefer editions that mention Blu-ray/蓝光 (typically the deluxe box).
    - Then higher price.
    - Then longer title for readability.
    """

    text = (display_title + " " + (page_html or "")).lower()
    score = 0
    if "blu-ray" in text or "bluray" in text or "蓝光" in (display_title + (page_html or "")):
        score += 200
    if "硬壳精装" in (display_title + (page_html or "")) or "精装" in (display_title + (page_html or "")):
        score += 40
    if "+" in display_title or "下载" in display_title:
        score += 10
    if "vinyl" in text or "黑胶" in (display_title + (page_html or "")):
        score += 5
    # Prefer non-download-only product pages.
    if "download" in url.lower():
        score -= 50
    return (score, float(price or 0.0), len(display_title))


def pick_physical_name(page_html: str) -> str | None:
    pairs = extract_title_subtitle_pairs(page_html)
    if not pairs:
        # Fallback for pages that don't follow the common variant layout.
        title_match = PRODUCT_TITLE_RE.search(page_html)
        if not title_match:
            return None
        product_title = clean_text(title_match.group(1))
        subtitle_match = PRODUCT_SUBTITLE_RE.search(page_html) or SUBTITLE_LIGHT_RE.search(page_html)
        subtitle = clean_text(subtitle_match.group(1)) if subtitle_match else ""
        candidate = (product_title + subtitle).strip()
        return candidate or None

    # Prefer the first variant that clearly contains physical media (CD / Blu-ray / SACD / vinyl, etc.).
    # Note: some physical editions also include download codes; they still count as physical.
    for title, subtitle in pairs:
        candidate = (title + subtitle).strip()
        if PHYSICAL_HINT_RE.search(candidate):
            return candidate

    # Fallback: if nothing is explicitly marked physical, pick the first non-download variant.
    for title, subtitle in pairs:
        candidate = (title + subtitle).strip()
        if not DOWNLOAD_NAME_HINT_RE.search(candidate):
            return candidate

    return None


def is_physical_release(url: str, name: str) -> bool:
    lower_url = url.lower()
    if "download" in lower_url and not PHYSICAL_HINT_RE.search(name):
        # Exclude download-only pages (24-bit download, etc.).
        return False
    if DOWNLOAD_URL_HINT_RE.search(lower_url):
        return False
    # Some pages may not say "Download" in the URL but still be digital-only.
    if DOWNLOAD_NAME_HINT_RE.search(name) and not PHYSICAL_HINT_RE.search(name):
        return False
    return True


def fetch_page(url: str) -> tuple[str, str | None, str | None]:
    try:
        html = curl(add_store_param(url))
        return url, html, None
    except Exception as e:
        return url, None, str(e)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate BOOKLETS.md checklist (physical editions only).")
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Only scan a specific product URL (can be repeated).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel fetch workers for sitemap scan (default: 8).",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help=f"Output markdown file (default: {OUTPUT_FILE}).",
    )
    parser.add_argument(
        "--debug-dedupe",
        action="store_true",
        help="Print dedupe decisions (groups with multiple editions).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    local_status = get_local_status_by_normalized_title(repo_root)

    if args.url:
        scan_urls = [u.strip() for u in args.url if u and u.strip()]
    else:
        sitemap_xml = curl(SITEMAP_URL)
        locs = parse_sitemap_locs(sitemap_xml)
        # Scan all HTML pages from the sitemap. Current size is manageable.
        scan_urls = [u for u in locs if u.endswith(".html") and not should_skip_url_pre_fetch(u)]

    # (group_key, norm_title, display_title, url, pages, score)
    found: list[tuple[str, str, str, str, int | None, tuple[int, float, int]]] = []
    errors: list[tuple[str, str]] = []

    if args.url:
        # URL-only mode: sequential, and print a short debug summary to stdout.
        for url in scan_urls:
            base_url, page, err = fetch_page(url)
            zh_url = add_store_param(base_url)
            if err or page is None:
                errors.append((zh_url, " ".join((err or "").splitlines()).strip()))
                continue
            if not BOOKLET_MARK_RE.search(page):
                continue
            name = pick_physical_name(page)
            if not name:
                continue
            if not is_physical_release(zh_url, name):
                continue
            display_title = sanitize_title_for_fs(name.strip())
            norm_title = normalize_title_for_dir(display_title)
            base_title = extract_base_title(page) or display_title
            base_norm = normalize_title_for_dir(base_title)
            pages = extract_booklet_pages(page)
            # De-duplicate across editions (CD / Blu-ray deluxe box / vinyl) by base title.
            # Page count is best-effort and should not block merging.
            group_key = base_norm
            price = extract_usd_price(page)
            score = deluxe_score(zh_url, display_title, page, price)
            found.append((group_key, norm_title, display_title, zh_url, pages, score))
    else:
        total = len(scan_urls)
        print(f"Fetching {total} pages with {args.workers} workers...", flush=True)
        completed = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(fetch_page, url): url for url in scan_urls}
            for fut in as_completed(futures):
                completed += 1
                url = futures[fut]
                base_url, page, err = fut.result()
                zh_url = add_store_param(base_url)
                if completed % 20 == 0 or completed == total:
                    print(f"Fetched {completed}/{total}", flush=True)
                if err or page is None:
                    errors.append((zh_url, " ".join((err or "").splitlines()).strip()))
                    continue
                if not BOOKLET_MARK_RE.search(page):
                    continue
                name = pick_physical_name(page)
                if not name:
                    continue
                if not is_physical_release(zh_url, name):
                    continue
                display_title = sanitize_title_for_fs(name.strip())
                norm_title = normalize_title_for_dir(display_title)
                base_title = extract_base_title(page) or display_title
                base_norm = normalize_title_for_dir(base_title)
                pages = extract_booklet_pages(page)
                group_key = base_norm
                price = extract_usd_price(page)
                score = deluxe_score(zh_url, display_title, page, price)
                found.append((group_key, norm_title, display_title, zh_url, pages, score))

    # De-duplicate by base product title.
    # Rationale: the same album often has multiple physical editions (CD/SACD vs deluxe box with Blu-ray vs vinyl)
    # that share the same booklet. Prefer deluxe/high-price editions.
    grouped: dict[str, list[tuple[str, str, str, int | None, tuple[int, float, int]]]] = {}
    # group_key -> [(norm_title, display_title, url, pages, score)]
    seen_in_group: dict[str, set[tuple[str, str]]] = {}
    for group_key, norm_title, display_title, url, pages, score in found:
        url = add_store_param(url)
        bucket = grouped.setdefault(group_key, [])
        seen = seen_in_group.setdefault(group_key, set())
        # avoid exact duplicates (same normalized title + same url)
        key = (norm_title, url)
        if key in seen:
            continue
        seen.add(key)
        bucket.append((norm_title, display_title, url, pages, score))

    # Choose best candidate per group.
    # Also compute local status by checking the chosen display title folder.
    items: list[tuple[str, str, bool, bool, str, str]] = []
    dedupe_debug: list[tuple[str, list[str], str]] = []
    for group_key, candidates in grouped.items():
        # Pick deluxe/high-price candidate.
        best = max(candidates, key=lambda x: x[4])
        best_norm, best_display, best_url, _pages, _score = best

        # Prefer linking against whichever local folder already contains booklet/translation.
        best_local_pdf = False
        best_local_zh = False
        best_local_folder = ""
        best_local_norm = best_norm
        for cand_norm, _cand_display, _cand_url, _cand_pages, _cand_score in candidates:
            lp, lz, lfolder = local_status.get(cand_norm, (False, False, ""))
            if (lp, lz) > (best_local_pdf, best_local_zh):
                best_local_pdf, best_local_zh, best_local_folder = lp, lz, lfolder
                best_local_norm = cand_norm

        if args.debug_dedupe and len(candidates) > 1:
            dedupe_debug.append(
                (
                    group_key,
                    [c[1] for c in sorted(candidates, key=lambda x: x[4], reverse=True)],
                    best_display,
                )
            )

        items.append((best_display, best_url, best_local_pdf, best_local_zh, best_local_folder, best_local_norm))
    # Sort by title initial.
    items.sort(key=lambda x: (title_initial_key(x[0]), normalize_title_for_dir(x[0])))

    out_path = os.path.join(repo_root, args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 柏林爱乐音像制品（含 booklet）翻译清单\n\n")
        f.write(
            "数据来源：Berliner Philharmoniker Recordings 官网中文站（根据官方 sitemap 扫描页面内容，是否出现 `Digital Booklet/Booklet` 标记）。\n\n"
        )
        f.write("说明：\n")
        f.write("- 每条发行物包含两项任务（均为 GitHub 可渲染的 task list）：\n")
        f.write("  - booklet 已收集：存在 `booklets/<标题>/booklet.pdf`\n")
        f.write("  - 中文翻译已完成：存在 `booklets/<标题>/booklet_zh.md`\n")
        f.write("- 列表按制品标题首字母（首字符）排序\n\n")

        for display_title, url, has_pdf, has_zh, folder_name, _stable_norm in items:
            pdf_box = "x" if has_pdf else " "
            zh_box = "x" if has_zh else " "
            f.write(f"- {display_title}\n")
            pdf_link = ""
            zh_link = ""
            if folder_name:
                if has_pdf:
                    pdf_link = f" ([目录](booklets/{folder_name}/) · [booklet.pdf](booklets/{folder_name}/booklet.pdf))"
                if has_zh:
                    zh_link = f" ([目录](booklets/{folder_name}/) · [booklet_zh.md](booklets/{folder_name}/booklet_zh.md))"
            f.write(f"  - [{pdf_box}] booklet 已收集{pdf_link}\n")
            f.write(f"  - [{zh_box}] 中文翻译已完成{zh_link}\n")
            f.write(f"  - 购买链接：{url}\n")

        if errors:
            f.write("\n## 抓取/解析异常（供排查）\n")
            for url, msg in errors[:100]:
                f.write(f"- {url} — {msg}\n")
            if len(errors) > 100:
                f.write(f"- ……（共 {len(errors)} 条，已截断）\n")

        if args.debug_dedupe and dedupe_debug:
            print("\nDedupe groups (multiple editions merged):")
            for group_key, titles, chosen in dedupe_debug:
                print(f"- {group_key} -> chosen: {chosen}")
                for t in titles:
                    print(f"    - {t}")

    print(f"Wrote {args.output}: {len(items)} items (from {len(scan_urls)} html pages).")
    if errors:
        print(f"Warnings: {len(errors)} pages had fetch/parse issues (see {args.output}).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
