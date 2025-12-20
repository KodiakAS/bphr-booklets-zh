#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path

from .common import DE_STOPWORDS_EXTRACT, EN_STOPWORDS, stopword_lang_score


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


_GERMAN_HINT_RE = re.compile(
    r"\b("
    r"Symphonie|INHALT|Inhalt|Entstehungszeit|Uraufführung|Fassung|Brüder|Freude|überm|"
    r"Satz|Takt|Dirigent|Mitglieder|wurde|werden|wobei|folgenden|Jahren|gleich"
    r")\b|ß",
    flags=re.IGNORECASE,
)


_ENGLISH_HINT_RE = re.compile(
    r"\b("
    r"Symphony|Conductor|ORCHESTRATION|CONTENT|Year of composition|First performance|"
    r"Flutes|Oboes|Clarinets|Bassoons|Horns|Trumpets|Trombones|Timpani|Percussion|Harp|"
    r"Violins|Violas|Cellos|Double\s+basses"
    r")\b",
    flags=re.IGNORECASE,
)


_JAPANESE_HINT_RE = re.compile(r"[\u3040-\u30ff\uff66-\uff9d]")


def _looks_german(text: str) -> bool:
    return bool(_GERMAN_HINT_RE.search(text))


def _looks_english(text: str) -> bool:
    return bool(_ENGLISH_HINT_RE.search(text))


def _looks_japanese(text: str) -> bool:
    return bool(_JAPANESE_HINT_RE.search(text))


def _lang_score(text: str) -> tuple[int, int]:
    """Return (en_score, de_score) based on stopword counts.

    Heuristic only: works best on paragraph-ish text, not on short labels.
    """

    return stopword_lang_score(text, en_stopwords=EN_STOPWORDS, de_stopwords=DE_STOPWORDS_EXTRACT)


def _filter_lines_by_language(lines: list[str], language_filter: str) -> list[str]:
    if language_filter == "none":
        return lines

    filtered: list[str] = []
    for line in lines:
        if not line:
            filtered.append("")
            continue

        if _looks_japanese(line) and not _looks_english(line):
            continue

        # Common bilingual pattern: "German · English".
        # Keep the English fragment (preserving leading counts like "3 Flöten · Flutes").
        if "·" in line:
            left, right = [p.strip() for p in line.split("·", maxsplit=1)]
            m_count = re.match(r"^(?P<count>\d+)\s+", left)
            if m_count:
                line = f"{m_count.group('count')} {right}".strip()
            else:
                # Preserve surrounding brackets in lines like:
                # "[BASSKLARINETTE · BASS CLARINET IN NO. 6]"
                if left.startswith("[") and right.endswith("]") and not right.startswith("["):
                    line = f"[{right}"
                else:
                    # Pattern like: "Pierre Amoyal, Violine · violin" -> keep name and English role.
                    if "," in left and right and right[:1].islower() and len(right) <= 40:
                        name = left.split(",", maxsplit=1)[0].strip()
                        line = f"{name}, {right}".strip()
                    else:
                        line = right

        # If a bracketed note still contains bilingual "·", keep the right-hand (English) part.
        # Example: "2 FLUTES [2. AUCH PICCOLOFLÖTE · 2ND ALSO PICCOLO IN NOS. 1 & 7]"
        if "·" in line and "[" in line and "]" in line:
            def _fix_bracket(m: re.Match[str]) -> str:
                content = m.group(1)
                if "·" not in content:
                    return f"[{content}]"
                _left, _right = [p.strip() for p in content.rsplit("·", maxsplit=1)]
                return f"[{_right}]"

            line = re.sub(r"\[([^\]]+)\]", _fix_bracket, line)

        # Keep track / movement title lines even if they're German-only (e.g. Strauss section titles).
        if re.match(r"^\d{1,3}\.\s", line):
            filtered.append(line)
            continue

        # Keep work title / metadata lines with opus numbers, even if non-English.
        if re.search(r"\bop\.\s*\d", line, flags=re.IGNORECASE):
            filtered.append(line)
            continue

        # If the line is clearly German and doesn't contain stable English labels,
        # drop it early (helps remove stray German-only fragments on bilingual pages).
        # Guard against dropping English lines with non-English names (e.g. Järnefelt, Mäkelä)
        # by requiring explicit German hints and no stable English labels.
        if _looks_german(line) and not _looks_english(line):
            en_score, de_score = _lang_score(line)
            if de_score >= en_score:
                continue

        # Protect stable English labels (e.g. "Conductor: Herbert von Karajan") from being
        # misclassified as German due to particles like "von" in names.
        if _looks_english(line) and not _looks_german(line):
            filtered.append(line)
            continue

        # Keep obvious numeric/time/track lines; they're useful for later structuring.
        if re.search(r"\b\d{1,2}:\d{2}\b", line) or re.search(r"\bCD\b", line):
            filtered.append(line)
            continue

        # Keep all-caps headings, but avoid obvious German-only ones.
        if line.isupper() and len(line) >= 6:
            en_score, de_score = _lang_score(line)
            if _looks_german(line) and not _looks_english(line):
                continue
            if de_score > en_score and not _looks_english(line):
                continue
            filtered.append(line)
            continue

        en, de = _lang_score(line)

        # If the line has no stopword signal, fall back to lightweight hints.
        # This helps drop obvious German-only fragments that otherwise slip through.
        if en == 0 and de == 0:
            if not _looks_german(line):
                filtered.append(line)
            continue

        if en >= de:
            filtered.append(line)

    return filtered


