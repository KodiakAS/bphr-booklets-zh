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
    python3 -m scripts.manage.generate_booklet_checklist

Outputs:
- BOOKLETS.md (repo root)

Notes:
- Primary discovery uses the official sitemap.
- To cover releases missing from the sitemap, the script also scans any purchase links
    recorded in local `booklets/<title>/SOURCE.md` (line: `- 购买链接：...`).
- Download-only pages are normally excluded by heuristics, but will be included when
    they are pinned by local SOURCE.md links and a local `booklet.pdf`/`booklet_zh.md`
    exists (e.g. `asia-tour.html`).
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

from .common import (
    REPO_ROOT,
    add_store_param,
    build_source_purchase_url_index,
    completion_rank,
    get_local_status_by_normalized_title,
    md_link_escape_path,
    normalize_title_for_dir,
    normalize_title_for_display,
    read_purchase_link_from_source,
    stable_url_key,
    title_initial_key,
)

SITEMAP_URL = "https://www.berliner-philharmoniker-recordings.com/sitemap.xml"
OUTPUT_FILE = "BOOKLETS.md"

PRODUCT_TITLE_RE = re.compile(r'class="product-title"[^>]*>\s*([^<]+?)\s*</h3>', re.I)
PRODUCT_SUBTITLE_RE = re.compile(r'class="product-subtitle"[^>]*>\s*([^<]+?)\s*</p>', re.I)
SUBTITLE_LIGHT_RE = re.compile(r'class="subtitle\s+light"[^>]*>\s*([^<]+?)\s*</span>', re.I)

PRODUCT_TITLE_SUBTITLE_PAIR_RE = re.compile(
    r'<h3\s+class="product-title"[^>]*>\s*([^<]+?)\s*</h3>\s*<p\s+class="product-subtitle"[^>]*>\s*([^<]+?)\s*</p>',
    re.I,
)

BOOKLET_MARK_RE = re.compile(r"<(?:strong|b)>\s*(?:Digital\s+Booklet|Booklet|手册)\s*</(?:strong|b)>", re.I)

OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]+?)"\s*/?>', re.I)
HTML_TITLE_RE = re.compile(r"<title>\s*([^<]+?)\s*</title>", re.I)

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

# Some pages list a base product title with per-variant subtitles like "4 SACD",
# "6张黑胶版", or "24-bit 下载". Those short subtitles are useful for choosing
# a deluxe variant but should not be merged into the display title.
_VARIANT_SUBTITLE_RE = re.compile(
    r"(?ix)^(?:\d+\s*(?:CD|SACD|DVD|LP)\b|\d+\s*张(?:黑胶|唱片|CD|DVD|蓝光)(?:版)?|24-bit\b|download\b|下载\b)"
)

NON_RECORDING_URL_HINT_RE = re.compile(
    r"(?:^|/)(?:gift-ideas|audio|video|books)\.html(?:\?|$)|(?:^|/)sbph-|thermos|flask|pen-|lamy-|dch-card|xmasticketdvd",
    re.I,
)

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


def _curl_with_retry(url: str) -> str:
    """curl() wrapper with one general retry for transient errors (non-404).

    This helps stabilize results across runs when the site intermittently times
    out or resets connections under higher concurrency.
    """

    try:
        return curl(url)
    except RuntimeError as e:
        msg = str(e)
        if "returned error: 404" in msg:
            raise

        # One conservative retry with longer timeouts and HTTP/1.1.
        time.sleep(0.4)
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
            "24",
            url,
        ]

        try:
            result = subprocess.run(
                retry_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=35,
            )
        except Exception:
            raise

        if result.returncode == 0:
            return result.stdout

        stderr_lines = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
        if stderr_lines and all(line == stderr_lines[0] for line in stderr_lines):
            raise RuntimeError(stderr_lines[0])
        raise RuntimeError(" ".join(stderr_lines).strip() or msg)


def clean_text(text: str) -> str:
    text = htmlmod.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def should_skip_url_pre_fetch(url: str) -> bool:
    lower_url = url.lower()
    if NON_RECORDING_URL_HINT_RE.search(lower_url):
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


def extract_official_page_title(page_html: str) -> str | None:
    """Best-effort extraction of the page's own title.

    This is more robust than scanning for `product-title` elements because
    cross-sell widgets may contain similar markup.
    """

    if not page_html:
        return None

    for rx in (OG_TITLE_RE, HTML_TITLE_RE):
        m = rx.search(page_html)
        if not m:
            continue
        raw = clean_text(m.group(1))
        if not raw:
            continue

        # Strip common site suffixes.
        for sep in (" | ", " - "):
            if sep in raw:
                left, right = raw.split(sep, 1)
                # Keep the left part if the right looks like a site name.
                if any(k in right.lower() for k in ("berliner", "recordings", "phil", "shop")):
                    raw = left.strip()
                    break
        return raw or None

    return None


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


