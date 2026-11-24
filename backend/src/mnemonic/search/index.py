"""Positional inverted index.

``postings[term][internal_doc_idx] = [position, ...]``. Looking a term up is a dict access
(O(1)); we never scan documents. Internal ids are small ints (cheaper than strings in every
posting); ``doc_id`` strings are kept in one table. Internal ids are never reused.

Document length = number of word positions that carry an indexed token (parts of an identifier
share the position of the whole, so they do not inflate the length).
"""

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from mnemonic.search.tokenizer import tokenize

FORMAT_VERSION = 1


class IndexFormatError(ValueError):
    pass


class InvertedIndex:
    def __init__(self) -> None:
        self._postings: dict[str, dict[int, list[int]]] = {}
        self._doc_ids: dict[int, str] = {}  # internal idx -> doc_id
        self._idx_of: dict[str, int] = {}  # doc_id -> internal idx
        self._lengths: dict[int, int] = {}
        self._doc_terms: dict[int, set[str]] = {}  # for fast removal
        self._total_length = 0
        self._next_idx = 0

    # --- writing -----------------------------------------------------------------------
    def add_document(self, doc_id: str, text: str) -> None:
        """Index ``text``. Adding an existing ``doc_id`` replaces the old version."""
        self.remove_document(doc_id)
        idx = self._next_idx
        self._next_idx += 1
        positions_seen: set[int] = set()
        terms: set[str] = set()
        for token in tokenize(text):
            self._postings.setdefault(token.term, {}).setdefault(idx, []).append(token.position)
            positions_seen.add(token.position)
            terms.add(token.term)
        self._doc_ids[idx] = doc_id
        self._idx_of[doc_id] = idx
        self._lengths[idx] = len(positions_seen)
        self._doc_terms[idx] = terms
        self._total_length += len(positions_seen)

    def remove_document(self, doc_id: str) -> bool:
        idx = self._idx_of.pop(doc_id, None)
        if idx is None:
            return False
        for term in self._doc_terms.pop(idx):
            docs = self._postings[term]
            del docs[idx]
            if not docs:
                del self._postings[term]
        self._total_length -= self._lengths.pop(idx)
        del self._doc_ids[idx]
        return True

    # --- reading -----------------------------------------------------------------------
    def postings(self, term: str) -> Mapping[int, list[int]]:
        return self._postings.get(term, {})

    def df(self, term: str) -> int:
        return len(self._postings.get(term, ()))

    @property
    def N(self) -> int:  # noqa: N802 - the textbook name
        return len(self._doc_ids)

    @property
    def avgdl(self) -> float:
        return self._total_length / self.N if self.N else 0.0

    @property
    def terms_count(self) -> int:
        return len(self._postings)

    def doc_length(self, idx: int) -> int:
        return self._lengths[idx]

    def doc_id(self, idx: int) -> str:
        return self._doc_ids[idx]

    def idx(self, doc_id: str) -> int | None:
        return self._idx_of.get(doc_id)

    def __contains__(self, doc_id: str) -> bool:
        return doc_id in self._idx_of

    # --- persistence -------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        """Write JSON atomically: temp file in the same folder, then ``os.replace``.

        A crash mid-write leaves the old file intact instead of a half-written one.
        """
        path = Path(path)
        data = {
            "version": FORMAT_VERSION,
            "next_idx": self._next_idx,
            "docs": {str(i): [d, self._lengths[i]] for i, d in self._doc_ids.items()},
            "postings": {
                t: {str(i): p for i, p in docs.items()} for t, docs in self._postings.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: str | Path) -> "InvertedIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
            version = data.get("version") if isinstance(data, dict) else None
            raise IndexFormatError(
                f"unsupported index version {version!r}, expected {FORMAT_VERSION}"
            )
        index = cls()
        index._next_idx = data["next_idx"]
        for key, (doc_id, length) in data["docs"].items():
            idx = int(key)
            index._doc_ids[idx] = doc_id
            index._idx_of[doc_id] = idx
            index._lengths[idx] = length
            index._doc_terms[idx] = set()
            index._total_length += length
        for term, docs in data["postings"].items():
            index._postings[term] = {int(i): p for i, p in docs.items()}
            for i in docs:
                index._doc_terms[int(i)].add(term)
        return index
