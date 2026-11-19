from mnemonic.rag import SYSTEM_PROMPT, build_messages, valid_citations
from mnemonic.schemas import ClientMessage

from .fakes import make_hit

HITS = [make_hit(7), make_hit(12), make_hit(40)]


def ids(answer: str) -> list[int]:
    return [h.id for h in valid_citations(answer, HITS)]


def test_valid_citations_are_kept_in_order_of_first_mention():
    assert ids("Use Query [12]. Also see [7]. Again [12].") == [12, 7]


def test_unknown_citations_are_dropped():
    assert ids("Made up [999] and real [7].") == [7]


def test_grouped_citations_are_validated_one_by_one():
    assert ids("See [7, 999, 40].") == [7, 40]


def test_answer_without_citations_has_none():
    assert ids("Nothing cited here, maybe a list [a] or [].") == []


def test_prompt_has_server_system_message_and_numbered_chunks():
    history = [ClientMessage(role="user", content="How do I declare a query parameter?")]
    messages = build_messages(history, HITS)

    assert [m.role for m in messages] == ["system", "user"]
    system = messages[0].content
    assert system.startswith(SYSTEM_PROMPT.split("{context}")[0])
    for hit in HITS:
        assert f'<chunk id="{hit.id}"' in system
        assert hit.content in system
    assert messages[1].content == "How do I declare a query parameter?"
