import csv
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from importlib.metadata import PackageNotFoundError, version

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.generation import Generator
from app.ingestion import clean_text, extract_pdf, split_text


CORPUS_DIR = ROOT / "corpus"
GOLDEN_PATH = ROOT / "eval" / "golden.json"
OUTPUT_PATH = ROOT / "docs" / "EVAL.md"
RESULTS_DIR = ROOT / "eval" / "results"
REFUSAL_TEXT = "The documents do not contain enough information to answer this question."
TOP_K = 5
CHUNK_CONFIGURATIONS = ((400, 100), (500, 100))
THRESHOLDS: tuple[float, ...] = (
    0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
    0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94, 0.96,
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def load_and_validate_cases() -> list[dict]:
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if not cases:
        raise ValueError("The evaluation set is empty")
    ids = [case.get("id") for case in cases]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("Every evaluation case must have a unique, non-empty id")

    documents: dict[str, list[str]] = {}
    for case in cases:
        if case["answerable"]:
            filename = case["document"]
            path = CORPUS_DIR / filename
            if not path.is_file():
                raise ValueError(f"{case['id']}: source document does not exist: {filename}")
            if filename not in documents:
                with pymupdf.open(path) as document:
                    documents[filename] = [
                        clean_text(page.get_text("text"))
                        for page in document
                    ]
            evidence = case.get("evidence", [])
            if not evidence or not case.get("answer_key_terms"):
                raise ValueError(f"{case['id']}: answerable cases need evidence and answer key terms")
            evidence_pages = set()
            for item in evidence:
                page_number = item["page"]
                if page_number < 1 or page_number > len(documents[filename]):
                    raise ValueError(f"{case['id']}: evidence page is outside {filename}")
                page_text = normalize(documents[filename][page_number - 1])
                if normalize(item["text"]) not in page_text:
                    raise ValueError(
                        f"{case['id']}: evidence is not present on "
                        f"{filename} page {page_number}: {item['text']}"
                    )
                evidence_pages.add(page_number)
            if set(case["pages"]) != evidence_pages:
                raise ValueError(f"{case['id']}: pages must match the verified evidence pages")
        elif case.get("evidence") or case.get("pages"):
            raise ValueError(f"{case['id']}: unanswerable cases cannot declare supporting evidence")
    return cases


def chunks_for_pdf(
    path: Path,
    chunk_size: int,
    overlap: int,
    tokenizer: Any | None = None,
) -> list[dict]:
    pages = extract_pdf(path.read_bytes())
    chunks = split_text(pages, chunk_size, overlap, tokenizer=tokenizer)
    return [
        {
            "filename": path.name,
            "page": chunk["page"],
            "chunk_index": chunk["chunk_index"],
            "chunk_id": f"{path.name}:{chunk['chunk_index']}",
            "text": chunk["text"],
        }
        for chunk in chunks
    ]


def retrieve(
    encoder: Any,
    cases: list[dict],
    chunk_size: int,
    overlap: int,
) -> tuple[int, list[tuple[dict, list[dict]]]]:
    corpus = []
    for pdf in sorted(CORPUS_DIR.glob("*.pdf")):
        corpus.extend(
            chunks_for_pdf(
                pdf,
                chunk_size,
                overlap,
                tokenizer=encoder.tokenizer,
            )
        )
    if not corpus:
        raise ValueError(f"No PDF text found in {CORPUS_DIR}")

    passages = ["passage: " + chunk["text"] for chunk in corpus]
    passage_lengths = encoder.tokenizer(
        passages,
        add_special_tokens=True,
        truncation=False,
        max_length=1_500_000,
    )["input_ids"]
    if any(len(input_ids) > encoder.max_seq_length for input_ids in passage_lengths):
        raise ValueError(
            "A chunk exceeds the embedding model context length; "
            "reduce the chunk size before evaluating"
        )
    corpus_embeddings = encoder.encode(
        passages,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=64,
    )
    query_embeddings = encoder.encode(
        ["query: " + case["question"] for case in cases],
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )

    retrieved: list[tuple[dict, list[dict]]] = []
    for case, query_embedding in zip(cases, query_embeddings):
        scores = corpus_embeddings @ query_embedding
        indices = sorted(
            range(len(corpus)),
            key=lambda index: float(scores[index]),
            reverse=True,
        )[:TOP_K]
        top_chunks = [
            corpus[index] | {"score": float(scores[index])}
            for index in indices
        ]
        retrieved.append((case, top_chunks))
    return len(corpus), retrieved


def retrieval_metrics(retrieved: list[tuple[dict, list[dict]]]) -> dict:
    answerable_cases = [case for case, _ in retrieved if case["answerable"]]
    if not answerable_cases:
        raise ValueError("The evaluation set has no answerable cases")
    hits = 0
    relevant_page_retrievals = 0
    relevant_page_count = 0
    reciprocal_ranks = []

    for case, chunks in retrieved:
        if not case["answerable"]:
            continue
        relevant_pages = {
            (case["document"], page)
            for page in case["pages"]
        }
        retrieved_pages = {
            (chunk["filename"], chunk["page"])
            for chunk in chunks
        }
        matched_pages = relevant_pages & retrieved_pages
        relevant_page_count += len(relevant_pages)
        relevant_page_retrievals += len(matched_pages)
        if matched_pages:
            hits += 1
        rank = next(
            (
                index
                for index, chunk in enumerate(chunks, start=1)
                if (chunk["filename"], chunk["page"]) in relevant_pages
            ),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    return {
        "answerable_questions": len(answerable_cases),
        "relevant_pages": relevant_page_count,
        "hit_rate_at_5": hits / len(answerable_cases),
        "page_recall_at_5": relevant_page_retrievals / relevant_page_count,
        "mrr_at_5": sum(reciprocal_ranks) / len(answerable_cases),
    }


def answer_metrics(
    retrieved: list[tuple[dict, list[dict]]],
    threshold: float | None,
    generator: Generator,
) -> dict:
    answerable_count = sum(case["answerable"] for case, _ in retrieved)
    unanswerable_count = len(retrieved) - answerable_count
    answered_count = 0
    answerable_refusals = 0
    key_term_coverage = []
    valid_citation_count = 0
    relevant_page_citations = 0
    out_of_corpus_refusals = 0

    for case, ranked_chunks in retrieved:
        chunks = [
            chunk for chunk in ranked_chunks
            if threshold is None or chunk["score"] >= threshold
        ]
        chunks = [
            {
                **chunk,
                "chunk_id": chunk.get("chunk_id", f"retrieved-{index}"),
            }
            for index, chunk in enumerate(chunks, start=1)
        ]
        generated = generator.generate(case["question"], chunks)
        answer = generated.answer
        refused = not generated.answerable or normalize(answer) == normalize(REFUSAL_TEXT)
        if case["answerable"]:
            if refused:
                answerable_refusals += 1
            else:
                answered_count += 1
            answer_text = normalize(answer)
            terms = case["answer_key_terms"]
            key_term_coverage.append(
                sum(normalize(term) in answer_text for term in terms) / len(terms)
            )
            cited_chunks = {
                chunk["chunk_id"]: chunk
                for chunk in chunks
            }
            cited_ids = generated.cited_chunk_ids
            if cited_ids and all(chunk_id in cited_chunks for chunk_id in cited_ids):
                valid_citation_count += 1
                if any(
                    (
                        cited_chunks[chunk_id]["filename"],
                        cited_chunks[chunk_id]["page"],
                    )
                    in {(case["document"], page) for page in case["pages"]}
                    for chunk_id in cited_ids
                ):
                    relevant_page_citations += 1
        elif refused:
            out_of_corpus_refusals += 1

    answerable_response_rate = answered_count / answerable_count
    out_of_corpus_refusal_rate = (
        out_of_corpus_refusals / unanswerable_count if unanswerable_count else 0.0
    )
    return {
        "threshold": threshold,
        "answerable_response_rate": answerable_response_rate,
        "answerable_refusal_rate": answerable_refusals / answerable_count,
        "answer_key_term_coverage": sum(key_term_coverage) / answerable_count,
        "out_of_corpus_refusal_rate": out_of_corpus_refusal_rate,
        "balanced_abstention_accuracy": (
            answerable_response_rate + out_of_corpus_refusal_rate
        ) / 2,
        "valid_citation_rate": (
            valid_citation_count / answerable_count if answerable_count else 0.0
        ),
        "relevant_page_citation_rate": (
            relevant_page_citations / answerable_count if answerable_count else 0.0
        ),
    }


def render_table(rows: list[dict]) -> str:
    lines = [
        "| Minimum score | Answerable response | Key-term coverage | Out-of-corpus refusal | Balanced abstention | Valid citation refs | Relevant-page citations |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        threshold = "off" if row["threshold"] is None else f"{row['threshold']:.2f}"
        lines.append(
            f"| {threshold} | {row['answerable_response_rate']:.3f} "
            f"| {row['answer_key_term_coverage']:.3f} "
            f"| {row['out_of_corpus_refusal_rate']:.3f} "
            f"| {row['balanced_abstention_accuracy']:.3f} "
            f"| {row['valid_citation_rate']:.3f} "
            f"| {row['relevant_page_citation_rate']:.3f} |"
        )
    return "\n".join(lines)


def evaluate_configuration(
    encoder: Any,
    generator: Generator,
    cases: list[dict],
    chunk_size: int,
    overlap: int,
) -> tuple[dict, list[dict], list[tuple[dict, list[dict]]]]:
    chunk_count, retrieved = retrieve(encoder, cases, chunk_size, overlap)
    retrieval = retrieval_metrics(retrieved)
    sweep = [
        answer_metrics(retrieved, None, generator),
        *[
            answer_metrics(retrieved, threshold, generator)
            for threshold in THRESHOLDS
        ],
    ]
    return {
        "chunk_size": chunk_size,
        "overlap": overlap,
        "chunk_count": chunk_count,
        **retrieval,
    }, sweep, retrieved


def version_or_unknown(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not installed"


def failure_analysis(
    retrieved: list[tuple[dict, list[dict]]],
    generator: Generator,
    threshold: float,
) -> dict:
    misses = []
    answerable_refusals = []
    unanswerable_answers = []
    for case, chunks in retrieved:
        relevant = {
            (case["document"], page)
            for page in case.get("pages", [])
        }
        retrieved_pages = [
            (chunk["filename"], chunk["page"])
            for chunk in chunks
        ]
        if case["answerable"] and not relevant.intersection(retrieved_pages):
            misses.append({
                "id": case["id"],
                "expected": sorted(f"{filename}#page-{page}" for filename, page in relevant),
                "retrieved": [f"{filename}#page-{page}" for filename, page in retrieved_pages],
            })

        kept = [chunk for chunk in chunks if chunk["score"] >= threshold]
        kept = [
            {
                **chunk,
                "chunk_id": chunk.get("chunk_id", f"retrieved-{index}"),
            }
            for index, chunk in enumerate(kept, start=1)
        ]
        generated = generator.generate(case["question"], kept)
        if case["answerable"] and not generated.answerable:
            answerable_refusals.append(case["id"])
        if not case["answerable"] and generated.answerable:
            unanswerable_answers.append(case["id"])
    return {
        "retrieval_miss_ids": [item["id"] for item in misses],
        "retrieval_miss_examples": misses[:5],
        "answerable_refusal_ids_at_threshold": answerable_refusals,
        "unanswerable_answer_ids_at_threshold": unanswerable_answers,
    }


def main() -> None:
    from sentence_transformers import SentenceTransformer

    cases = load_and_validate_cases()
    encoder = SentenceTransformer("intfloat/e5-small-v2")
    generator = Generator(api_key=None, model="local-extractive")
    configurations = []
    for chunk_size, overlap in CHUNK_CONFIGURATIONS:
        metrics, sweep, retrieved = evaluate_configuration(
            encoder, generator, cases, chunk_size, overlap
        )
        configurations.append({
            "retrieval": metrics,
            "threshold_sweep": sweep,
            "retrieved_cases": retrieved,
        })

    answerable_count = sum(case["answerable"] for case in cases)
    unanswerable_count = len(cases) - answerable_count
    selected_threshold = 0.84
    failures = [
        failure_analysis(
            config["retrieved_cases"],
            generator,
            selected_threshold,
        )
        for config in configurations
    ]
    selected_answerable_response_rates = [
        next(
            row["answerable_response_rate"]
            for row in config["threshold_sweep"]
            if row["threshold"] == selected_threshold
        )
        for config in configurations
    ]
    results = {
        "run_date": date.today().isoformat(),
        "corpus": sorted(path.name for path in CORPUS_DIR.glob("*.pdf")),
        "gold_cases": len(cases),
        "answerable_cases": answerable_count,
        "unanswerable_cases": unanswerable_count,
        "embedding_model": "intfloat/e5-small-v2",
        "versions": {
            "sentence-transformers": version_or_unknown("sentence-transformers"),
            "transformers": version_or_unknown("transformers"),
            "torch": version_or_unknown("torch"),
        },
        "retrieval_top_k": TOP_K,
        "threshold_sweep": list(THRESHOLDS),
        "selected_threshold": selected_threshold,
        "configurations": [
            {
                "retrieval": config["retrieval"],
                "threshold_sweep": config["threshold_sweep"],
                "failures_at_selected_threshold": failure,
            }
            for config, failure in zip(configurations, failures)
        ],
        "evaluation_limitations": [
            "Reference labels and answer key terms have not been independently hand-graded.",
            "Answer key-term coverage is a lexical proxy, not correctness or faithfulness.",
            "No LLM judge, RAGAS, or Langfuse calls are made.",
        ],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "latest.json"
    csv_path = RESULTS_DIR / "latest.csv"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        fieldnames = [
            "chunk_size",
            "overlap",
            "threshold",
            "answerable_response_rate",
            "answerable_refusal_rate",
            "answer_key_term_coverage",
            "out_of_corpus_refusal_rate",
            "balanced_abstention_accuracy",
            "valid_citation_rate",
            "relevant_page_citation_rate",
        ]
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for config in configurations:
            metrics = config["retrieval"]
            for row in config["threshold_sweep"]:
                writer.writerow({
                    "chunk_size": metrics["chunk_size"],
                    "overlap": metrics["overlap"],
                    **row,
                })

    report = [
        "# Evaluation",
        "",
        f"Run date: {date.today().isoformat()}",
        "",
        "Generated with the local E5 embedding model and deterministic extractive "
        "generator. It makes no remote API calls.",
        "",
        f"- **Corpus:** {', '.join(results['corpus'])}.",
        f"- **Gold set:** {len(cases)} cases ({answerable_count} answerable, "
        f"{unanswerable_count} unanswerable); answerable evidence quotes are "
        "checked against their declared PDF pages by the runner.",
        "- **Embedding:** intfloat/e5-small-v2 (384 dimensions), E5 query/passage "
        "prefixes, normalized vectors, cosine similarity.",
        f"- **Versions:** sentence-transformers "
        f"{results['versions']['sentence-transformers']}, transformers "
        f"{results['versions']['transformers']}, torch {results['versions']['torch']}.",
        f"- **Retrieval:** top {TOP_K}; Hit@5 and MRR use answerable questions; "
        "Page Recall@5 uses the number of labeled source pages as its denominator.",
        "- **Reproduction:** `python eval/run_evaluation.py`; writes this report, "
        "`eval/results/latest.json`, and `eval/results/latest.csv`.",
        "",
        "## Gold-set validation",
        "",
        f"- {len(cases)} stable-ID cases: {answerable_count} answerable and "
        f"{unanswerable_count} out of corpus.",
        "- Every answerable case has an evidence quote verified against the "
        "declared page in the checked-in source PDFs.",
        "",
        "## Retrieval",
        "",
        "| Chunking | Chunks | Labeled relevant pages | Hit@5 | Page Recall@5 | MRR@5 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for config in configurations:
        metrics = config["retrieval"]
        report.append(
            f"| {metrics['chunk_size']}/{metrics['overlap']} "
            f"| {metrics['chunk_count']} | {metrics['relevant_pages']} "
            f"| {metrics['hit_rate_at_5']:.3f} "
            f"| {metrics['page_recall_at_5']:.3f} "
            f"| {metrics['mrr_at_5']:.3f} |"
        )
    report.extend([
        "",
        "Hit@5 is the fraction of answerable questions with at least one labeled "
        "source page in the top five. Page Recall@5 is the total distinct labeled "
        "source pages retrieved divided by all labeled relevant pages. MRR@5 uses "
        "the rank of the first retrieved chunk from a labeled page. The gold "
        "labels are script-validated but not yet independently hand-reviewed.",
        "",
        "## Local generated-answer and threshold evaluation",
        "",
        "Answer key-term coverage is a deterministic overlap proxy against "
        "case-specific required terms, not a correctness or faithfulness judge. "
        "Key-term coverage is a lexical overlap proxy against case-specific "
        "required terms. Citation validity checks that generated chunk ids belong "
        "to the retrieved set; relevant-page citations checks whether a cited "
        "chunk is on a labeled page. These are not answer correctness or "
        "faithfulness judgements. Refusal checks the extractor's explicit "
        "answerable flag and exact refusal text.",
        "",
        f"### {configurations[0]['retrieval']['chunk_size']}/"
        f"{configurations[0]['retrieval']['overlap']}",
        "",
        render_table(configurations[0]["threshold_sweep"]),
        "",
        f"### {configurations[1]['retrieval']['chunk_size']}/"
        f"{configurations[1]['retrieval']['overlap']}",
        "",
        render_table(configurations[1]["threshold_sweep"]),
        "",
        f"The runtime default is {selected_threshold:.2f}, selected from this "
        "diagnostic sweep. At this cutoff the answerable response rates are "
        f"{selected_answerable_response_rates[0]:.3f} "
        f"for {configurations[0]['retrieval']['chunk_size']}/"
        f"{configurations[0]['retrieval']['overlap']} and "
        f"{selected_answerable_response_rates[1]:.3f} "
        f"for {configurations[1]['retrieval']['chunk_size']}/"
        f"{configurations[1]['retrieval']['overlap']}. This is not a "
        "production-calibrated confidence score. Five "
        "negative examples are insufficient to establish a safe production "
        "cutoff; revalidate on a larger, independently reviewed set before "
        "deployment. Scores are specific to local E5 and must not be transferred "
        "to another provider.",
        "",
        "## Failure analysis",
        "",
    ])
    for config, failure in zip(configurations, failures):
        metrics = config["retrieval"]
        report.append(
            f"### {metrics['chunk_size']}/{metrics['overlap']} "
            f"(threshold {selected_threshold:.2f})"
        )
        report.append("")
        report.append(
            "Top-5 retrieval misses: "
            + (
                ", ".join(failure["retrieval_miss_ids"])
                if failure["retrieval_miss_ids"]
                else "none"
            )
            + "."
        )
        report.append(
            "Answerable refusals at threshold: "
            + (
                ", ".join(failure["answerable_refusal_ids_at_threshold"])
                if failure["answerable_refusal_ids_at_threshold"]
                else "none"
            )
            + "."
        )
        report.append(
            "Unanswerable cases answered at threshold: "
            + (
                ", ".join(failure["unanswerable_answer_ids_at_threshold"])
                if failure["unanswerable_answer_ids_at_threshold"]
                else "none"
            )
            + "."
        )
        for example in failure["retrieval_miss_examples"][:2]:
            report.append(
                f"- `{example['id']}` expected {', '.join(example['expected'])}; "
                f"top-5 pages were {', '.join(example['retrieved'])}."
            )
        report.append("")
    report.extend([
        "",
        "## Evaluation framework and limitations",
        "",
        "This is a deterministic, local evaluation harness rather than RAGAS or "
        "Langfuse. It was chosen to make retrieval, citation-id, and refusal "
        "checks reproducible without sending the corpus or questions to a third "
        "party or relying on unknown API quotas. It does not claim semantic "
        "correctness or faithfulness. An LLM judge was not enabled because its "
        "quota and reliability against human ratings have not been established; "
        "at least ten human-graded answers and agreement analysis are still "
        "required before reporting judge metrics.",
        "",
        f"Results are also saved as `{json_path.relative_to(ROOT)}` and "
        f"`{csv_path.relative_to(ROOT)}`. The local evaluation makes no provider "
        "calls, so it requires no call cache or quota-resume mechanism.",
        "",
        "## Limitations and next validation",
        "",
        "- The gold set is still 20 answerable and 5 out-of-corpus questions; it "
        "does not yet document independently verified reworded, multi-part, or "
        "cross-passage examples.",
        "- The user has not hand-reviewed reference answers or labels; this "
        "report is not submission-ready evidence of correctness.",
        "- No human answer grades, judge agreement, faithfulness metric, or "
        "Gemini answer-quality result is available.",
        "- DOCX ingestion is tested by generated test fixtures, not a user-provided "
        "real DOCX corpus.",
        "- Do not treat key-term coverage or embedding similarity as confidence.",
        "",
    ])
    OUTPUT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({
        "gold_cases": len(cases),
        "retrieval_results": [
            config["retrieval"]
            for config in configurations
        ],
        "results_json": str(json_path.relative_to(ROOT)),
        "results_csv": str(csv_path.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
