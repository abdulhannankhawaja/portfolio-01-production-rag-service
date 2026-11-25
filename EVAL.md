# Evaluation

Run date: 2026-11-24

> The saved answer/threshold metrics below were generated before the local
> extractive generator was tightened to abstain when no retrieved sentence
> matches the question and to prefer the strongest-overlap sentences. Retrieval
> metrics are unaffected, but answer-side results are stale and must be
> regenerated before submission.

Generated with the local E5 embedding model and deterministic extractive generator. It makes no remote API calls.

- **Corpus:** NIST_AI_RMF_1.0.pdf, NIST_Generative_AI_Profile.pdf.
- **Gold set:** 25 cases (20 answerable, 5 unanswerable); answerable evidence quotes are checked against their declared PDF pages by the runner.
- **Embedding:** intfloat/e5-small-v2 (384 dimensions), E5 query/passage prefixes, normalized vectors, cosine similarity.
- **Versions:** sentence-transformers 5.7.0, transformers 5.24.0, torch 2.15.0.
- **Retrieval:** top 5; Hit@5 and MRR use answerable questions; Page Recall@5 uses the number of labeled source pages as its denominator.
- **Reproduction:** `python eval/run_evaluation.py`; writes this report, `eval/results/latest.json`, and `eval/results/latest.csv`.

## Gold-set validation

- 25 stable-ID cases: 20 answerable and 5 out of corpus.
- Every answerable case has an evidence quote verified against the declared page in the checked-in source PDFs.

## Retrieval

| Chunking | Chunks | Labeled relevant pages | Hit@5 | Page Recall@5 | MRR@5 |
|---|---:|---:|---:|---:|---:|
| 400/100 | 776 | 20 | 0.600 | 0.600 | 0.442 |
| 500/100 | 359 | 20 | 0.650 | 0.650 | 0.493 |

Hit@5 is the fraction of answerable questions with at least one labeled source page in the top five. Page Recall@5 is the total distinct labeled source pages retrieved divided by all labeled relevant pages. MRR@5 uses the rank of the first retrieved chunk from a labeled page. The gold labels are script-validated but not yet independently hand-reviewed.

## Local generated-answer and threshold evaluation

Answer key-term coverage is a deterministic overlap proxy against case-specific required terms, not a correctness or faithfulness judge. Key-term coverage is a lexical overlap proxy against case-specific required terms. Citation validity checks that generated chunk ids belong to the retrieved set; relevant-page citations checks whether a cited chunk is on a labeled page. These are not answer correctness or faithfulness judgements. Refusal checks the extractor's explicit answerable flag and exact refusal text.

### 400/100

| Minimum score | Answerable response | Key-term coverage | Out-of-corpus refusal | Balanced abstention | Valid citation refs | Relevant-page citations |
|---:|---:|---:|---:|---:|---:|---:|
| off | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.30 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.35 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.40 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.45 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.50 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.55 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.60 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.65 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.70 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.75 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.80 | 1.000 | 0.597 | 0.000 | 0.500 | 1.000 | 0.550 |
| 0.82 | 1.000 | 0.597 | 0.400 | 0.700 | 1.000 | 0.550 |
| 0.84 | 1.000 | 0.560 | 0.800 | 0.900 | 1.000 | 0.500 |
| 0.86 | 0.750 | 0.358 | 1.000 | 0.875 | 0.750 | 0.350 |
| 0.88 | 0.550 | 0.268 | 1.000 | 0.775 | 0.550 | 0.250 |
| 0.90 | 0.150 | 0.100 | 1.000 | 0.575 | 0.150 | 0.000 |
| 0.92 | 0.050 | 0.050 | 1.000 | 0.525 | 0.050 | 0.000 |
| 0.94 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |
| 0.96 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |

### 500/100

| Minimum score | Answerable response | Key-term coverage | Out-of-corpus refusal | Balanced abstention | Valid citation refs | Relevant-page citations |
|---:|---:|---:|---:|---:|---:|---:|
| off | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.30 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.35 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.40 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.45 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.50 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.55 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.60 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.65 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.70 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.75 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.80 | 1.000 | 0.610 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.82 | 1.000 | 0.610 | 0.400 | 0.700 | 1.000 | 0.600 |
| 0.84 | 0.900 | 0.460 | 0.600 | 0.750 | 0.900 | 0.500 |
| 0.86 | 0.700 | 0.370 | 1.000 | 0.850 | 0.700 | 0.350 |
| 0.88 | 0.450 | 0.255 | 1.000 | 0.725 | 0.450 | 0.200 |
| 0.90 | 0.100 | 0.100 | 1.000 | 0.550 | 0.100 | 0.000 |
| 0.92 | 0.050 | 0.050 | 1.000 | 0.525 | 0.050 | 0.000 |
| 0.94 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |
| 0.96 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |

