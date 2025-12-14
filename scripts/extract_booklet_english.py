#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractConfig:
    booklet_dir: Path
    pdf_path: Path
    out_path: Path


DEFAULT_RUNNING_TITLE_LINES = {
    "Bruckner in Berlin",
    "A Philharmonic quadriga and",
    "other driving forces",
    "Listening again to Bruckner",
    "From Vienna into the World",
    "The Conductors of this Edition",
}


EN_STOPWORDS = {
    "the",
    "and",
    "of",
    "to",
    "in",
    "a",
    "is",
    "that",
    "with",
    "as",
    "for",
    "on",
    "by",
    "from",
    "at",
    "this",
    "be",
    "are",
    "was",
    "were",
    "it",
    "his",
    "her",
    "their",
}


DE_STOPWORDS = {
    "der",
    "die",
    "das",
    "und",
    "zu",
    "mit",
    "im",
    "in",
    "auf",
    "für",
    "von",
    "ist",
    "sind",
    "war",
    "wurden",
    "ein",
    "eine",
    "einer",
    "eines",
    "als",
    "auch",
    "nicht",
    "sich",
    "dass",
}


def _word_counts(text: str) -> dict[str, int]:
    words = re.findall(r"[A-Za-zÄÖÜäöüß']+", text.lower())
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return counts


def _lang_score(text: str) -> tuple[int, int]:
    """Return (en_score, de_score) based on stopword counts.

    Heuristic only: works best on paragraph-ish text, not on short labels.
    """

    counts = _word_counts(text)
    en = sum(counts.get(w, 0) for w in EN_STOPWORDS)
    de = sum(counts.get(w, 0) for w in DE_STOPWORDS)
    return en, de


def _filter_lines_by_language(lines: list[str], language_filter: str) -> list[str]:
    if language_filter == "none":
        return lines

    filtered: list[str] = []
    for line in lines:
        if not line:
            filtered.append("")
            continue

        # Keep obvious numeric/time/track lines; they're useful for later structuring.
        if re.search(r"\b\d{1,2}:\d{2}\b", line) or re.search(r"\bCD\b", line):
            filtered.append(line)
            continue

        # Keep all-caps headings.
        if line.isupper() and len(line) >= 6:
            filtered.append(line)
            continue

        en, de = _lang_score(line)
        # If the line has no signal, keep it (manual review will decide).
        if en == 0 and de == 0:
            filtered.append(line)
            continue

        if en >= de:
            filtered.append(line)

    return filtered


def _normalize_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"([A-Za-z])\-\n([A-Za-z])", r"\1\2", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    blank = 0
    for line in lines:
        if line == "":
            blank += 1
            if blank <= 1:
                collapsed.append("")
        else:
            blank = 0
            collapsed.append(line)

    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return collapsed


def _clean_lines(text: str, running_title_lines: set[str]) -> str:
    out: list[str] = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            out.append("")
            continue
        if re.fullmatch(r"\d{1,3}", s):
            continue
        if s in running_title_lines:
            continue
        out.append(s)

    return "\n".join(_collapse_blank_lines(out))


