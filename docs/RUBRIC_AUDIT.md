# Rubric and Project-Prompt Audit

**Audit date:** 2026-11-25

**Evidence basis:** current repository, 75 passing automated tests, the
executed `notebooks/pipeline.ipynb`, and the local evaluation run in
[EVAL.md](./EVAL.md). Answer-side evaluation and saved notebook output predate
the latest extractive-generator refinement and need refresh.

Status definitions: **Verified** means implementation and available execution
evidence support the requirement; **Partially verified** means meaningful work
exists but required evidence or scope is incomplete; **Not implemented** means
the feature is absent; **Not verified** means evidence is unavailable.

## Mandatory rubric items

| Item | Marks | Status | Evidence and remaining gap |
|---|---:|---|---|
| M1 Structure | 6 | Partially verified | `app/`, `frontend/`, `tests/`, `eval/`, `docs/`, and `notebooks/` separate core concerns. The backend uses focused modules such as `app/ingestion.py`; it does not use the requested `app/ingestion/` package or `evals/` name. |
| M2 Frontend | 8 | Partially verified | React/Vite UI supports account creation, sign-in, document upload/list/delete, questions, citations, retrieved chunks, and observability. Screenshot captures are supplied; a demo-video walkthrough is not. |
| M3 DESIGN.md | 9 | Verified | [DESIGN.md](./DESIGN.md) documents component choices, trade-offs, data flows, grounding, score semantics, API, tests, and limitations. |
| M4 API design | 4 | Verified | FastAPI routes and schemas are implemented; [tests/test_app.py](../tests/test_app.py) covers API behaviors, validation, and response fields. |
| M5 Ingestion | 8 | Partially verified | PDF, DOCX, TXT, MD, and PPTX extraction, validation, token-aware chunking, metadata, deduplication, lifecycle, and deletion are implemented and tested. The evaluation corpus contains PDFs only; no user-supplied DOCX has been evaluated. |
| M6 Grounded answers | 8 | Partially verified | API tests cover citation validation, refusal, and retrieved-chunk responses. The saved notebook output and answer-side evaluation predate the latest local extractor change; optional Gemini quality has not been measured. |
| M7 Golden set and results | 12 | Partially verified | 25 cases and real retrieval/threshold results are in [eval/golden.json](../eval/golden.json) and [EVAL.md](./EVAL.md). Labels/reference terms have not been independently user-reviewed; broader question types and human answer grading are missing. |
| M8 Evaluation frameworks and reproducibility | 8 | Partially verified | One command reproduces deterministic JSON/CSV results and compares two context-safe chunk sizes, changing only chunk size. RAGAS/Langfuse or a validated LLM judge, judge-human agreement, and quota-resume caching are absent. |
| M9 Guardrails | 6 | Partially verified | Input checks, prompt-injection/jailbreak patterns, untrusted-document prompting, document validation, secret-output checks, grounding, and citation checks exist. Pattern matching is limited; malicious-file scanning and video evidence are absent. |
| M10 Errors and status codes | 4 | Verified | Routes map validation, unsupported uploads, duplicates, size limits, provider failures, and rate limits to explicit HTTP responses; focused API tests exercise representative cases. |
| M11 Testing | 6 | Partially verified | Full suite: **75 passed**. Includes local Chroma/SQLite round trips and cleanup plus API, generation, ingestion, Unicode/table, timeout/rate-limit, contradiction, and concurrent storage tests. Not every provider/outage and adversarial scenario is covered. |
| M12 Code quality | 6 | Partially verified | Settings, service layer, type annotations, pinned dependencies, and bounded timeouts/retries are present. No dedicated type-check/linter run or broader deployment-quality review is recorded. |
| M13 Git | 4 | Partially verified | This accumulated update is being prepared on a fresh `feat/rag-service-improvements` branch from `origin/main`, with a PR for review. The previous feedback's event/registration feature names refer to a different project and are not present here. For future work, keep each independently reviewable feature on its own branch/PR rather than retroactively rewriting merged history. |
| M14 README, requirements, screenshots, AI docs | 3 | Partially verified | Step-by-step README, pinned `requirements.txt`, [AI_USAGE.md](./AI_USAGE.md), and a screenshot gallery exist. The complete chat export must still be supplied by the user, and screenshots should be checked against the current app before submission. |
| M15 Demo video | 8 | Not verified | No demo video is present. |

**Verified mandatory score only: 17 / 100** (M3 + M4 + M10). Partial or
unverified items receive no marks in this conservative total.

## Bonus items

| Item | Marks | Status | Evidence and remaining gap |
|---|---:|---|---|
| B1 JWT | 5 | Partially verified | Signup/login, Argon2id hashes, signed expiring JWTs, and owner-filtered document APIs are implemented and tested. Deployment hardening and broader security review remain. |
| B2 Multilingual | 4 | Partially verified | Unicode extraction and local lexical matching have a Japanese question/answer test. The default E5 retrieval model is English-oriented; there is no multilingual retrieval model or evaluation set. |
| B3 Monitoring | 4 | Partially verified | Local metrics dashboard, request IDs, spans, latency, errors, token/cost fields, and traces are implemented and tested. It is local telemetry, not a deployed monitoring stack. |
| B4 Modern frontend | 3 | Partially verified | React/Vite frontend is implemented and builds/lints; deployment evidence is absent. |
| B5 Extra file types | 2 | Verified | TXT, Markdown, and PPTX are supported in addition to PDF/DOCX, with upload/parser tests. |
| B6 Document guardrails | 3 | Partially verified | Supported file formats receive structural, integrity, encoding, and size checks; malformed/encrypted cases are rejected. There is no antivirus/general malware scanner or comprehensive malicious-file campaign. |
| B7 Edge cases | 4 | Partially verified | Tests cover duplicates, malformed/encrypted/scanned uploads, empty index, deletion, rate limits, Unicode/tables, contradictions, and concurrent storage operations. Real provider outage demonstration and the demo video remain. See [EDGE_CASES.md](./EDGE_CASES.md). |
| B8 Deployment | 3 | Not implemented | No deployed service or verified host persistence/configuration. |

**Verified bonus score: 2 / 28.**

## Submission gate and critical work

**M7 is not verified to submission standard. The project is NOT safe to submit
as final evidence yet.** The evaluation run is real and reproducible, but the
user must review the corpus/questions/references, provide a real DOCX source,
and hand-grade answers. The current two-PDF set is small; its retrieval Hit@5
is 60% for 400/100 and 65% for 500/100. Those are retrieval metrics, not answer
accuracy. See [ACCURACY_REPORT.md](./ACCURACY_REPORT.md).

Remaining work, in priority order:

1. User supplies and reviews the legally usable PDF + DOCX corpus, gold
   questions, answer references, and page/section labels.
2. Expand the question set with the required reworded, multi-part,
   cross-passage, and negative cases; hand-grade at least ten answers.
3. If an LLM judge is used, validate it against human grades and report
   disagreement; otherwise document the evidence-based reason for omitting it.
4. Verify the supplied screenshot captures against the current build and record
   the required demo video; do not fabricate submission evidence.
5. Review and merge the new feature PR. Keep future changes in smaller
   feature-specific PRs and retain the original exported AI chat history as a
   separate submission artifact.

No score is awarded for work that still depends on user review or absent
submission artifacts. See [PROGRESS.md](./PROGRESS.md) for the current state.
