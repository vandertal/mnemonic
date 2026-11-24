"""Search engine: parse query -> candidate docs -> rank -> snippets.

The engine keeps the (NFKC-normalised) text of every document next to the index so it can build
snippets. ``add_document`` / ``remove_document`` update both.
"""

from array import array
from collections.abc import Collection
from dataclasses import dataclass, field

from mnemonic.search.index import InvertedIndex
from mnemonic.search.query import Phrase, Query, parse_query
from mnemonic.search.ranking import IDF, RANKERS, term_score
from mnemonic.search.snippets import Snippet, make_snippet
from mnemonic.search.tokenizer import TOKEN_RE, normalize, word_starts


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float
    snippet: Snippet
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TermExplanation:
    term: str
    tf: int
    df: int
    idf: float
    doc_length: int
    contribution: float


@dataclass(frozen=True)
class Explanation:
    doc_id: str
    ranker: str
    n_docs: int
    avgdl: float
    terms: list[TermExplanation]

    @property
    def score(self) -> float:
        return sum(t.contribution for t in self.terms)


class SearchEngine:
    def __init__(self, index: InvertedIndex | None = None) -> None:
        self.index = index or InvertedIndex()
        self._texts: dict[str, str] = {}
        self._starts: dict[str, array] = {}  # doc_id -> char offset of every word position

    def add_document(self, doc_id: str, text: str) -> None:
        self.index.add_document(doc_id, text)
        self._texts[doc_id] = normalize(text)
        self._starts[doc_id] = array("I", word_starts(text))

    def remove_document(self, doc_id: str) -> bool:
        self._texts.pop(doc_id, None)
        self._starts.pop(doc_id, None)
        return self.index.remove_document(doc_id)

    # --- matching ----------------------------------------------------------------------
    def _phrase_docs(self, phrase: Phrase) -> set[int]:
        """Docs where the phrase words sit at the exact relative offsets (positional join)."""
        if not phrase.items:
            return set()
        docs = set.intersection(*(set(self.index.postings(t)) for t, _ in phrase.items))
        found: set[int] = set()
        first_term, first_off = phrase.items[0]
        for idx in docs:
            starts = self.index.postings(first_term)[idx]
            others = [
                (set(self.index.postings(t)[idx]), off - first_off) for t, off in phrase.items
            ]
            if any(all(p + off in pos for pos, off in others) for p in starts):
                found.add(idx)
        return found

    def _candidates(self, query: Query, mode: str) -> set[int]:
        units: list[set[int]] = [set(self.index.postings(t)) for t in query.terms]
        units += [self._phrase_docs(p) for p in query.phrases]
        if not units:
            return set()
        found = set.intersection(*units) if mode == "all" else set.union(*units)
        for term in query.excluded:
            found -= set(self.index.postings(term))
        return found

    # --- public API --------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        mode: str = "all",
        limit: int = 10,
        allowed_ids: Collection[str] | None = None,
        ranker: str = "bm25",
    ) -> list[Hit]:
        """``mode="all"``: every term and phrase must match (AND). ``"any"``: union, ranked."""
        if mode not in ("all", "any"):
            raise ValueError(f"unknown mode {mode!r}")
        if ranker not in RANKERS:
            raise ValueError(f"unknown ranker {ranker!r}")
        parsed = parse_query(query)
        if limit <= 0 or not parsed.has_positive or self.index.N == 0:
            return []
        candidates = self._candidates(parsed, mode)
        if allowed_ids is not None:  # filter BEFORE ranking
            allowed = {i for i in map(self.index.idx, allowed_ids) if i is not None}
            candidates &= allowed
        if not candidates:
            return []
        terms = parsed.scoring_terms
        scored = RANKERS[ranker](self.index, terms, candidates)
        ranked = sorted(
            ((sum(c.values()), self.index.doc_id(idx), c) for idx, c in scored.items()),
            key=lambda row: (-row[0], row[1]),
        )[:limit]
        hits = []
        for score, doc_id, contributions in ranked:
            matched = [t for t in terms if t in contributions]
            hits.append(Hit(doc_id, score, self._snippet(doc_id, matched), matched))
        return hits

    def _snippet(self, doc_id: str, terms: list[str]) -> Snippet:
        """Matched words come from the postings (word positions) -> offsets: no re-tokenizing."""
        text, starts = self._texts.get(doc_id), self._starts.get(doc_id)
        if text is None or starts is None:
            return Snippet("")
        idx = self.index.idx(doc_id)
        positions = {p for t in terms for p in self.index.postings(t).get(idx, ())}
        spans = []
        for pos in sorted(positions):
            start = starts[pos]
            spans.append((start, TOKEN_RE.match(text, start).end()))
        return make_snippet(text, spans)

    def explain(self, query: str, doc_id: str, *, ranker: str = "bm25") -> Explanation:
        """Per-term tf, df, idf, doc length and contribution; contributions sum to the score."""
        if ranker not in RANKERS:
            raise ValueError(f"unknown ranker {ranker!r}")
        idx = self.index.idx(doc_id)
        if idx is None:
            raise KeyError(doc_id)
        n, avgdl, dl = self.index.N, self.index.avgdl, self.index.doc_length(idx)
        rows = []
        for term in parse_query(query).scoring_terms:
            df = self.index.df(term)
            tf = len(self.index.postings(term).get(idx, ()))
            rows.append(
                TermExplanation(
                    term, tf, df, IDF[ranker](n, df) if df else 0.0, dl,
                    term_score(ranker, tf, df, n, dl, avgdl),
                )
            )  # fmt: skip
        return Explanation(doc_id, ranker, n, avgdl, rows)
