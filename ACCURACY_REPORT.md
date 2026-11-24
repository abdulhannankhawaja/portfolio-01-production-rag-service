# Accuracy and Verification Report

**Run date:** 2026-11-24
**Project:** Production RAG Service
**Evaluation command:** `python eval/run_evaluation.py`
**Test command:** `pytest -q`

## Executive summary

The current evaluation does **not** measure end-to-end answer accuracy. It
measures retrieval against a small source-page-labeled question set, lexical
overlap between retrieved context and reference answers, and a low-score
refusal proxy. No generated answers were scored for correctness or faithfulness.
Therefore, a single answer-accuracy percentage cannot be reported honestly.

The strongest directly interpretable retrieval result is **top-5 source-page
Hit@5: 70% (14/20)** with 800/150 chunking, and **75% (15/20)** with
500/100 chunking. These values are low enough that they should not be presented
as answer accuracy.

The current test suite passes **23 tests**. Those tests primarily use an
in-memory document store and mocked generation; they verify API behaviors, not
real-provider answer quality or a live upload-to-answer round trip.

## Evaluation setup

- **Corpus:** `NIST_AI_RMF_1.0.pdf` and `NIST_Generative_AI_Profile.pdf`.
- **Embedding:** `intfloat/e5-small-v2`, with E5 `passage:` and `query:` prefixes.
- **Question set:** `eval/golden.json`, 25 questions: 20 answerable and 5
  unanswerable.
- **Configurations:** 800 characters / 150 overlap and 500 characters / 100
  overlap. Chunking is the only changed variable.
- **Retrieval cutoff:** top 5.
- **Compared pages:** for each answerable item, a hit means at least one of the
  top five chunks came from the expected document and one of the listed pages.
- **Reproduction:** run `python eval/run_evaluation.py` from the repository root.

## Retrieval results

| Metric | 800 / 150 | 500 / 100 |
|---|---:|---:|
| Chunk count | 436 | 687 |
| Top-5 source-page Hit@5 | 70.0% (14/20) | 75.0% (15/20) |
| Page Recall@5 | 70.0% | 75.0% |
| MRR@5 | 0.400 | 0.522 |
| Local answer key-term coverage | 59.1% | 58.4% |
| Relevant-page citation rate | 60.0% | 75.0% |
| Unanswerable refusal without a threshold | 0% (0/5) | 0% (0/5) |

Page Recall@5 is the fraction of distinct labeled relevant pages found across
the top five retrieved chunks. It does not count all relevant chunks and should
not be treated as conventional recall over independently judged documents.

`MRR@5` is the mean reciprocal rank of the first top-five chunk matching the
expected document and any expected page; misses contribute zero. Key-term coverage is a deterministic lexical proxy against case-specific terms.
It does not evaluate semantic support, answer correctness, or faithfulness.
The 500/100 configuration performs better on Hit@5, Page Recall@5, MRR@5, and
relevant-page citations. Its key-term coverage is slightly lower. The small gold
set does not establish a robust general winner.

## Answer quality and abstention

**Answer correctness, faithfulness, and Gemini answer quality were not
measured.** The offline runner now scores the deterministic local extractor,
valid citation indices, relevant-page citations, and exact refusal text, but it
does not call Gemini or perform human grading.

The threshold sweep is diagnostic. With no threshold, the local generator
answers every answerable and out-of-corpus case, so out-of-corpus refusal is
0/5. Higher thresholds increase refusal, but a threshold of 0.84 also begins to
remove answerable evidence in both configurations. The runtime threshold
remains unset; five negative examples are not enough to calibrate production
abstention.

The golden set also lacks independently reviewed document/page-level relevance
labels and broader negative examples. The current report does not include
human-graded answers, a structured LLM
judge, judge-versus-human agreement, or threshold calibration.

## Automated test results

Latest run: **23 passed**.

The tests cover health and frontend responses, PDF and DOCX uploads, duplicate
rejection, unsupported and malformed documents, scanned/empty files, upload
size limits, document listing/detail/deletion, empty retrieval refusal,
mocked answer/citation behavior, mocked generation failure, request validation,
and Cohere query embedding configuration.

These are API/unit-level checks. The store is replaced with an in-memory fake in
document API tests; the answer-generation tests use a mocked generator. The
suite does not establish live Pinecone/Neon integration, real Gemini quality,
or an automated upload → retrieve → generate → delete end-to-end result.

## Overall assessment and next steps

- **Functional tests:** pass (23/23).
- **Top-5 retrieval source-page Hit@5:** 70–75% on 20 answerable cases.
- **Answer accuracy:** not measured; no defensible percentage available.
- **Out-of-corpus refusal:** 0/5 without a threshold; threshold-dependent in the diagnostic sweep.
- **Evaluation confidence:** limited by the small dataset and incomplete labels.

Before describing the system as accurate or submission-ready, expand and verify
the gold set, report page/source retrieval metrics with correct definitions,
add a similarity-threshold sweep, evaluate actual generated answers for
correctness/faithfulness/citation validity/refusal, hand-grade a sample, and
run a real end-to-end integration test. Report failures as well as successes.