def deluxe_score(url: str, display_title: str, page_html: str, price: float | None) -> tuple[float, int, int]:
    """Higher is better.

    We treat “most deluxe” as primarily “higher priced physical edition”, then
    refine with a few content hints.

    Note: some pages contain multiple variants; `extract_usd_price()` currently
    returns the highest visible USD price, which generally aligns with choosing
    the most deluxe variant on those pages.
    """

    text = (display_title + " " + (page_html or "")).lower()
    feature = 0

    if "blu-ray" in text or "bluray" in text or "蓝光" in (display_title + (page_html or "")):
        feature += 30
    if "硬壳精装" in (display_title + (page_html or "")) or "精装" in (display_title + (page_html or "")):
        feature += 10
    if "limited" in text or "numbered" in text or "限量" in (display_title + (page_html or "")) or "独立编号" in (display_title + (page_html or "")):
        feature += 12
    if "vinyl" in text or "黑胶" in (display_title + (page_html or "")):
        feature += 4

    lower_url = url.lower()
    effective_price = float(price or 0.0)

    # Prefer non-download-only product pages.
    if "download" in lower_url:
        feature -= 30
        effective_price = 0.0

    # Primary: price. Secondary: feature hints. Tertiary: longer title.
    return (effective_price, int(feature), len(display_title))


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
        subtitle = subtitle.strip()
        if subtitle and _VARIANT_SUBTITLE_RE.search(subtitle):
            candidate = product_title.strip()
        else:
            candidate = (product_title + subtitle).strip()
        return candidate or None

    # Prefer the first variant that clearly contains physical media (CD / Blu-ray / SACD / vinyl, etc.).
    # Note: some physical editions also include download codes; they still count as physical.
    for title, subtitle in pairs:
        subtitle = (subtitle or "").strip()
        if subtitle and _VARIANT_SUBTITLE_RE.search(subtitle):
            candidate = (title or "").strip()
        else:
            candidate = (title + subtitle).strip()
        if PHYSICAL_HINT_RE.search(candidate):
            return candidate

    # Fallback: if nothing is explicitly marked physical, pick the first non-download variant.
    for title, subtitle in pairs:
        subtitle = (subtitle or "").strip()
        if subtitle and _VARIANT_SUBTITLE_RE.search(subtitle):
            candidate = (title or "").strip()
        else:
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
        html = _curl_with_retry(add_store_param(url))
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
    repo_root = REPO_ROOT
    booklets_dir = os.path.join(repo_root, "booklets")
    local_status = get_local_status_by_normalized_title(booklets_dir)
    source_url_to_folder, source_urls, folder_to_official_title = build_source_purchase_url_index(booklets_dir)

    if args.url:
        scan_urls = [u.strip() for u in args.url if u and u.strip()]
    else:
        sitemap_xml = curl(SITEMAP_URL)
        locs = parse_sitemap_locs(sitemap_xml)
        # Scan all HTML pages from the sitemap. Current size is manageable.
        scan_urls = [u for u in locs if u.endswith(".html") and not should_skip_url_pre_fetch(u)]
        # Also scan local SOURCE.md purchase links to cover releases missing from sitemap.
        scan_urls.extend(source_urls)

    # De-dup scan URLs using stable store-param normalization.
    seen_scan: set[str] = set()
    scan_urls_dedup: list[str] = []
    for u in scan_urls:
        if not u:
            continue
        key = stable_url_key(u)
        if key in seen_scan:
            continue
        seen_scan.add(key)
        scan_urls_dedup.append(u)
    scan_urls = scan_urls_dedup

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
            pinned_folder = source_url_to_folder.get(stable_url_key(zh_url))
            pinned_norm = normalize_title_for_dir(pinned_folder) if pinned_folder else ""
            pinned_has_pdf, pinned_has_zh, _p_folder = local_status.get(pinned_norm, (False, False, ""))

            has_booklet_label = bool(BOOKLET_MARK_RE.search(page))
            if not (has_booklet_label or pinned_has_pdf or pinned_has_zh):
                continue

            name = pick_physical_name(page) or extract_official_page_title(page) or extract_base_title(page)
            if not name and not pinned_folder:
                continue

            if name and (not is_physical_release(zh_url, name)) and not (pinned_has_pdf or pinned_has_zh):
                # Keep pinned/local-booklet releases even if they are download-only.
                continue

            override_title = folder_to_official_title.get(pinned_folder or "") if pinned_folder else None
            # Prefer explicit official title override; else use the page-derived name.
            display_title = normalize_title_for_display((override_title or name or pinned_folder or "").strip())
            # IMPORTANT: keep the internal normalized key aligned with the local folder
            # so local status + links still work even if display_title differs.
            norm_title = pinned_norm or normalize_title_for_dir(display_title)
            # Dedupe key: use the on-page product title (stable across editions/variants).
            # Avoid using og:title/<title> here because those can differ across variant pages
            # even when the underlying release is the same.
            base_title = override_title or extract_base_title(page) or display_title
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
                pinned_folder = source_url_to_folder.get(stable_url_key(zh_url))
                pinned_norm = normalize_title_for_dir(pinned_folder) if pinned_folder else ""
                pinned_has_pdf, pinned_has_zh, _p_folder = local_status.get(pinned_norm, (False, False, ""))

                has_booklet_label = bool(BOOKLET_MARK_RE.search(page))
                if not (has_booklet_label or pinned_has_pdf or pinned_has_zh):
                    continue

                name = pick_physical_name(page) or extract_official_page_title(page) or extract_base_title(page)
                if not name and not pinned_folder:
                    continue

                if name and (not is_physical_release(zh_url, name)) and not (pinned_has_pdf or pinned_has_zh):
                    continue

                override_title = folder_to_official_title.get(pinned_folder or "") if pinned_folder else None
                display_title = normalize_title_for_display((override_title or name or pinned_folder or "").strip())
                norm_title = pinned_norm or normalize_title_for_dir(display_title)
                base_title = override_title or extract_base_title(page) or display_title
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

    # Stabilize candidate ordering within each group so that selection is
    # deterministic even under concurrent fetching.
    #
    # Primary: deluxe score (desc)
    # Ties: pick by URL, then by normalized title, then by display title.
    for _gk, bucket in grouped.items():
        bucket.sort(
            key=lambda x: (
                x[4],
                stable_url_key(x[2]),
                x[0],
                normalize_title_for_dir(x[1]),
            ),
            reverse=True,
        )

    # Choose best candidate per group.
    # Also compute local status by checking the chosen display title folder.
    items: list[tuple[str, str, bool, bool, str, str]] = []
    dedupe_debug: list[tuple[str, list[str], str]] = []
    for group_key in sorted(grouped.keys()):
        candidates = grouped[group_key]
        # Pick deluxe/high-price candidate (bucket is already stably sorted).
        best_norm, best_display, best_url, _pages, _score = candidates[0]

        # Prefer linking against whichever local folder already contains booklet/translation.
        best_local_pdf = False
        best_local_zh = False
        best_local_folder = ""
        best_local_norm = best_norm
        # Deterministic local folder selection:
        # - Prefer higher (has_pdf, has_zh)
        # - Then prefer having a concrete folder name
        # - Then folder name lexicographically
        # - Then by candidate normalized title
        local_candidates: list[tuple[tuple[bool, bool], str, str]] = []
        # Also consider the base-title group key itself as a lookup into local folders.
        # This covers cases where the page-derived display title includes media subtitles
        # (e.g. "4 SACD") but the local folder is named by the base product title.
        g_pdf, g_zh, g_folder = local_status.get(group_key, (False, False, ""))
        if g_folder:
            local_candidates.append(((g_pdf, g_zh), g_folder or "", group_key))
        for cand_norm, _cand_display, _cand_url, _cand_pages, _cand_score in candidates:
            lp, lz, lfolder = local_status.get(cand_norm, (False, False, ""))
            local_candidates.append(((lp, lz), lfolder or "", cand_norm))

        best_status = max((s for s, _folder, _norm in local_candidates), default=(False, False))
        # Filter to best status; then pick a stable winner.
        best_locals = [c for c in local_candidates if c[0] == best_status]
        if best_locals:
            # Prefer non-empty folder names (so links resolve), then stable folder name and norm.
            _status, chosen_folder, chosen_norm = sorted(
                best_locals,
                key=lambda x: (
                    0 if x[1] else 1,
                    x[1],
                    x[2],
                ),
            )[0]
            best_local_pdf, best_local_zh = best_status
            best_local_folder = chosen_folder
            best_local_norm = chosen_norm

        if args.debug_dedupe and len(candidates) > 1:
            dedupe_debug.append(
                (
                    group_key,
                    [c[1] for c in sorted(candidates, key=lambda x: x[4], reverse=True)],
                    best_display,
                )
            )

    items.append((best_display, best_url, best_local_pdf, best_local_zh, best_local_folder, best_local_norm))
    out_path = os.path.join(repo_root, args.output)
    online_norms: set[str] = {stable_norm for *_rest, stable_norm in items}
    existing_url_keys: set[str] = {
        stable_url_key(url)
        for _display_title, url, *_rest in items
        if url and url != "待补充"
    }

    # Always keep SOURCE.md-pinned releases in the list even if:
    # - the page is missing from sitemap,
    # - the page is temporarily unreachable,
    # - heuristics classify it as download-only or fail to detect booklet labels.
    #
    # This ensures manual/pinned entries never get dropped by regeneration.
    for url_key, folder in sorted(source_url_to_folder.items(), key=lambda x: x[0]):
        if url_key in existing_url_keys:
            continue

        folder_norm = normalize_title_for_dir(folder)
        if folder_norm in online_norms:
            continue

        folder_path = os.path.join(booklets_dir, folder)
        has_pdf = os.path.isfile(os.path.join(folder_path, "booklet.pdf"))
        has_zh = os.path.isfile(os.path.join(folder_path, "booklet_zh.md"))

        official_title = folder_to_official_title.get(folder)
        display_title = normalize_title_for_display((official_title or folder).strip())
        purchase = read_purchase_link_from_source(booklets_dir, folder, require_url=True)
        url = add_store_param(purchase) if purchase else "待补充"

        items.append((display_title, url, has_pdf, has_zh, folder, folder_norm))
        online_norms.add(folder_norm)
        if url and url != "待补充":
            existing_url_keys.add(stable_url_key(url))

    # Merge local-only releases (missing from sitemap scan) into the main list.
    for norm, (has_pdf, has_zh, folder) in local_status.items():
        if norm in online_norms:
            continue
        if not (has_pdf or has_zh):
            continue
        if not folder:
            continue
        purchase = read_purchase_link_from_source(booklets_dir, folder, require_url=True)
        official_title = folder_to_official_title.get(folder)
        display_title = normalize_title_for_display((official_title or folder).strip())
        items.append((display_title, purchase or "待补充", has_pdf, has_zh, folder, norm))

    # Sort by completion status first, then by title initial.
    # IMPORTANT: run after merging local-only entries so they follow the same rule.
    items.sort(
        key=lambda x: (
            completion_rank(x[2], x[3]),
            title_initial_key(x[0]),
            normalize_title_for_dir(x[0]),
        )
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 柏林爱乐音像制品（含 booklet）翻译清单\n\n")
        f.write(
            "数据来源：Berliner Philharmoniker Recordings 官网中文站（根据官方 sitemap 扫描页面内容，是否出现 `Digital Booklet/Booklet` 标记）。\n\n"
        )
        f.write("说明：\n")
        f.write("- 每条发行物包含两项任务（均为 GitHub 可渲染的 task list）：\n")
        f.write("  - booklet 已收集：存在 `booklets/<标题>/booklet.pdf`\n")
        f.write("  - 中文翻译已完成：存在 `booklets/<标题>/booklet_zh.md`\n")
        f.write("- 列表按完成状态优先级排序（中文翻译已完成 > booklet 已收集 > 其他）；同一优先级内按制品标题首字母（首字符）排序\n\n")

        for display_title, url, has_pdf, has_zh, folder_name, _stable_norm in items:
            pdf_box = "x" if has_pdf else " "
            zh_box = "x" if has_zh else " "
            f.write(f"- {display_title}\n")
            pdf_link = ""
            zh_link = ""
            if folder_name:
                folder_md = md_link_escape_path(folder_name)
                if has_pdf:
                    pdf_link = f" ([目录](booklets/{folder_md}/) · [booklet.pdf](booklets/{folder_md}/booklet.pdf))"
                if has_zh:
                    zh_link = f" ([目录](booklets/{folder_md}/) · [booklet_zh.md](booklets/{folder_md}/booklet_zh.md))"
            f.write(f"  - [{pdf_box}] booklet 已收集{pdf_link}\n")
            f.write(f"  - [{zh_box}] 中文翻译已完成{zh_link}\n")
            f.write(f"  - 购买链接：{url}\n")

        if errors:
            f.write("\n## 抓取/解析异常（供排查）\n")
            # Stable ordering to avoid noisy diffs between runs.
            errors_sorted = sorted(
                errors,
                key=lambda x: (
                    stable_url_key(x[0]),
                    " ".join((x[1] or "").split()),
                ),
            )
            for url, msg in errors_sorted[:100]:
                f.write(f"- {url} — {msg}\n")
            if len(errors_sorted) > 100:
                f.write(f"- ……（共 {len(errors_sorted)} 条，已截断）\n")

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
