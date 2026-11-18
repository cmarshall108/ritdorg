"""Align a verse the reader knows with the same verse in a language they are learning.

Glosses are taken only from the target verse. Every target word is kept, every
native word receives a gloss when the target verse has words, and each gloss
carries the neighboring target words so a single token is not pulled out of
its sentence.
"""

from __future__ import annotations

import re
from collections import Counter

# Same split the reader uses for tappable words: whitespace, plus Hebrew maqaf.
_SPLIT = re.compile(r"[\s\u05BE]+")
_EDGE = ".,;:!?\"'“”‘’()[]{}<>«»—–…··։،؛؟。、・「」『』（）【】《》〈〉〔〕"
_WORDISH = re.compile(r"[^\W_]", re.UNICODE)
_RTL = re.compile(r"[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

# Longer prefixes first so "Aramaic" is not classified as Arabic.
_LANG_PREFIXES = (
    ("hungarian", "hu"),
    ("swahili", "sw"),
    ("hebrew", "he"),
    ("aramaic", "arc"),
    ("arabic", "ar"),
    ("spanish", "es"),
    ("french", "fr"),
    ("german", "de"),
    ("portuguese", "pt"),
    ("chinese", "zh"),
    ("japanese", "ja"),
    ("korean", "ko"),
    ("russian", "ru"),
    ("greek", "el"),
    ("italian", "it"),
    ("dutch", "nl"),
    ("polish", "pl"),
    ("ukrainian", "uk"),
    ("romanian", "ro"),
    ("turkish", "tr"),
    ("hindi", "hi"),
    ("bengali", "bn"),
    ("amharic", "am"),
    ("afrikaans", "af"),
    ("indonesian", "id"),
    ("vietnamese", "vi"),
    ("english", "en"),
    ("nasb", "en"),
    ("nkjv", "en"),
    ("kjv", "en"),
    ("esv", "en"),
    ("niv", "en"),
)


def word_core(token: str) -> str:
    """Strip punctuation the reader leaves attached to a visible word."""
    return (token or "").strip().strip(_EDGE).strip()


def verse_words(text: str) -> list[str]:
    """Return the words a verse will show as separate reading tokens."""
    words = []
    for raw in _SPLIT.split(text or ""):
        core = word_core(raw)
        if core and _WORDISH.search(core):
            words.append(core)
    return words


def text_dir(sample: str) -> str:
    return "rtl" if _RTL.search(sample or "") else "ltr"


def guess_lang(name: str) -> str:
    """Best-effort BCP-47 base code from a translation name. Empty if unknown."""
    folded = (name or "").lower()
    for prefix, code in sorted(_LANG_PREFIXES, key=lambda item: len(item[0]), reverse=True):
        if folded.startswith(prefix):
            return code
    return ""


def align_verse(native_text: str, target_text: str) -> list[dict]:
    """Map each native word to target words from the same verse.

    The mapping is monotonic. Extra target words stay attached to the nearest
    native word as a phrase, and a native word with no unique target word
    borrows the nearest one and is marked ``shared`` rather than left blank
    or assigned a word from outside the verse.
    """
    src = verse_words(native_text)
    tgt = verse_words(target_text)
    count = len(src)
    target_count = len(tgt)
    if count == 0:
        return []

    groups: list[list[int]] = [[] for _ in range(count)]
    if target_count:
        for index in range(target_count):
            slot = 0 if count == 1 else min(count - 1, (index * count) // target_count)
            groups[slot].append(index)
        for slot in range(count):
            if groups[slot]:
                continue
            left = next((i for i in range(slot - 1, -1, -1) if groups[i]), None)
            right = next((i for i in range(slot + 1, count) if groups[i]), None)
            if left is None and right is None:
                continue
            if right is None or (left is not None and slot - left <= right - slot):
                borrowed = groups[left][-1]
            else:
                borrowed = groups[right][0]
            groups[slot] = [borrowed]

    used = Counter(index for group in groups for index in group)
    aligned = []
    for slot, group in enumerate(groups):
        gloss_words = [tgt[index] for index in group]
        if group:
            start = max(0, min(group) - 1)
            end = min(target_count - 1, max(group) + 1)
            phrase = tgt[start:end + 1]
        else:
            phrase = []
        aligned.append({
            "word": src[slot],
            "gloss": " ".join(gloss_words),
            "gloss_words": gloss_words,
            "phrase": " ".join(phrase),
            "shared": any(used[index] > 1 for index in group),
            "target_span": [min(group), max(group)] if group else [],
        })
    return aligned