The runtime default is 0.84, selected from this diagnostic sweep. At this cutoff the answerable response rates are 1.000 for 400/100 and 0.900 for 500/100. This is not a production-calibrated confidence score. Five negative examples are insufficient to establish a safe production cutoff; revalidate on a larger, independently reviewed set before deployment. Scores are specific to local E5 and must not be transferred to another provider.

## Failure analysis

### 400/100 (threshold 0.84)

Top-5 retrieval misses: rmf-manage, rmf-trustworthy-characteristics, rmf-function-order, rmf-risk-response, genai-data-privacy, genai-information-integrity, genai-harmful-bias, genai-human-ai.
Answerable refusals at threshold: none.
Unanswerable cases answered at threshold: out-of-corpus-cake.
- `rmf-manage` expected NIST_AI_RMF_1.0.pdf#page-37; top-5 pages were NIST_AI_RMF_1.0.pdf#page-25, NIST_AI_RMF_1.0.pdf#page-38, NIST_AI_RMF_1.0.pdf#page-44, NIST_AI_RMF_1.0.pdf#page-46, NIST_AI_RMF_1.0.pdf#page-26.
- `rmf-trustworthy-characteristics` expected NIST_AI_RMF_1.0.pdf#page-8; top-5 pages were NIST_AI_RMF_1.0.pdf#page-47, NIST_Generative_AI_Profile.pdf#page-16, NIST_AI_RMF_1.0.pdf#page-17, NIST_AI_RMF_1.0.pdf#page-44, NIST_AI_RMF_1.0.pdf#page-7.

### 500/100 (threshold 0.84)

Top-5 retrieval misses: rmf-manage, rmf-trustworthy-characteristics, rmf-function-order, rmf-risk-response, genai-data-privacy, genai-harmful-bias, genai-human-ai.
Answerable refusals at threshold: rmf-measure, genai-transparency.
Unanswerable cases answered at threshold: out-of-corpus-cake, out-of-corpus-private-key.
- `rmf-manage` expected NIST_AI_RMF_1.0.pdf#page-37; top-5 pages were NIST_AI_RMF_1.0.pdf#page-25, NIST_AI_RMF_1.0.pdf#page-46, NIST_AI_RMF_1.0.pdf#page-38, NIST_AI_RMF_1.0.pdf#page-26, NIST_AI_RMF_1.0.pdf#page-30.
- `rmf-trustworthy-characteristics` expected NIST_AI_RMF_1.0.pdf#page-8; top-5 pages were NIST_AI_RMF_1.0.pdf#page-47, NIST_AI_RMF_1.0.pdf#page-7, NIST_AI_RMF_1.0.pdf#page-9, NIST_AI_RMF_1.0.pdf#page-17, NIST_AI_RMF_1.0.pdf#page-25.


## Evaluation framework and limitations

This is a deterministic, local evaluation harness rather than RAGAS or Langfuse. It was chosen to make retrieval, citation-id, and refusal checks reproducible without sending the corpus or questions to a third party or relying on unknown API quotas. It does not claim semantic correctness or faithfulness. An LLM judge was not enabled because its quota and reliability against human ratings have not been established; at least ten human-graded answers and agreement analysis are still required before reporting judge metrics.

Results are also saved as `eval/results/latest.json` and `eval/results/latest.csv`. The local evaluation makes no provider calls, so it requires no call cache or quota-resume mechanism.

## Limitations and next validation

- The gold set is still 20 answerable and 5 out-of-corpus questions; it does not yet document independently verified reworded, multi-part, or cross-passage examples.
- The user has not hand-reviewed reference answers or labels; this report is not submission-ready evidence of correctness.
- No human answer grades, judge agreement, faithfulness metric, or Gemini answer-quality result is available.
- DOCX ingestion is tested by generated test fixtures, not a user-provided real DOCX corpus.
- Do not treat key-term coverage or embedding similarity as confidence.
