"""Pure-Python search engine (no web framework, no database). See docs/labs/lab-15.md."""

from mnemonic.search.engine import Explanation, Hit, SearchEngine, TermExplanation
from mnemonic.search.index import IndexFormatError, InvertedIndex
from mnemonic.search.snippets import Snippet

__all__ = [
    "Explanation",
    "Hit",
    "IndexFormatError",
    "InvertedIndex",
    "SearchEngine",
    "Snippet",
    "TermExplanation",
]
