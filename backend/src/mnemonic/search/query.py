"""Query syntax: ``foo bar`` (all terms), ``"exact phrase"``, ``-word`` (exclude)."""

import re
from dataclasses import dataclass, field

from mnemonic.search.tokenizer import tokenize

_PART_RE = re.compile(r'"([^"]*)"?|(\S+)')


@dataclass(frozen=True)
class Phrase:
    # (term, offset from the first word); offsets keep stop-word gaps
    items: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Query:
    terms: list[str] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    @property
    def scoring_terms(self) -> list[str]:
        seen: dict[str, None] = {t: None for t in self.terms}
        for phrase in self.phrases:
            for term, _ in phrase.items:
                seen.setdefault(term)
        return list(seen)

    @property
    def has_positive(self) -> bool:
        return bool(self.terms or self.phrases)


def _wholes(text: str) -> list[tuple[int, str]]:
    """(position, term) with only the WHOLE token per position: the index also holds the parts,
    so ``response_model`` finds the identifier while ``model`` finds it through its part."""
    seen: dict[int, str] = {}
    for token in tokenize(text):
        seen.setdefault(token.position, token.term)
    return list(seen.items())


def parse_query(text: str) -> Query:
    terms: list[str] = []
    phrases: list[Phrase] = []
    excluded: list[str] = []
    for match in _PART_RE.finditer(text):
        quoted, word = match.groups()
        if quoted is not None:
            words = _wholes(quoted)
            if words:
                first = words[0][0]
                phrases.append(Phrase(tuple((term, pos - first) for pos, term in words)))
        elif word.startswith("-") and len(word) > 1:
            excluded.extend(term for _, term in _wholes(word[1:]))
        else:
            terms.extend(term for _, term in _wholes(word))
    return Query(list(dict.fromkeys(terms)), phrases, list(dict.fromkeys(excluded)))
