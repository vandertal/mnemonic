import json

import pytest

from mnemonic.search import IndexFormatError, InvertedIndex


def build() -> InvertedIndex:
    index = InvertedIndex()
    index.add_document("a", "apple banana apple")
    index.add_document("b", "banana cherry")
    return index


def test_add_builds_positional_postings():
    index = build()
    idx_a = index.idx("a")
    assert index.postings("apple") == {idx_a: [0, 2]}
    assert index.df("banana") == 2
    assert index.N == 2
    assert index.avgdl == pytest.approx(2.5)
    assert index.doc_length(idx_a) == 3


def test_unknown_term():
    index = build()
    assert index.df("zzz") == 0
    assert index.postings("zzz") == {}


def test_readding_replaces():
    index = build()
    index.add_document("a", "durian")
    assert index.N == 2
    assert index.df("apple") == 0
    assert index.df("durian") == 1
    assert index.avgdl == pytest.approx(1.5)


def test_remove():
    index = build()
    assert index.remove_document("a") is True
    assert index.N == 1
    assert index.df("apple") == 0
    assert "a" not in index
    assert index.remove_document("a") is False
    assert index.avgdl == pytest.approx(2.0)


def test_save_load_roundtrip(tmp_path):
    index = build()
    index.remove_document("a")
    index.add_document("c", "cherry apple")
    path = tmp_path / "index.json"
    index.save(path)
    loaded = InvertedIndex.load(path)
    assert loaded.N == index.N
    assert loaded.avgdl == index.avgdl
    for term in ("apple", "banana", "cherry"):
        assert {loaded.doc_id(i): p for i, p in loaded.postings(term).items()} == {
            index.doc_id(i): p for i, p in index.postings(term).items()
        }
    loaded.add_document("d", "banana")  # still usable, ids do not collide
    assert loaded.df("banana") == 2
    assert not list(tmp_path.glob("*.tmp"))  # no temp file left behind


def test_load_rejects_unknown_version(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"version": 999}), encoding="utf-8")
    with pytest.raises(IndexFormatError):
        InvertedIndex.load(path)


def test_failed_save_keeps_old_file(tmp_path, monkeypatch):
    path = tmp_path / "index.json"
    build().save(path)
    before = path.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("mnemonic.search.index.os.replace", boom)
    with pytest.raises(OSError):
        InvertedIndex().save(path)
    assert path.read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.tmp"))
