"""Snippets: a ~160-char window around the densest cluster of matches.

The result carries plain text plus highlight offsets INTO that text, never HTML: the client
decides how to draw marks, so no markup from a document can be injected (XSS).
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Snippet:
    text: str
    highlights: list[tuple[int, int]] = field(default_factory=list)  # (start, end) in ``text``


def make_snippet(text: str, spans: list[tuple[int, int]], width: int = 160) -> Snippet:
    """``spans`` = (start, end) char offsets of matched words in ``text``.

    The window starts and ends on word boundaries (it may grow by one word on each side;
    a word is never cut).
    """
    spans = sorted(set(spans))
    if len(text) <= width:
        return Snippet(text, spans)
    if not spans:
        lo = 0
    else:
        # candidate windows start slightly before a match; pick the one covering most matches
        # spans are sorted and do not overlap, so starts and ends are both sorted: bisect counts
        starts = [s for s, _ in spans]
        ends = [e for _, e in spans]
        lo, best_count = 0, -1
        for start in starts:
            cand = max(0, start - 20)
            count = bisect_right(ends, cand + width) - bisect_left(starts, cand)
            if count > best_count:
                lo, best_count = cand, count
    hi = min(lo + width, len(text))
    # snap outwards to word boundaries
    while lo > 0 and not text[lo - 1].isspace() and not text[lo].isspace():
        lo -= 1
    while hi < len(text) and not text[hi - 1].isspace() and not text[hi].isspace():
        hi += 1
    window = text[lo:hi]
    stripped = window.lstrip()
    lo += len(window) - len(stripped)
    window = stripped.rstrip()
    highlights = [(s - lo, e - lo) for s, e in spans if s >= lo and e <= lo + len(window)]
    return Snippet(window, highlights)
