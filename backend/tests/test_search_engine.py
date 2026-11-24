import math

import pytest

from mnemonic.search import SearchEngine


def engine_with(**docs: str) -> SearchEngine:
    engine = SearchEngine()
    for doc_id, text in docs.items():
        engine.add_document(doc_id, text)
    return engine


def ids(hits) -> list[str]:
    return [h.doc_id for h in hits]


# --- ranking -------------------------------------------------------------------------------
def test_bm25_hand_computed():
    # d1 = "apple pear" (dl 2), d2 = "apple apple pear pear pear pear" (dl 6), d3 = "grape pear" (2)
    # N = 3, avgdl = (2 + 6 + 2) / 3 = 10/3, df(apple) = 2
    # idf  = ln(1 + (3 - 2 + 0.5) / (2 + 0.5)) = ln(1.6) = 0.4700036
    # d1: tf=1, norm = 1 - 0.75 + 0.75 * 2 / (10/3) = 0.7
    #     score = 0.4700036 * 1 * 2.5 / (1 + 1.5 * 0.7) = 0.4700036 * 2.5 / 2.05 = 0.5731752
    # d2: tf=2, norm = 0.25 + 0.75 * 6 / (10/3) = 1.6
    #     score = 0.4700036 * 2 * 2.5 / (2 + 1.5 * 1.6) = 0.4700036 * 5 / 4.4 = 0.5340950
    engine = engine_with(d1="apple pear", d2="apple apple pear pear pear pear", d3="grape pear")
    hits = engine.search("apple")
    assert ids(hits) == ["d1", "d2"]
    assert hits[0].score == pytest.approx(0.5731751576, abs=1e-6)
    assert hits[1].score == pytest.approx(0.5340950332, abs=1e-6)


def test_tfidf_hand_computed():
    # idf = ln(3 / 2) = 0.4054651; d2 has tf=2 -> 0.8109302
    engine = engine_with(d1="apple pear", d2="apple apple pear pear pear pear", d3="grape pear")
    hits = engine.search("apple", ranker="tfidf")
    assert ids(hits) == ["d2", "d1"]
    assert hits[0].score == pytest.approx(2 * math.log(3 / 2), abs=1e-6)


def test_tfidf_is_zero_for_term_in_every_doc():
    engine = engine_with(a="common alpha", b="common beta")
    hits = engine.search("common", ranker="tfidf")
    assert [h.score for h in hits] == [0.0, 0.0]


def test_bm25_never_negative_for_common_term():
    engine = engine_with(a="common alpha", b="common beta", c="common gamma")
    assert all(h.score >= 0 for h in engine.search("common"))


def test_rare_term_outranks_common_term():
    docs = {f"d{i}": "common filler" for i in range(8)}
    docs["rare_doc"] = "unique filler"
    docs["common_doc"] = "common filler"
    engine = engine_with(**docs)
    hits = engine.search("common unique", mode="any")
    assert hits[0].doc_id == "rare_doc"


def test_length_normalisation_shorter_doc_wins_at_equal_tf():
    engine = engine_with(short="needle hay", long="needle " + "hay " * 30)
    assert ids(engine.search("needle")) == ["short", "long"]


# --- matching ------------------------------------------------------------------------------
def test_all_vs_any():
    engine = engine_with(both="red green", only_red="red blue", only_green="green blue")
    assert ids(engine.search("red green", mode="all")) == ["both"]
    assert set(ids(engine.search("red green", mode="any"))) == {"both", "only_red", "only_green"}
    assert engine.search("red green", mode="any")[0].doc_id == "both"


def test_phrase_requires_consecutive_terms():
    engine = engine_with(
        yes="we love fast api here", split="fast and furious api", reverse="api fast"
    )
    assert ids(engine.search('"fast api"')) == ["yes"]


def test_phrase_respects_stopword_gap():
    engine = engine_with(gap="use the dependency", nogap="use dependency", other="use a dependency")
    # the stop word "the" still occupies a position: exactly one word may sit between
    assert set(ids(engine.search('"use the dependency"'))) == {"gap", "other"}


def test_exclusion():
    engine = engine_with(a="python search", b="python java")
    assert ids(engine.search("python -java")) == ["a"]
    assert engine.search("-java") == []


def test_allowed_ids_filters_before_ranking():
    engine = engine_with(a="needle", b="needle needle needle", c="other")
    assert ids(engine.search("needle", allowed_ids={"a"})) == ["a"]
    assert engine.search("needle", allowed_ids=set()) == []
    assert engine.search("needle", allowed_ids={"unknown"}) == []


def test_limit():
    engine = engine_with(**{f"d{i}": "needle" for i in range(5)})
    assert len(engine.search("needle", limit=2)) == 2


def test_identifier_found_by_whole_and_by_part():
    engine = engine_with(a="pass response_model to the decorator", b="a model of a response")
    assert ids(engine.search("response_model")) == ["a"]
    assert set(ids(engine.search("model response"))) == {"a", "b"}


def test_matched_terms():
    engine = engine_with(a="red green blue")
    assert engine.search("blue red", mode="any")[0].matched_terms == ["blue", "red"]


def test_empty_query_and_empty_index():
    assert SearchEngine().search("anything") == []
    engine = engine_with(a="text")
    assert engine.search("") == []
    assert engine.search("   ") == []
    assert engine.search("the") == []  # only stop words
    assert engine.search("missing") == []


def test_invalid_options():
    engine = engine_with(a="text")
    with pytest.raises(ValueError):
        engine.search("text", mode="some")
    with pytest.raises(ValueError):
        engine.search("text", ranker="magic")


def test_remove_document_removes_hits():
    engine = engine_with(a="needle", b="needle")
    engine.remove_document("a")
    assert ids(engine.search("needle")) == ["b"]


# --- snippets via the engine ---------------------------------------------------------------
def test_hit_highlights_point_at_matched_words():
    text = " ".join(f"word{i}" for i in range(80)) + " the Depends function " + "end " * 80
    engine = engine_with(a=text)
    hit = engine.search("depends")[0]
    assert [hit.snippet.text[s:e] for s, e in hit.snippet.highlights] == ["Depends"]


# --- explain -------------------------------------------------------------------------------
@pytest.mark.parametrize("ranker", ["bm25", "tfidf"])
def test_explain_sums_to_score(ranker):
    engine = engine_with(a="red green green", b="red blue", c="yellow")
    hit = engine.search("red green", mode="any", ranker=ranker)[0]
    explanation = engine.explain("red green", hit.doc_id, ranker=ranker)
    assert explanation.score == pytest.approx(hit.score)
    by_term = {t.term: t for t in explanation.terms}
    assert by_term["green"].tf == 2
    assert by_term["green"].df == 1
    assert by_term["red"].df == 2
    assert by_term["red"].doc_length == 3


def test_explain_unknown_doc():
    with pytest.raises(KeyError):
        engine_with(a="x").explain("x", "nope")
