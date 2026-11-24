# Evaluation

Run date: 2026-11-24

Generated with the local E5 embedding model and deterministic extractive generator. This runner makes no Gemini, Cohere, Pinecone, or Neon calls.

## Gold-set validation

- 25 stable-ID cases: 20 answerable and 5 out of corpus.
- Every answerable case has an evidence quote verified against the declared page in the checked-in source PDFs.

## Retrieval

| Chunking | Chunks | Labeled relevant pages | Hit@5 | Page Recall@5 | MRR@5 |
|---|---:|---:|---:|---:|---:|
| 800/150 | 436 | 20 | 0.700 | 0.700 | 0.400 |
| 500/100 | 687 | 20 | 0.750 | 0.750 | 0.522 |

Hit@5 is the fraction of answerable questions with at least one labeled source page in the top five. Page Recall@5 is the total distinct labeled source pages retrieved divided by all labeled relevant pages. MRR@5 uses the rank of the first retrieved chunk from a labeled page. Evidence quotes are verified, but page relevance labels still require independent human review.

## Local generated-answer and threshold evaluation

Answer key-term coverage is a deterministic overlap proxy against case-specific required terms, not a correctness or faithfulness judge. Valid citation references only checks that bracketed indices point to a returned chunk; relevant-page citations checks whether a cited chunk is from a labeled page. Neither establishes that every answer claim is supported. The refusal metric checks the application's exact refusal text for the five out-of-corpus cases.

### 800/150

| Minimum score | Answerable response | Key-term coverage | Out-of-corpus refusal | Balanced abstention | Valid citation refs | Relevant-page citations |
|---:|---:|---:|---:|---:|---:|---:|
| off | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.30 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.35 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.40 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.45 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.50 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.55 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.60 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.65 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.70 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.75 | 1.000 | 0.591 | 0.000 | 0.500 | 1.000 | 0.600 |
| 0.80 | 1.000 | 0.591 | 0.600 | 0.800 | 1.000 | 0.600 |
| 0.82 | 1.000 | 0.591 | 0.800 | 0.900 | 1.000 | 0.600 |
| 0.84 | 1.000 | 0.591 | 1.000 | 1.000 | 1.000 | 0.600 |
| 0.86 | 0.800 | 0.420 | 1.000 | 0.900 | 0.800 | 0.450 |
| 0.88 | 0.500 | 0.280 | 1.000 | 0.750 | 0.500 | 0.300 |
| 0.90 | 0.200 | 0.150 | 1.000 | 0.600 | 0.200 | 0.000 |
| 0.92 | 0.050 | 0.050 | 1.000 | 0.525 | 0.050 | 0.000 |
| 0.94 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |
| 0.96 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |

### 500/100

| Minimum score | Answerable response | Key-term coverage | Out-of-corpus refusal | Balanced abstention | Valid citation refs | Relevant-page citations |
|---:|---:|---:|---:|---:|---:|---:|
| off | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.30 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.35 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.40 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.45 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.50 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.55 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.60 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.65 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.70 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.75 | 1.000 | 0.584 | 0.000 | 0.500 | 1.000 | 0.750 |
| 0.80 | 1.000 | 0.584 | 0.400 | 0.700 | 1.000 | 0.750 |
| 0.82 | 1.000 | 0.584 | 0.800 | 0.900 | 1.000 | 0.750 |
| 0.84 | 1.000 | 0.572 | 1.000 | 1.000 | 1.000 | 0.700 |
| 0.86 | 0.900 | 0.530 | 1.000 | 0.950 | 0.900 | 0.650 |
| 0.88 | 0.500 | 0.291 | 1.000 | 0.750 | 0.500 | 0.400 |
| 0.90 | 0.300 | 0.179 | 1.000 | 0.650 | 0.300 | 0.050 |
| 0.92 | 0.050 | 0.050 | 1.000 | 0.525 | 0.050 | 0.000 |
| 0.94 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |
| 0.96 | 0.000 | 0.000 | 1.000 | 0.500 | 0.000 | 0.000 |

The threshold sweep is diagnostic and the runtime threshold remains unset by default. Five negative examples are insufficient to establish a production cutoff; use a larger, independently reviewed set before enabling one. Scores are calibrated for local E5 and should not be assumed transferable to another embedding provider.

## Limitations and next validation

- This is not a human-graded answer-quality or faithfulness evaluation.
- The gold set is small and evidence-page labels have not received independent double annotation.
- The local extractive generator is measured; Gemini generation is not called or evaluated.
- Pinecone/Neon integration and deployed-service behavior are outside this offline evaluation.
- Review errors and expand the corpus/query set before treating these metrics as general performance estimates.
