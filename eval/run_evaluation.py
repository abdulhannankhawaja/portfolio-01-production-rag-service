import json
import re
import sys
from datetime import date
from pathlib import Path

import pymupdf
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.generation import Generator
from app.ingestion import clean_text, extract_pdf, split_text


CORPUS_DIR = ROOT / "corpus"
GOLDEN_PATH = ROOT / "eval" / "golden.json"
OUTPUT_PATH = ROOT / "EVAL.md"
REFUSAL_TEXT = "The documents do not contain enough information to answer this question."
TOP_K = 5
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


def chunks_for_pdf(path: Path, chunk_size: int, overlap: int) -> list[dict]:
    pages = extract_pdf(path.read_bytes())
    chunks = split_text(pages, chunk_size, overlap)
    return [
        {
            "filename": path.name,
            "page": chunk["page"],
            "chunk_index": chunk["chunk_index"],
            "text": chunk["text"],
        }
        for chunk in chunks
    ]


def retrieve(
    encoder: SentenceTransformer,
    cases: list[dict],
    chunk_size: int,
    overlap: int,
) -> tuple[int, list[tuple[dict, list[dict]]]]:
    corpus = []
    for pdf in sorted(CORPUS_DIR.glob("*.pdf")):
        corpus.extend(chunks_for_pdf(pdf, chunk_size, overlap))
    if not corpus:
        raise ValueError(f"No PDF text found in {CORPUS_DIR}")

    corpus_embeddings = encoder.encode(
        ["passage: " + chunk["text"] for chunk in corpus],
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


def citation_indices(answer: str) -> list[int]:
    return [int(value) for value in re.findall(r"\[(\d+)\]", answer)]


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
        answer, _ = generator.generate(case["question"], chunks)
        refused = normalize(answer) == normalize(REFUSAL_TEXT)
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
            indices = citation_indices(answer)
            if indices and all(1 <= index <= len(chunks) for index in indices):
                valid_citation_count += 1
                if any(
                    (chunks[index - 1]["filename"], chunks[index - 1]["page"])
                    in {(case["document"], page) for page in case["pages"]}
                    for index in indices
                ):
                    relevant_page_citations += 1
        elif refused:
            out_of_corpus_refusals += 1

    answerable_response_rate = (
        (answerable_count - answerable_refusals) / answerable_count
    )
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
    encoder: SentenceTransformer,
    generator: Generator,
    cases: list[dict],
    chunk_size: int,
    overlap: int,
) -> tuple[dict, list[dict]]:
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
    }, sweep


def main() -> None:
    cases = load_and_validate_cases()
    encoder = SentenceTransformer("intfloat/e5-small-v2")
    generator = Generator(api_key=None, model="local-extractive")
    configurations = []
    for chunk_size, overlap in ((800, 150), (500, 100)):
        metrics, sweep = evaluate_configuration(
            encoder, generator, cases, chunk_size, overlap
        )
        configurations.append((metrics, sweep))

    answerable_count = sum(case["answerable"] for case in cases)
    unanswerable_count = len(cases) - answerable_count
    report = [
        "# Evaluation",
        "",
        f"Run date: {date.today().isoformat()}",
        "",
        "Generated with the local E5 embedding model and deterministic extractive "
        "generator. This runner makes no Gemini, Cohere, Pinecone, or Neon calls.",
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
    for metrics, _ in configurations:
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
        "the rank of the first retrieved chunk from a labeled page. Evidence "
        "quotes are verified, but page relevance labels still require independent "
        "human review.",
        "",
        "## Local generated-answer and threshold evaluation",
        "",
        "Answer key-term coverage is a deterministic overlap proxy against "
        "case-specific required terms, not a correctness or faithfulness judge. "
        "Valid citation references only checks that bracketed indices point to a "
        "returned chunk; relevant-page citations checks whether a cited chunk is "
        "from a labeled page. Neither establishes that every answer claim is "
        "supported. The refusal metric checks the application's exact refusal "
        "text for the five out-of-corpus cases.",
        "",
        "### 800/150",
        "",
        render_table(configurations[0][1]),
        "",
        "### 500/100",
        "",
        render_table(configurations[1][1]),
        "",
        "The threshold sweep is diagnostic and the runtime threshold remains "
        "unset by default. Five negative examples are insufficient to establish "
        "a production cutoff; use a larger, independently reviewed set before "
        "enabling one. Scores are calibrated for local E5 and should not be "
        "assumed transferable to another embedding provider.",
        "",
        "## Limitations and next validation",
        "",
        "- This is not a human-graded answer-quality or faithfulness evaluation.",
        "- The gold set is small and evidence-page labels have not received "
        "independent double annotation.",
        "- The local extractive generator is measured; Gemini generation is not "
        "called or evaluated.",
        "- Pinecone/Neon integration and deployed-service behavior are outside "
        "this offline evaluation.",
        "- Review errors and expand the corpus/query set before treating these "
        "metrics as general performance estimates.",
        "",
    ])
    OUTPUT_PATH.write_text("\n".join(report), encoding="utf-8")
    summary = {
        "gold_cases": len(cases),
        "configurations": [
            {"retrieval": metrics, "threshold_sweep": sweep}
            for metrics, sweep in configurations
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
