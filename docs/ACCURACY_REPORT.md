# Accuracy and Verification Report

**Run date:** 2026-11-24
**Project:** Production RAG Service
**Evaluation command:** `python eval/run_evaluation.py`
**Test command:** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_app.py tests/test_evaluation.py tests/test_generation.py tests/test_storage.py tests/test_ingestion.py`

> Retrieval results below remain valid for the current code. Answer/threshold
> results are from immediately before the local extractor was changed to abstain
> when no retrieved sentence matches and to prefer the strongest-overlap
> sentences. Those answer-side values are stale and require a fresh evaluation.

## Executive summary

This evaluation does **not** establish end-to-end answer accuracy. It measures
retrieval against a small source-page-labeled set and runs a deterministic
extractive baseline for lexical coverage, citation, and refusal proxies. It does
not judge semantic correctness or faithfulness.

The latest evaluation contains 25 cases (20 answerable and 5 out of corpus)
from two checked-in NIST PDFs. At top 5, source-page Hit@5 is **60% (12/20)**
with 400/100 token chunking and **65% (13/20)** with 500/100. These are
retrieval results, not answer-accuracy percentages.

## Evaluation setup

- **Corpus:** `NIST_AI_RMF_1.0.pdf` and `NIST_Generative_AI_Profile.pdf`.
- **Embedding:** `intfloat/e5-small-v2`, normalized 384-dimensional vectors
  with E5 query/passage prefixes.
- **Question set:** `eval/golden.json`, 25 cases (20 answerable and 5
  unanswerable). Evidence quotes are checked against the declared PDF page by
  the runner; labels and reference terms have not been independently reviewed.
- **Configurations:** 400 tokens / 100 overlap and 500 tokens / 100 overlap.
  Chunk size is the only changed variable. Both settings fit the E5 model
  context; the evaluation rejects passages that exceed it.
- **Retrieval cutoff:** top 5.
- **Reproduction:** `python eval/run_evaluation.py` from the repository root.

## Retrieval results

| Metric | 400 / 100 | 500 / 100 |
|---|---:|---:|
| Chunk count | 776 | 359 |
| Top-5 source-page Hit@5 | 60.0% (12/20) | 65.0% (13/20) |
| Page Recall@5 | 60.0% | 65.0% |
| MRR@5 | 0.442 | 0.493 |

Hit@5 is the fraction of answerable questions with at least one labeled
document/page in the top five. Page Recall@5 is the number of distinct labeled
source pages retrieved divided by the total labeled relevant source pages (20).
MRR@5 is the mean reciprocal rank of the first matching page, with misses
scored zero. Gold labels are script-validated but not hand-reviewed; the small
set does not establish a general winner.

## Local answer and threshold diagnostics

With the threshold disabled, local extractive key-term coverage is 0.597 for
400/100 and 0.610 for 500/100. Relevant-page citation rates are 0.550 and
0.600 respectively. These deterministic proxies do not establish that an answer
is correct or supported.

At the configured 0.84 minimum similarity, in the previous local-extractor run:

| Metric | 400 / 100 | 500 / 100 |
|---|---:|---:|
| Answerable response rate | 100.0% (20/20) | 90.0% (18/20) |
| Out-of-corpus refusal rate | 80.0% (4/5) | 60.0% (3/5) |
| Balanced abstention proxy | 0.900 | 0.750 |
| Valid citation reference rate | 100.0% | 90.0% |
| Relevant-page citation rate | 50.0% | 50.0% |

The 0.84 threshold is diagnostic, not a calibrated confidence score. It rejects
some answerable questions and still answers some out-of-corpus questions. Five
negative examples are insufficient to establish a safe production cutoff.
Full threshold sweeps and failure examples are recorded in [EVAL.md](./EVAL.md)
and `eval/results/latest.json`.

## Automated tests

The most recent full test run reported **75 passed**. It covers API behavior,
upload validation, local Chroma/SQLite lifecycle, fixed-vector round trips,
similarity conversion, retrieval/generation validation, rate limiting, and
ingestion edge cases. The offline evaluation is separate from tests and makes
no external provider calls.

The API tests use deterministic fakes for several provider-dependent behaviors.
The notebook executes the actual local service pipeline on the checked-in PDF
corpus, but neither the tests nor notebook provide a user-supplied DOCX corpus
or human validation of generated answers.

## Limitations and next validation

- The source corpus contains two PDF documents; a user-provided, hand-reviewed
  DOCX corpus and answer labels are still needed.
- The gold set has 20 answerable and 5 out-of-corpus cases. The user has not
  independently reviewed its questions, references, or relevance labels.
- No human answer grades, faithfulness scores, validated LLM judge, or
  judge-versus-human agreement are available.
- The local baseline is not Gemini answer-quality evaluation. Provider
  availability, cost, terms, and quotas must be checked before live use.
- Screenshot captures are supplied in the [gallery](./screenshots/README.md),
  but should be checked against the current build. A demo video and deployment
  evidence are absent.

Do not present the numbers above as answer accuracy or claim that this project
is submission-ready until these evidence gaps are addressed.