def _extract_symphony_metadata_english(
    page_text: str,
    running_title_lines: set[str],
    language_filter: str,
) -> str:
    text = _normalize_text(page_text)
    lines = text.split("\n")
    out: list[str] = []

    for raw in lines:
        s = raw.strip()
        if not s:
            out.append("")
            continue

        # Drop standalone German continuation lines.
        if s.startswith("Revisionen"):
            continue

        # Drop common German-only metadata lines when no English counterpart is present.
        if re.search(r"\bSymphonie\b", raw) and "Symphony" not in raw:
            continue
        if re.search(r"\bFassung\b", raw) and "version" not in raw.lower():
            continue

        # Conductor line often looks like: "Seiji Ozawa Dirigent · Conductor"
        m = re.match(r"^(?P<name>.+?)\s+Dirigent\s*·\s*Conductor\s*$", raw)
        if m:
            out.append(f"Conductor: {m.group('name').strip()}")
            continue

        # Common pattern: "German · English"
        if "·" in s:
            left, right = [p.strip() for p in s.split("·", maxsplit=1)]
            # Preserve counts in instrumentation lines like "3 Flöten · Flutes".
            m2 = re.match(r"^(?P<count>\d+)\b", left)
            if m2:
                s = f"{m2.group('count')} {right}"
            else:
                s = right

        # If both present, keep English fragment.
        if "Symphonie" in raw and "Symphony No." in raw:
            m = re.search(r"(Symphony No\.[^\n]+)$", raw)
            if m:
                s = m.group(1).strip()

        # Version line: prefer the part containing "version".
        if "Fassung" in raw and "version" in raw.lower():
            m = re.search(r"(.*\bversion\b.*)", raw, flags=re.IGNORECASE)
            if m:
                s = m.group(1).strip()

        # Remove trailing German fragments after English labels.
        if s.startswith("Year of composition"):
            s = re.sub(r",\s*Revisionen\b.*", "", s)

        # Drop obvious German-only labels.
        if re.fullmatch(
            r"(SYMPHONIE|Symphonie|Fassung|Entstehungszeit|Uraufführung|Erste Aufführung der Berliner Philharmoniker)\s*",
            s,
        ):
            continue

        # Normalize heading
        if "ORCHESTRATION" in raw:
            s = "ORCHESTRATION"

        out.append(s)

    cleaned = _clean_lines("\n".join(out), running_title_lines)
    lines2 = cleaned.split("\n")
    lines2 = _filter_lines_by_language(lines2, language_filter)
    return "\n".join(_collapse_blank_lines(lines2))


def _extract_symphony_commentary_english(
    page_text: str,
    running_title_lines: set[str],
    language_filter: str,
) -> str:
    text = _normalize_text(page_text)
    idx = text.find("SYMPHONY NO.")
    if idx != -1:
        text = text[idx:]
    cleaned = _clean_lines(text, running_title_lines)
    lines2 = cleaned.split("\n")
    lines2 = _filter_lines_by_language(lines2, language_filter)
    return "\n".join(_collapse_blank_lines(lines2))


def _extract_generic(page_text: str, running_title_lines: set[str], language_filter: str) -> str:
    text = _normalize_text(page_text)
    cleaned = _clean_lines(text, running_title_lines)
    lines2 = cleaned.split("\n")
    lines2 = _filter_lines_by_language(lines2, language_filter)
    return "\n".join(_collapse_blank_lines(lines2))


def _parse_page_spec(spec: str) -> list[int]:
    """Parse page specifications like: "5,6-23,53-58,61-68,79-84,95-96"."""
    pages: list[int] = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a.strip())
            end = int(b.strip())
            if end < start:
                raise ValueError(f"Invalid range: {part}")
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    # de-dupe while preserving order
    seen: set[int] = set()
    ordered: list[int] = []
    for p in pages:
        if p not in seen:
            ordered.append(p)
            seen.add(p)
    return ordered


