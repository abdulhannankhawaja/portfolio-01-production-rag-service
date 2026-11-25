# Progress

- **Current phase:** final verification and evidence audit; core local service is implemented.
- **Verified:** focused API/storage/generation/ingestion tests passed (48 tests); the local notebook executed the service pipeline on the two checked-in NIST PDFs. Retrieval metrics were measured with the current chunking/retrieval code.
- **Verified design:** FastAPI service, PDF/DOCX ingestion, token-aware chunking, persistent Chroma with SQLite lifecycle registry, local E5 embeddings, extractive default, optional Gemini/Cohere, citation validation, retrieved-chunk UI, and bounded request/provider handling.
- **Known gaps:** corpus is PDF-only and not independently user-reviewed; no user DOCX, human answer grades, validated judge/agreement, screenshots, demo video, or deployment evidence. The local extractor was tightened after the last answer-metric run, so answer/threshold results need regeneration. The 0.84 cutoff is not production-calibrated.
- **Next:** rerun evaluation and notebook after final edits; inspect and commit the diff. User review and submission artifacts remain necessary.
