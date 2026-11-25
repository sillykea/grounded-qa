from grounded_qa.answer import REFUSAL, answer, build_messages, is_refusal, parse_citations
from grounded_qa.chunking import Chunk

SOURCES = [
    Chunk("a#0", "ledger/a.md", "ADR 3", "Keys are stored in the same transaction."),
    Chunk("b#0", "ledger/b.md", "README", "Retries replay the stored response."),
]


def test_citations():
    assert parse_citations("Yes [1]. Also [2, 1] and [7].", 2) == ([1, 2], [7])
    assert parse_citations("No citations.", 2) == ([], [])


def test_refusal_detection():
    assert is_refusal(REFUSAL)
    assert is_refusal("The sources don't mention that.")
    assert not is_refusal("It stores the key [1].")


def test_answer_maps_citations_to_chunks():
    seen = {}

    def chat(messages):
        seen["messages"] = messages
        return "It stores the key with the posting [1] and replays it [2]. See also [3]."

    a = answer("How?", SOURCES, chat)
    assert [c.doc for c in a.cited_chunks] == ["ledger/a.md", "ledger/b.md"]
    assert a.invalid_citations == [3] and not a.refused
    user = seen["messages"][1]["content"]
    assert "[1] (ledger: ADR 3)" in user and user.endswith("Question: How?")
    d = a.to_dict()
    assert d["citations"][0]["url"].startswith("https://github.com/sillykea/ledger/")


def test_no_sources_means_refusal_without_calling_the_model():
    a = answer("Anything?", [], lambda m: (_ for _ in ()).throw(AssertionError("called")))
    assert a.refused


def test_prompt_instructs_refusal_phrase():
    assert REFUSAL in build_messages("q", SOURCES)[0]["content"]