def _page_lang_score(text: str) -> tuple[int, int]:
    """Return (en_score, de_score) for an entire extracted page block."""

    # Ignore very short lines and pure numeric markers.
    kept: list[str] = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        if re.fullmatch(r"[\d:()\[\]–—\-./ ]+", s):
            continue
        if len(s) < 8:
            continue
        kept.append(s)
    return _lang_score("\n".join(kept))


def _should_drop_page(raw_page_text: str, extracted: str, language_filter: str) -> bool:
    """Return True if we should drop this page block as non-English scope.

    Safety rule: never drop a page if we can detect *any* English signal
    (stopwords or stable English labels) in either the raw page text or
    the filtered extracted text.
    """

    if language_filter != "en":
        return False

    raw_en, raw_de = _page_lang_score(raw_page_text)
    extracted_en, extracted_de = _page_lang_score(extracted)

    # Protect against losing pages that contain some English content.
    if raw_en > 0 or extracted_en > 0:
        return False
    if _looks_english(raw_page_text) or _looks_english(extracted):
        return False

    # If we have no signal at all, don't drop.
    if raw_en == 0 and raw_de == 0 and extracted_en == 0 and extracted_de == 0:
        return False

    # Drop pages that are clearly German-dominant.
    return raw_de >= raw_en + 2


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
            m2 = re.match(r"^(?P<count>\d+)\s+", left)
            if m2:
                s = f"{m2.group('count')} {right}"
            else:
                # Pattern like: "Pierre Amoyal, Violine · violin" -> keep name and English role.
                if "," in left and right and right[:1].islower() and len(right) <= 40:
                    name = left.split(",", maxsplit=1)[0].strip()
                    s = f"{name}, {right}".strip()
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


