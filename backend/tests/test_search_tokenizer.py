from mnemonic.search.snippets import make_snippet
from mnemonic.search.tokenizer import tokenize


def terms(text: str) -> list[str]:
    return [t.term for t in tokenize(text)]


def test_punctuation_is_dropped_and_case_folded():
    assert terms("Hello, WORLD!") == ["hello", "world"]


def test_ukrainian_text():
    assert terms("Привіт, Світе! Їжак") == ["привіт", "світе", "їжак"]


def test_nfkc_normalisation():
    assert terms("ﬁle") == ["file"]  # ligature fi -> "fi"


def test_snake_case_emits_whole_and_parts_at_same_position():
    tokens = tokenize("use response_model now")
    by_term = {t.term: t.position for t in tokens}
    assert by_term["response_model"] == by_term["response"] == by_term["model"] == 1
    assert by_term["now"] == 2


def test_camel_case_parts_share_position():
    tokens = tokenize("OAuth2PasswordBearer")
    assert [t.term for t in tokens] == ["oauth2passwordbearer", "o", "auth2", "password", "bearer"]
    assert {t.position for t in tokens} == {0}


def test_dotted_name():
    tokens = tokenize("import fastapi.security")
    assert [t.term for t in tokens] == ["import", "fastapi.security", "fastapi", "security"]
    assert {t.position for t in tokens[1:]} == {1}


def test_digits_stay_with_letters():
    assert "auth2" in terms("OAuth2Password")


def test_acronym_split():
    assert terms("HTTPException") == ["httpexception", "http", "exception"]


def test_stop_words_dropped_but_positions_advance():
    tokens = tokenize("use the dependency")
    assert [(t.term, t.position) for t in tokens] == [("use", 0), ("dependency", 2)]


def test_offsets_point_at_the_token():
    text = "Use Depends here"
    token = tokenize(text)[1]
    assert text[token.start : token.end] == "Depends"


def test_empty_text():
    assert tokenize("") == []


# --- snippets (kept here: they depend on token offsets) ------------------------------------
def test_snippet_short_text_is_whole():
    text = "short text with Depends"
    spans = [(t.start, t.end) for t in tokenize(text) if t.term == "depends"]
    snippet = make_snippet(text, spans)
    assert snippet.text == text
    assert [snippet.text[s:e] for s, e in snippet.highlights] == ["Depends"]


def test_snippet_snaps_to_word_boundaries_and_highlights_match():
    text = (
        " ".join(f"filler{i}" for i in range(60))
        + " the Depends marker "
        + " ".join(f"tail{i}" for i in range(60))
    )
    spans = [(t.start, t.end) for t in tokenize(text) if t.term == "depends"]
    snippet = make_snippet(text, spans)
    assert 100 < len(snippet.text) < 220
    words = set(text.split())
    assert snippet.text.split()[0] in words  # first word is a whole word
    assert snippet.text.split()[-1] in words  # last word is a whole word
    assert [snippet.text[s:e] for s, e in snippet.highlights] == ["Depends"]


def test_snippet_picks_densest_region():
    far = "alpha " + "x " * 200
    dense = "alpha beta alpha beta alpha"
    text = far + dense + " y" * 100
    spans = [(t.start, t.end) for t in tokenize(text) if t.term in {"alpha", "beta"}]
    snippet = make_snippet(text, spans)
    assert len(snippet.highlights) == 5
