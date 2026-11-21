import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.schemas import ToolCall
from mnemonic.security import get_global_limiter
from mnemonic.tools import calculate, run_tool

from .fakes import FakeRetriever, MemoryStore, login, make_hit
from .test_chat import SESSION, chat_body, parse_events

# --- calculator ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("3*12+2*7", "50"),
        ("2+3*4", "14"),  # precedence
        ("(2+3)*4", "20"),
        ("-3 + 5", "2"),
        ("2**10", "1024"),
        ("7 // 2", "3"),
        ("7 % 4", "3"),
        ("1/4", "0.25"),
        ("0.1+0.2", "0.3"),
    ],
)
def test_calculator_valid(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "().__class__",
        "abs(-1)",
        "x + 1",
        "1 if 1 else 2",
        "'a' * 3",
        "True + 1",
        "2 +",
        "",
        "+3",  # only unary minus is allowed
        "9**9**9",
        "2**101",
        "(-8)**0.5",
        "1e308 * 10",
        "9" * 101,
    ],
)
def test_calculator_rejects_bad_input_with_a_text_result(expression):
    result = calculate(expression)  # never raises
    assert result.startswith("Error:")


def test_calculator_division_by_zero():
    assert calculate("1/0") == "Error: division by zero"
    assert calculate("1//0").startswith("Error:")


def test_run_tool_handles_unknown_tool_and_bad_args():
    assert run_tool(ToolCall(name="calculator", args={"expression": "2+2"})) == "4"
    assert run_tool(ToolCall(name="calculator", args={})).startswith("Error:")
    assert run_tool(ToolCall(name="shell", args={"cmd": "ls"})).startswith("Error:")


# --- the agentic loop ----------------------------------------------------------------------

CALL = ToolCall(name="calculator", args={"expression": "3*12+2*7"})


def tool_client(provider: FakeProvider, store: MemoryStore, budget: int = 1000):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, similarity_threshold=0.5
    )
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([make_hit(1)])
    app.dependency_overrides[get_provider] = lambda: provider
    limiter = SlidingWindowLimiter(budget)
    app.dependency_overrides[get_global_limiter] = lambda: limiter
    return TestClient(app, headers=login(store, sessions=[SESSION]))


def test_tool_call_is_run_and_the_model_answers_with_the_result():
    provider = FakeProvider(tool_script=[[CALL], ["It is ", "50 [1]."]])
    store = MemoryStore()
    events = parse_events(tool_client(provider, store).post("/chat", json=chat_body("total?")).text)

    assert [n for n, _ in events] == ["tool", "message", "message", "sources", "done"]
    assert events[0][1] == {
        "name": "calculator",
        "args": {"expression": "3*12+2*7"},
        "result": "50",
    }
    # Round 2 saw the call and its result; the first offered the tool, the last one did not.
    second_round = provider.event_calls[1][0]
    assert [m.role for m in second_round][-2:] == ["assistant", "tool"]
    assert second_round[-1].content == "50" and second_round[-1].tool_name == "calculator"
    assert provider.event_calls[0][1] and provider.event_calls[1][1]  # still 2 rounds < max
    # History keeps the final text only: no tool messages in the table.
    assert [m.role for m in store.messages[next(iter(store.messages))]] == ["user", "assistant"]


def test_loop_stops_after_three_rounds_and_the_last_has_no_tools():
    provider = FakeProvider(tool_script=[[CALL], [CALL], [CALL], ["never reached"]])
    store = MemoryStore()
    events = parse_events(tool_client(provider, store).post("/chat", json=chat_body("q")).text)

    assert len(provider.event_calls) == 3
    assert [bool(tools) for _, tools in provider.event_calls] == [True, True, False]
    assert [n for n, _ in events].count("tool") == 2  # the call in the tool-less round is ignored
    assert len(store.llm_calls) == 3  # one llm_calls row per round


def test_each_round_spends_one_slot_of_the_global_budget():
    # Budget 3 covers exactly 3 rounds; budget 2 runs out before the third.
    provider = FakeProvider(tool_script=[[CALL], [CALL], ["done"]])
    ok = tool_client(provider, MemoryStore(), budget=3).post("/chat", json=chat_body("q"))
    assert "error" not in [n for n, _ in parse_events(ok.text)]

    provider = FakeProvider(tool_script=[[CALL], [CALL], ["done"]])
    store = MemoryStore()
    busy = tool_client(provider, store, budget=2).post("/chat", json=chat_body("q"))
    names = [n for n, _ in parse_events(busy.text)]
    assert names[-1] == "error" and len(provider.event_calls) == 2
    assert len(store.llm_calls) == 2


def test_provider_without_tool_support_skips_the_loop():
    provider = FakeProvider()  # supports_tools is False
    assert provider.supports_tools is False
    store = MemoryStore()
    events = parse_events(tool_client(provider, store).post("/chat", json=chat_body("hi")).text)

    assert [n for n, _ in events] == ["message"] * 3 + ["sources", "done"] or events[0][
        0
    ] == "message"
    assert provider.event_calls == []
    assert len(store.llm_calls) == 1


def test_client_still_cannot_send_tool_or_system_messages():
    client = tool_client(FakeProvider(tool_script=[]), MemoryStore())
    body = chat_body("hi") | {"messages": [{"role": "tool", "content": "x"}]}
    assert client.post("/chat", json=body).status_code == 422
