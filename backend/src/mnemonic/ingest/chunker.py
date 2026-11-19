"""Markdown -> overlapping token-sized chunks. Pure: no network, no database."""

import re
from dataclasses import dataclass
from typing import Protocol

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_ANCHOR = re.compile(r"\s*\{\s*#[^}]*\}\s*$")  # MkDocs "{ #custom-id }" suffix
_FENCE = re.compile(r"^\s*(```|~~~)")


class Encoding(Protocol):
    offsets: list[tuple[int, int]]


class Tokenizer(Protocol):
    """The slice of `tokenizers.Tokenizer` we need (so tests can pass a fake)."""

    def encode(self, text: str, add_special_tokens: bool = ...) -> Encoding: ...


@dataclass(frozen=True)
class Chunk:
    file_path: str
    heading: str  # "H1 > H2 > H3" path of the section the chunk belongs to
    chunk_index: int  # position inside the file, starting at 0
    content: str


def _sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading path, body) pairs. '#' inside code fences is not a heading."""
    sections: list[tuple[str, str]] = []
    path: list[tuple[int, str]] = []  # (level, title)
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            sections.append((" > ".join(t for _, t in path), text))
        body.clear()

    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, _ANCHOR.sub("", match.group(2))))
        else:
            body.append(line)
    flush()
    return sections


def _windows(text: str, tokenizer: Tokenizer, max_tokens: int, overlap: int) -> list[str]:
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    if len(offsets) <= max_tokens:
        return [text]
    step = max_tokens - overlap
    pieces = []
    for start in range(0, len(offsets), step):
        end = min(start + max_tokens, len(offsets))
        pieces.append(text[offsets[start][0] : offsets[end - 1][1]])
        if end == len(offsets):
            break
    return pieces


def chunk_markdown(
    markdown: str,
    file_path: str,
    tokenizer: Tokenizer,
    max_tokens: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """Chunks never cross a heading; a long section is cut into windows of `max_tokens`
    tokens, each starting `max_tokens - overlap` tokens after the previous one."""
    if not 0 <= overlap < max_tokens:
        raise ValueError("overlap must be >= 0 and < max_tokens")
    chunks: list[Chunk] = []
    for heading, body in _sections(markdown):
        for piece in _windows(body, tokenizer, max_tokens, overlap):
            chunks.append(Chunk(file_path, heading, len(chunks), piece))
    return chunks
