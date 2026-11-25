# Progress

- **Current phase:** documentation and project onboarding improvements; the
  local service and React frontend are implemented.
- **Verified:** the latest full test run reported 75 passing tests. The
  frontend production build and Oxlint passed. The local notebook and offline
  evaluation use the two checked-in NIST PDFs.
- **Verified design:** FastAPI, PDF/DOCX/TXT/MD/PPTX ingestion, token-aware
  chunking, Chroma with a SQLite lifecycle registry, local E5 embeddings,
  extractive default answers, optional Gemini/Cohere, account-scoped documents,
  citation checks, a React UI, and local observability.
- **Edge cases:** empty/scanned and malformed files, duplicate and concurrent
  uploads, long-document limits, empty-corpus/unanswerable questions,
  deletion, contradictions, Unicode/tables, provider failures, and concurrent
  query paths have focused tests. See [EDGE_CASES.md](./EDGE_CASES.md) for
  exact coverage and a demo-video checklist.
- **Known gaps:** evaluation corpus remains PDF-only and labels are not
  independently reviewed; there is no user-provided real DOCX evaluation
  document, human answer grades, validated judge/agreement, complete AI chat
  export, demo video, or deployment evidence. [AI_USAGE.md](./AI_USAGE.md)
  documents representative prompt objectives but is not a transcript.
  Screenshots are present in the
  [gallery](./screenshots/README.md), but should be checked against the current
  build before being used as feature evidence. The local extractor was
  tightened after the last answer-metric run, so answer/threshold results need
  regeneration. The 0.84 cutoff is not production-calibrated.
- **Next:** refresh evaluation after behavior changes; complete user review and
  any required demo/deployment evidence before making submission claims.
