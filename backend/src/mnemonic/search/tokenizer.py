"""Code-aware unicode tokenizer.

Pipeline: NFKC normalisation -> tokens by ``\\w+`` (dots between word characters stay inside
one token, so ``fastapi.security`` is one token) -> casefold.

Identifiers are queries people type, so for a token with several parts
(``response_model``, ``OAuth2PasswordBearer``, ``fastapi.security``) we emit the WHOLE token
first and then each PART.

POSITION RULE: ``position`` is the index of the *word* in the text (0, 1, 2, ...). A whole token
and all its parts share ONE position, so they never push the following words away and phrase
search stays "consecutive words". Stop words are dropped from the output, but they still take
a position, so there is a gap where they were (``use the dependency`` -> use@0, dependency@2).

``start``/``end`` are char offsets into the NFKC-normalised text. Parts reuse the offsets of
the whole token (a snippet highlights the whole identifier).
"""

import re
import unicodedata
from dataclasses import dataclass

from mnemonic.search.stopwords import STOPWORDS

# word characters, optionally joined by dots: "fastapi.security", but not "end." at a sentence end
TOKEN_RE = re.compile(r"\w+(?:\.\w+)*")


@dataclass(frozen=True)
class Token:
    term: str
    position: int
    start: int
    end: int


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def word_starts(text: str) -> list[int]:
    """Char offset where each word (position 0, 1, 2, ...) starts in ``normalize(text)``.

    Lets the engine turn a posting position back into a place in the text without
    re-tokenizing the document at query time.
    """
    return [m.start() for m in TOKEN_RE.finditer(normalize(text))]


def _split_camel(word: str) -> list[str]:
    """``OAuth2PasswordBearer`` -> ``O, Auth2, Password, Bearer``; digits stay with letters."""
    parts: list[str] = []
    current = ""
    for i, ch in enumerate(word):
        if current:
            prev = word[i - 1]
            nxt = word[i + 1] if i + 1 < len(word) else ""
            lower_to_upper = ch.isupper() and (prev.islower() or prev.isdigit())
            acronym_end = ch.isupper() and prev.isupper() and nxt.islower()
            if lower_to_upper or acronym_end:
                parts.append(current)
                current = ""
        current += ch
    if current:
        parts.append(current)
    return parts


def _parts(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[_.]+", raw):
        if chunk:
            parts.extend(_split_camel(chunk))
    return parts


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[Token]:
    tokens: list[Token] = []
    for position, match in enumerate(TOKEN_RE.finditer(normalize(text))):
        raw = match.group()
        whole = raw.casefold()
        start, end = match.start(), match.end()
        if drop_stopwords and whole in STOPWORDS:
            continue  # the position is already spent: that is the gap
        tokens.append(Token(whole, position, start, end))
        parts = _parts(raw)
        if len(parts) > 1:
            seen = {whole}
            for part in parts:
                term = part.casefold()
                if term in seen or (drop_stopwords and term in STOPWORDS):
                    continue
                seen.add(term)
                tokens.append(Token(term, position, start, end))
    return tokens
