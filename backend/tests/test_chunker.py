import re
from types import SimpleNamespace

import pytest

from mnemonic.ingest.chunker import chunk_markdown


class WordTokenizer:
    """Offline stand-in for the bge tokenizer: one token per whitespace-separated word."""

    def encode(self, text, add_special_tokens=True):
        return SimpleNamespace(offsets=[m.span() for m in re.finditer(r"\S+", text)])


TOK = WordTokenizer()


def words(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_section_is_one_chunk_with_metadata():
    chunks = chunk_markdown("# Title\n\nhello world", "a/b.md", TOK)
    assert len(chunks) == 1
    c = chunks[0]
    assert (c.file_path, c.heading, c.chunk_index, c.content) == (
        "a/b.md",
        "Title",
        0,
        "hello world",
    )


def test_heading_path_nests_and_resets():
    md = "# A\n\nx\n\n## B\n\ny\n\n### C\n\nz\n\n## D\n\nq\n"
    assert [c.heading for c in chunk_markdown(md, "f.md", TOK)] == [
        "A",
        "A > B",
        "A > B > C",
        "A > D",
    ]


def test_hash_inside_code_fence_is_not_a_heading():
    md = "# A\n\n```python\n# comment\nx = 1\n```\n"
    chunks = chunk_markdown(md, "f.md", TOK)
    assert len(chunks) == 1
    assert "# comment" in chunks[0].content


def test_chunks_do_not_exceed_max_tokens():
    chunks = chunk_markdown("# T\n\n" + words(1234), "f.md", TOK, max_tokens=100, overlap=10)
    assert len(chunks) > 1
    assert all(len(c.content.split()) <= 100 for c in chunks)


def test_consecutive_chunks_overlap_by_exactly_overlap_tokens():
    chunks = chunk_markdown("# T\n\n" + words(300), "f.md", TOK, max_tokens=100, overlap=10)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert prev.content.split()[-10:] == nxt.content.split()[:10]


def test_whole_text_is_covered_without_gaps():
    chunks = chunk_markdown("# T\n\n" + words(250), "f.md", TOK, max_tokens=100, overlap=10)
    seen = {w for c in chunks for w in c.content.split()}
    assert seen == set(words(250).split())


def test_chunk_index_is_sequential_across_sections():
    md = "# A\n\n" + words(150) + "\n\n# B\n\nshort"
    chunks = chunk_markdown(md, "f.md", TOK, max_tokens=100, overlap=10)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_empty_sections_are_skipped():
    assert chunk_markdown("# A\n\n# B\n\n", "f.md", TOK) == []


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        chunk_markdown("x", "f.md", TOK, max_tokens=10, overlap=10)


def test_mkdocs_anchor_is_stripped_from_heading():
    chunks = chunk_markdown("# Title { #title }\n\n## Sub { #sub-id }\n\ntext", "f.md", TOK)
    assert chunks[0].heading == "Title > Sub"
