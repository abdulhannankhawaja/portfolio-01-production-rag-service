from app.generation import Generator
from eval.run_evaluation import answer_metrics, load_and_validate_cases, retrieval_metrics


def test_golden_set_evidence_matches_declared_source_pages():
    cases = load_and_validate_cases()

    assert len(cases) == 25
    assert sum(case["answerable"] for case in cases) == 20


def test_page_recall_counts_relevant_pages_not_question_hits():
    cases = [
        {
            "answerable": True,
            "document": "rmf.pdf",
            "pages": [1, 2],
        },
        {
            "answerable": True,
            "document": "profile.pdf",
            "pages": [3],
        },
    ]
    retrieved = [
        (
            cases[0],
            [{"filename": "rmf.pdf", "page": 2}],
        ),
        (
            cases[1],
            [
                {"filename": "other.pdf", "page": 3},
                {"filename": "profile.pdf", "page": 3},
            ],
        ),
    ]

    metrics = retrieval_metrics(retrieved)

    assert metrics["hit_rate_at_5"] == 1.0
    assert metrics["page_recall_at_5"] == 2 / 3
    assert metrics["mrr_at_5"] == 0.75


def test_threshold_sweep_measures_refusal_and_answer_key_terms():
    answerable = {
        "answerable": True,
        "answer_key_terms": ["risk management"],
        "document": "guide.pdf",
        "pages": [1],
        "question": "What is important?",
    }
    unanswerable = {
        "answerable": False,
        "answer_key_terms": [],
        "document": "",
        "pages": [],
        "question": "What is unrelated?",
    }
    retrieved = [
        (
            answerable,
            [{
                "text": "A culture of risk management is important.",
                "filename": "guide.pdf",
                "page": 1,
                "score": 0.7,
            }],
        ),
        (
            unanswerable,
            [{
                "text": "A culture of risk management is important.",
                "filename": "guide.pdf",
                "page": 1,
                "score": 0.6,
            }],
        ),
    ]

    metrics = answer_metrics(retrieved, 0.65, Generator(None, "local"))

    assert metrics["answerable_response_rate"] == 1.0
    assert metrics["answer_key_term_coverage"] == 1.0
    assert metrics["out_of_corpus_refusal_rate"] == 1.0
    assert metrics["balanced_abstention_accuracy"] == 1.0


def test_local_generator_selects_query_relevant_sentences_and_cites_their_chunks():
    generator = Generator(None, "local")
    chunks = [
        {
            "text": "The document discusses general AI system deployment.",
            "filename": "guide.pdf",
            "page": 1,
        },
        {
            "text": "GOVERN cultivates and implements a culture of risk management.",
            "filename": "guide.pdf",
            "page": 2,
        },
    ]

    answer = generator.generate("What culture does GOVERN cultivate?", chunks)

    assert answer.model == "extractive-local"
    assert "culture of risk management" in answer.answer.lower()
    assert answer.cited_chunk_ids == ["retrieved-2"]
