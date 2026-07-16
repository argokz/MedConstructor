"""Russian morphology helpers (pymorphy3) for relevance matching.

Used to lemmatise assignment text and catalog block names so that the palette
matches by *lemma* (инфаркте → инфаркт) instead of naive substring (which made
"боль" match "больным" and surfaced clinically unrelated blocks).
"""
from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

# Functional parts of speech carry no clinical signal — drop them so that
# stop-words ("в", "на", "и", "при", "у") never become match keys.
_FUNCTIONAL_POS = frozenset({"PREP", "CONJ", "PRCL", "INTJ", "NPRO", "Apro"})

# Generic case/clinical filler that survives POS filtering but is noise for
# block relevance (present in almost every scenario description).
_EXTRA_STOPWORDS = frozenset({
    "пациент", "больной", "год", "лет", "история", "необходимо", "определить",
    "дальнейший", "шаг", "жалоба", "обратиться", "отделение", "содержать",
    "выявляться", "данный", "это", "который", "проводить", "иметь", "ваш",
})

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-]*", flags=re.UNICODE)

_analyzer: pymorphy3.MorphAnalyzer | None = None


def _get_analyzer() -> pymorphy3.MorphAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = pymorphy3.MorphAnalyzer()
    return _analyzer


@lru_cache(maxsize=100_000)
def lemmatize_word(word: str) -> str | None:
    """Return the normal form of a single token, or None if it should be dropped."""
    token = word.strip("-").lower()
    if len(token) < 3:
        return None

    # Latin tokens (e.g. drug abbreviations) are kept verbatim — no RU morphology.
    if token.isascii():
        return token

    parsed = _get_analyzer().parse(token)
    if not parsed:
        return None
    best = parsed[0]
    pos = best.tag.POS
    if pos in _FUNCTIONAL_POS:
        return None
    return best.normal_form


@lru_cache(maxsize=200_000)
def lemmas(text: str | None) -> frozenset[str]:
    """Lemmatise free text into a set of significant content lemmas.

    Cached per phrase so repeated catalog-name lookups across palette requests
    are O(1) after the first pass.
    """
    if not text:
        return frozenset()

    result: set[str] = set()
    for match in _TOKEN_RE.findall(text):
        lemma = lemmatize_word(match)
        if lemma and lemma not in _EXTRA_STOPWORDS:
            result.add(lemma)
    return frozenset(result)


def overlap_score(query_lemmas: frozenset[str], candidate: str | None) -> int:
    """Number of shared lemmas between a query and a candidate block name."""
    if not query_lemmas or not candidate:
        return 0
    return len(query_lemmas & lemmas(candidate))