def _build_default_pages_for_bruckner() -> list[int]:
    pages: list[int] = []
    pages += [5]
    pages += list(range(6, 24))
    pages += list(range(53, 59)) + list(range(61, 69))
    pages += list(range(79, 85))
    pages += [95, 96]
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract an English-only scope document (booklet_en.md) from a booklet PDF text layer. "
            "This is the first step of a 2-step translation workflow."
        )
    )
    parser.add_argument(
        "--booklet-dir",
        required=True,
        help="Target booklet directory under booklets/, containing booklet.pdf",
    )
    parser.add_argument(
        "--pdf",
        default="booklet.pdf",
        help="PDF filename inside booklet-dir (default: booklet.pdf)",
    )
    parser.add_argument(
        "--out",
        default="booklet_en.md",
        help="Output markdown filename inside booklet-dir (default: booklet_en.md)",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help=(
            "1-based page spec like '5,6-23,53-58,61-68,79-84,95-96'. "
            "If omitted, uses a Bruckner test preset."
        ),
    )
    parser.add_argument(
        "--skip-pages",
        default="",
        help="1-based page ranges to skip (comma-separated). Default: 59-60",
    )
    parser.add_argument(
        "--cut-before",
        default=r"\nSeiji Ozawa\b",
        help=(
            "Regex; for any page where it matches, content is cut before the match. "
            "Default cuts the conductors intro before biographies." 
        ),
    )
    parser.add_argument(
        "--cut-before-min-page",
        type=int,
        default=90,
        help=(
            "Only apply --cut-before on pages >= this 1-based page number. "
            "Prevents accidental truncation on earlier pages that mention the same phrase."
        ),
    )
    parser.add_argument(
        "--language-filter",
        choices=["none", "en"],
        default="en",
        help=(
            "Heuristic filter to keep English-leaning lines on bilingual pages. "
            "Always requires manual skim; set to 'none' to disable. Default: en"
        ),
    )
    args = parser.parse_args()

    booklet_dir = Path(args.booklet_dir)
    cfg = ExtractConfig(
        booklet_dir=booklet_dir,
        pdf_path=booklet_dir / args.pdf,
        out_path=booklet_dir / args.out,
    )

    if not cfg.pdf_path.exists():
        raise SystemExit(f"PDF not found: {cfg.pdf_path}")

    try:
        import fitz  # type: ignore
    except Exception as exc:
        raise SystemExit(
            "Missing dependency: PyMuPDF. Install with: python3 -m pip install pymupdf"
        ) from exc

    doc = fitz.open(str(cfg.pdf_path))

    pages = _build_default_pages_for_bruckner() if not args.pages else _parse_page_spec(args.pages)
    skip_pages = set(_parse_page_spec(args.skip_pages)) if args.skip_pages else set()
    pages = [p for p in pages if p not in skip_pages]

    running_title_lines = set(DEFAULT_RUNNING_TITLE_LINES)

    cut_before_re = re.compile(args.cut_before)

    parts: list[str] = []
    parts.append("# Booklet English extraction (for translation scope)")
    parts.append("")
    parts.append(f"- Source: {cfg.pdf_path.name} (text layer; no OCR)")
    parts.append("- Purpose: confirm translation scope before producing booklet_zh.md")
    parts.append(f"- Generated: {_dt.date.today().isoformat()}")
    parts.append(f"- Included pages (PDF): {', '.join(map(str, pages))}")
    if skip_pages:
        parts.append(f"- Skipped pages (PDF): {', '.join(map(str, sorted(skip_pages)))}")
    parts.append(f"- Language filter: {args.language_filter} (heuristic; manual skim required)")
    parts.append(
        "- Manual checklist: skim each section; delete any leftover German-only lines; confirm cutoffs for biographies/credits/captions"
    )
    parts.append("")

    included_count = 0

    for p in pages:
        if not (1 <= p <= doc.page_count):
            continue

        page_text = doc.load_page(p - 1).get_text("text")

        # Optional cutoff for pages that transition into biographies etc.
        if p >= args.cut_before_min_page:
            m = cut_before_re.search(page_text)
            if m:
                page_text = page_text[: m.start()]  # cut before match

        if 6 <= p <= 23 and (p % 2 == 0):
            extracted = _extract_symphony_metadata_english(page_text, running_title_lines, args.language_filter)
        elif 7 <= p <= 23 and (p % 2 == 1):
            extracted = _extract_symphony_commentary_english(page_text, running_title_lines, args.language_filter)
        else:
            extracted = _extract_generic(page_text, running_title_lines, args.language_filter)

        extracted = extracted.strip()
        if not extracted:
            continue

        parts.append(f"## [PDF p.{p}]")
        parts.append("")
        parts.append(extracted)
        parts.append("")
        included_count += 1

    cfg.out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

    print(f"OK: wrote {cfg.out_path}")
    print(f"Included {included_count} page blocks out of {len(pages)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
