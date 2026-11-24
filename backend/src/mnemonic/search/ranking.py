"""Ranking functions. Both return PER-TERM contributions per document (needed by explain);
the score of a document is the sum of its contributions.

TF-IDF:
    contribution = tf * log(N / df)
    A term that occurs in every document has idf = log(1) = 0, so it adds nothing
    (it cannot tell documents apart). No length normalisation, no tf saturation.

BM25 (k1 = 1.5, b = 0.75):
    idf          = log(1 + (N - df + 0.5) / (df + 0.5))        # never negative
    contribution = idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
    tf saturates (the 10th repeat adds far less than the 2nd) and long documents are
    penalised (dl = document length, avgdl = average length).

tf = occurrences of the term in the document, df = documents containing the term,
N = documents in the index.
"""

import math
from collections.abc import Callable, Collection

from mnemonic.search.index import InvertedIndex

K1 = 1.5
B = 0.75

Contributions = dict[int, dict[str, float]]  # internal doc idx -> term -> contribution


def idf_tf_idf(n: int, df: int) -> float:
    return math.log(n / df) if df else 0.0


def idf_bm25(n: int, df: int) -> float:
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


IDF: dict[str, Callable[[int, int], float]] = {"tfidf": idf_tf_idf, "bm25": idf_bm25}


def term_score(ranker: str, tf: int, df: int, n: int, dl: int, avgdl: float) -> float:
    """One term's contribution to one document: the single source of truth for scoring."""
    if tf == 0 or df == 0:
        return 0.0
    idf = IDF[ranker](n, df)
    if ranker == "tfidf":
        return tf * idf
    norm = 1 - B + B * dl / avgdl if avgdl else 1.0
    return idf * tf * (K1 + 1) / (tf + K1 * norm)


def _score(
    ranker: str, index: InvertedIndex, terms: Collection[str], doc_idxs: Collection[int]
) -> Contributions:
    n, avgdl = index.N, index.avgdl
    result: Contributions = {idx: {} for idx in doc_idxs}
    for term in terms:
        postings = index.postings(term)
        df = len(postings)
        for idx in doc_idxs:
            positions = postings.get(idx)
            if positions:
                result[idx][term] = term_score(
                    ranker, len(positions), df, n, index.doc_length(idx), avgdl
                )
    return result


def tf_idf(
    index: InvertedIndex, terms: Collection[str], doc_idxs: Collection[int]
) -> Contributions:
    return _score("tfidf", index, terms, doc_idxs)


def bm25(index: InvertedIndex, terms: Collection[str], doc_idxs: Collection[int]) -> Contributions:
    return _score("bm25", index, terms, doc_idxs)


RANKERS = {"tfidf": tf_idf, "bm25": bm25}
