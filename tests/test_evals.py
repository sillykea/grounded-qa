from grounded_qa.chunking import load_corpus
from grounded_qa.config import ROOT
from grounded_qa.evals import Case, check, load_cases, markdown, run, summarise
from grounded_qa.retrieval import Retriever


def test_dataset_is_valid_and_points_at_real_documents():
    cases = load_cases(ROOT / "evals" / "dataset.yaml")
    docs = {c.doc for c in load_corpus(ROOT / "corpus")}
    assert sum(not c.answerable for c in cases) >= 5
    for c in cases:
        for s in c.sources:
            assert s in docs, f"{c.id}: {s} is not in the corpus"


def test_scoring_with_a_fake_model():
    retriever = Retriever(load_corpus(ROOT / "corpus"))
    cases = [
        Case(
            "good",
            "How are console passwords hashed?",
            ["llm-gateway-console/docs/adr/0002-users-from-a-file.md", "llm-gateway-console/README.md"],
            ["pbkdf2", "600,?000"],
        ),
        Case("none", "Who is on call this week?", answerable=False),
    ]

    def chat(messages):
        q = messages[1]["content"].rsplit("Question: ", 1)[1]
        if "on call" in q:
            return "I don't know based on these documents."
        n = next(i for i, part in enumerate(messages[1]["content"].split("\n\n[")) if "PBKDF2" in part)
        n = n or 1
        return f"PBKDF2-SHA256 with 600,000 iterations [{n}]."

    results = run(cases, retriever, 4, chat)
    s = summarise(results, 4)
    assert results[0].passed, results[0]
    assert results[1].passed
    assert s["answer_pass_rate"] == 1 and s["correct_refusals"] == 1 and s["false_refusals"] == 0
    assert check(s, {"answer_pass_rate": 0.9, "false_refusals": 0.1}) == []
    assert check({"false_refusals": 0.2, "mrr": 0.5}, {"false_refusals": 0.1, "mrr": 0.6}) == [
        "false_refusals 0.200 is above 0.1",
        "mrr 0.500 is below 0.6",
    ]
    assert "Answers passing every check | 100%" in markdown(s, results, 4, {})


def test_a_wrong_answer_is_explained():
    retriever = Retriever(load_corpus(ROOT / "corpus"))
    cases = [
        Case(
            "x",
            "How are console passwords hashed?",
            ["llm-gateway-console/docs/adr/0002-users-from-a-file.md"],
            ["pbkdf2"],
        )
    ]
    results = run(cases, retriever, 4, lambda m: "With bcrypt [9].")
    report = markdown(summarise(results, 4), results, 4, {})
    assert "invalid citation" in report and "0/1 facts" in report
