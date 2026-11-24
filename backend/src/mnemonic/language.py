"""Is a question written in a language the (English) knowledge base cannot answer?

Deliberately simple and dependency-free: count WORDS by script. Code is ignored first, and so are
Latin words that look like names or identifiers (`Depends`, `FastAPI`, `get_db`, `HTTP2`): a
Russian question around product names must still be recognised, an English one around a foreign
word must not."""

import re

_CODE = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)
_WORD = re.compile(r"\w+")
NON_LATIN_SHARE = 0.5  # "mostly": more than half of the counted words


def _is_latin_letter(ch: str) -> bool:
    # Basic Latin + Latin-1 + Latin Extended-A/B (accents: "naive", "Zurich" are not "foreign").
    return ch.isalpha() and ord(ch) < 0x250


def _looks_like_a_name(word: str, position: int) -> bool:
    """A Latin word that is probably an identifier or a product name, not prose: it has a digit
    or an underscore, or it is capitalised in the middle of the text."""
    return (
        any(ch.isdigit() or ch == "_" for ch in word)
        or (position > 0 and word[0].isupper())
        or (position == 0 and sum(ch.isupper() for ch in word) > 1)  # FastAPI, HTTPException
    )


def is_non_english(text: str) -> bool:
    """True when most of the prose words are not Latin (Cyrillic, CJK, Arabic, ...)."""
    foreign = latin = 0
    for position, word in enumerate(_WORD.findall(_CODE.sub(" ", text))):
        letters = [ch for ch in word if ch.isalpha()]
        if not letters:
            continue  # numbers, "422"
        if sum(not _is_latin_letter(ch) for ch in letters) * 2 > len(letters):
            foreign += 1
        elif not _looks_like_a_name(word, position):
            latin += 1
    return foreign > 0 and foreign / (foreign + latin) > NON_LATIN_SHARE
