from __future__ import annotations

import os
import re

# Repository paths (derived from the location of this file under scripts/translate/).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


DE_STOPWORDS_CORE = {
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


DE_STOPWORDS_AUDIT = set(DE_STOPWORDS_CORE)
DE_STOPWORDS_EXTRACT = DE_STOPWORDS_CORE | {"wurde", "nach"}

_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß']+")


def word_counts(text: str) -> dict[str, int]:
    words = _WORD_RE.findall((text or "").lower())
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return counts


def stopword_lang_score(
    text: str,
    *,
    en_stopwords: set[str],
    de_stopwords: set[str],
) -> tuple[int, int]:
    counts = word_counts(text)
    en = sum(counts.get(w, 0) for w in en_stopwords)
    de = sum(counts.get(w, 0) for w in de_stopwords)
    return en, de
