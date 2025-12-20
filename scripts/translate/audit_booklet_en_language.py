#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from .common import DE_STOPWORDS_AUDIT, EN_STOPWORDS, REPO_ROOT, stopword_lang_score


GERMAN_HINT_RE = re.compile(
    r"[ÄÖÜäöüß]|\b(Symphonie|INHALT|Entstehungszeit|Uraufführung|Fassung|Brüder|Freude|überm|Satz|Takt|Dirigent|Mitglieder)\b"
)


def _lang_score(text: str) -> tuple[int, int]:
    return stopword_lang_score(text, en_stopwords=EN_STOPWORDS, de_stopwords=DE_STOPWORDS_AUDIT)


@dataclass(frozen=True)
class PageBlock:
    page: int
    text: str


_PAGE_HEADER_RE = re.compile(r"^## \[PDF p\.(\d+)\]\s*$")


def _parse_booklet_en_pages(md: str) -> list[PageBlock]:
    lines = md.splitlines()
    blocks: list[PageBlock] = []

    current_page: int | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal current_page, buf
        if current_page is None:
            buf = []
            return
        text = "\n".join(buf).strip("\n")
        blocks.append(PageBlock(page=current_page, text=text))
        current_page = None
        buf = []

    for line in lines:
        m = _PAGE_HEADER_RE.match(line)
        if m:
            flush()
            current_page = int(m.group(1))
            continue
        if current_page is not None:
            buf.append(line)

    flush()
    return blocks


def _page_metrics(text: str) -> tuple[int, int, int, int]:
    """Return (en_score, de_score, hint_lines, nonempty_lines)."""

    en_total = 0
    de_total = 0
    hint_lines = 0
    nonempty = 0

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        nonempty += 1
        en, de = _lang_score(s)
        en_total += en
        de_total += de
        if GERMAN_HINT_RE.search(s):
            hint_lines += 1

    return en_total, de_total, hint_lines, nonempty


def _classify_page(en: int, de: int, hint_lines: int, nonempty: int) -> str:
    if nonempty == 0:
        return "empty"

    # Strong stopword signal.
    if en == 0 and de == 0:
        # Fall back to hints.
        return "hint-german" if hint_lines > 0 else "unknown"

    if de >= en + 2:
        return "german-dominant"
    if en >= de:
        return "english-dominant"
    return "mixed"


def _iter_booklet_en_files(root: Path) -> list[Path]:
    return sorted(root.glob("booklets/**/booklet_en.md"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit existing booklet_en.md files for German-dominant content by heuristic. "
            "Useful to catch extraction issues that can mask missing translations." 
        )
    )
    parser.add_argument(
        "--root",
        default=Path(REPO_ROOT),
        type=Path,
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--fail-on-german-pages",
        action="store_true",
        default=False,
        help="Exit with code 2 if any German-dominant pages are found",
    )
    parser.add_argument(
        "--show-top",
        type=int,
        default=8,
        help="Show top N most suspicious pages per file (default: 8)",
    )
    args = parser.parse_args()

    root: Path = args.root
    files = _iter_booklet_en_files(root)
    if not files:
        print("No booklet_en.md files found")
        return 0

    any_german = False

    for path in files:
        md = path.read_text(encoding="utf-8")
        pages = _parse_booklet_en_pages(md)

        counts: dict[str, int] = {}
        scored: list[tuple[float, int, str, int, int, int, int]] = []
        # (suspicion_score, page, cls, en, de, hint_lines, nonempty)

        for blk in pages:
            en, de, hint_lines, nonempty = _page_metrics(blk.text)
            cls = _classify_page(en, de, hint_lines, nonempty)
            counts[cls] = counts.get(cls, 0) + 1

            # Suspicion score: prioritize German-dominant pages with signal,
            # then hint-german pages with many hint lines.
            if en == 0 and de == 0:
                suspicion = float(hint_lines)
            else:
                suspicion = float(max(0, de - en)) + (hint_lines * 0.25)

            scored.append((suspicion, blk.page, cls, en, de, hint_lines, nonempty))

        german_pages = [p for p in scored if p[2] in {"german-dominant", "hint-german"}]
        if german_pages:
            any_german = True

        rel = path.relative_to(root)
        total = len(pages)
        ed = counts.get("english-dominant", 0)
        gd = counts.get("german-dominant", 0)
        hg = counts.get("hint-german", 0)
        mixed = counts.get("mixed", 0)
        unk = counts.get("unknown", 0)
        empty = counts.get("empty", 0)

        print(f"\n== {rel} ==")
        print(
            f"pages: {total} | english: {ed} | german: {gd} | hint-german: {hg} | mixed: {mixed} | unknown: {unk} | empty: {empty}"
        )

        if total == 0:
            continue

        scored_sorted = sorted(scored, key=lambda t: t[0], reverse=True)
        top = [t for t in scored_sorted if t[0] > 0][: args.show_top]
        if top:
            print("top suspicious pages:")
            for suspicion, page, cls, en, de, hint_lines, nonempty in top:
                print(
                    f"  p.{page:>3}: {cls:>14} | score={suspicion:.2f} | en={en} de={de} | hints={hint_lines}/{nonempty}"
                )

    if args.fail_on_german_pages and any_german:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