def _page_text_with_columns(page) -> str:
    """Extract page text with a simple multi-column reading order.

    PyMuPDF's plain get_text('text') can interleave columns in row order on
    multi-column layouts. For booklet essays and similar pages, we prefer a
    column-wise order (left-to-right columns, top-to-bottom within each column).
    """

    try:
        blocks = page.get_text("blocks")
    except Exception:
        return page.get_text("text")

    text_blocks: list[tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text, _no, block_type in blocks:
        if block_type != 0:
            continue
        s = text.strip()
        if not s:
            continue
        compact = " ".join(s.split())
        # Drop pure page numbers early; _clean_lines will also filter them, but
        # excluding them here helps column detection.
        if re.fullmatch(r"\d{1,3}", compact):
            continue
        text_blocks.append((x0, y0, x1, y1, s))

    if not text_blocks:
        return ""

    # Detect likely column anchors by frequent x0 values.
    from collections import Counter

    x0s = [round(x0, 1) for x0, _y0, _x1, _y1, _t in text_blocks]
    counts = Counter(x0s)
    main_x = sorted([x for x, n in counts.items() if n >= 5])

    # If we can't confidently detect columns, fall back to row-wise ordering.
    if len(main_x) < 2 or (max(main_x) - min(main_x)) <= 120:
        ordered = sorted(text_blocks, key=lambda b: (b[1], b[0]))
        return "\n".join(t.strip() for *_, t in ordered)

    def _nearest_main_x(x: float) -> tuple[float, float]:
        best = min(main_x, key=lambda m: abs(x - m))
        return best, abs(x - best)

    columns: dict[float, list[tuple[float, float, float, float, str]]] = {x: [] for x in main_x}
    misc: list[tuple[float, float, float, float, str]] = []

    for x0, y0, x1, y1, t in text_blocks:
        col_x, dist = _nearest_main_x(round(x0, 1))
        # Allow some tolerance for minor indentations.
        if dist <= 30:
            columns[col_x].append((x0, y0, x1, y1, t))
        else:
            misc.append((x0, y0, x1, y1, t))

    min_col_y = min(b[1] for col in columns.values() for b in col) if any(columns.values()) else 0.0
    top_misc = [b for b in misc if b[1] < (min_col_y - 5)]
    bottom_misc = [b for b in misc if b[1] >= (min_col_y - 5)]

    out: list[str] = []
    out.extend(t.strip() for *_, t in sorted(top_misc, key=lambda b: (b[1], b[0])))
    for x in main_x:
        out.extend(t.strip() for *_, t in sorted(columns[x], key=lambda b: (b[1], b[0])))
    out.extend(t.strip() for *_, t in sorted(bottom_misc, key=lambda b: (b[1], b[0])))
    return "\n".join(out)


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
    parser.add_argument(
        "--drop-non-english-pages",
        action="store_true",
        default=True,
        help=(
            "When --language-filter=en, drop page blocks that are strongly German-dominant. "
            "This keeps booklet_en.md closer to the actual translation scope. Default: enabled"
        ),
    )
    parser.add_argument(
        "--keep-non-english-pages",
        action="store_true",
        default=False,
        help="Disable dropping and keep all extracted pages (even if German-dominant)",
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

    dropped_pages: list[int] = []

    included_count = 0

    for p in pages:
        if not (1 <= p <= doc.page_count):
            continue

        page = doc.load_page(p - 1)
        page_text = _page_text_with_columns(page)

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

        if args.language_filter == "en" and args.drop_non_english_pages and not args.keep_non_english_pages:
            if _should_drop_page(page_text, extracted, args.language_filter):
                dropped_pages.append(p)
                continue

        parts.append(f"## [PDF p.{p}]")
        parts.append("")
        parts.append(extracted)
        parts.append("")
        included_count += 1

    if dropped_pages:
        # Insert after the existing header bullets (right before the first blank line after them).
        insert_at = 0
        for i, line in enumerate(parts):
            if line == "" and i > 0:
                insert_at = i
                break
        parts.insert(insert_at, f"- Dropped pages (PDF): {', '.join(map(str, dropped_pages))} (German-dominant by heuristic)")

    cfg.out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")

    print(f"OK: wrote {cfg.out_path}")
    print(f"Included {included_count} page blocks out of {len(pages)} pages")
    if dropped_pages:
        print(f"Dropped {len(dropped_pages)} page blocks as non-English-dominant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
