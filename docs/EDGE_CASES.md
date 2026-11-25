# Edge-case coverage and demo checklist

This note maps the requested edge cases to current behavior and automated
evidence. It is also a suggested demo-video run sheet. The repository does not
contain a recording; a checklist or screenshot is not a substitute for the
requested video.

## Coverage

| Edge case | Current behavior | Automated evidence / caveat |
|---|---|---|
| Scanned or empty PDF | Rejects a PDF with no extractable text; rejects an empty upload. | `tests/test_app.py::test_upload_rejects_scanned_pdf`, `test_upload_rejects_empty_and_oversized_files` |
| Same file uploaded twice | Returns `409` for duplicate content for the same account. The SQLite uniqueness constraint also arbitrates concurrent duplicate writes. | `tests/test_app.py::test_upload_pdf_and_reject_duplicate`, `tests/test_storage.py::test_concurrent_duplicate_uploads_create_only_one_document` |
| Very large file or very long document | Upload size is bounded by `MAX_UPLOAD_MB`; page/slide counts and extracted text are bounded during parsing/chunking. | `tests/test_app.py::test_upload_rejects_empty_and_oversized_files`, `tests/test_ingestion.py::test_very_long_extracted_text_is_rejected_before_chunking` |
| Question before any document is uploaded | Returns a fixed refusal with no citations, rather than calling generation with empty context. | `tests/test_app.py::test_ask_refuses_when_no_chunks_are_found` |
| Question the documents cannot answer | The local generator abstains if no retrieved sentence overlaps the question; Gemini is instructed to return the fixed refusal when unsupported. | `tests/test_generation.py::test_local_generator_refuses_when_no_retrieved_sentence_matches`, `tests/test_app.py::test_ask_refuses_when_no_chunks_are_found` |
| Question about a deleted document | Deleted vectors are removed from search; a subsequent question returns no citation for that document. | `tests/test_app.py::test_local_upload_ask_delete_round_trip`, `test_persistent_chroma_api_upload_ask_delete_round_trip` |
| Contradictory passages | Gemini is instructed to describe conflicting positions separately. The local extractive mode can surface both equally relevant conflicting statements with citations, but does not independently prove a contradiction. | `tests/test_generation.py::test_local_generator_surfaces_both_conflicting_passages`, `tests/test_app.py::test_ask_surfaces_contradictory_retrieved_passages` |
| Tables, special characters, and non-English text | DOCX/PPTX tables are flattened into row text. UTF-8 content preserves Unicode punctuation, symbols, and non-English text. Local lexical matching includes Unicode terms and bigrams; local E5 retrieval is English-oriented, so non-English retrieval quality is not guaranteed. | `tests/test_ingestion.py::test_docx_table_text_is_preserved`, `test_pptx_table_cells_are_extracted`, `test_utf8_text_preserves_non_english_and_special_characters`, `tests/test_generation.py::test_local_generator_matches_non_english_question_and_cites_unicode_text` |
| Embedding or LLM timeout / rate limit | Provider calls use bounded retries/timeouts and surface rate limits or unavailable-provider errors instead of returning a success-shaped answer. | `tests/test_storage.py::test_cohere_timeout_becomes_unavailable_and_four_xx_is_not_retried`, `test_cohere_retries_transient_rate_limits_with_a_bounded_count`, `tests/test_generation.py::test_provider_rate_limit_is_not_hidden_as_a_success`, `test_gemini_timeout_retries_then_returns_a_valid_answer` |
| Several uploads/questions at once | Storage is exercised with concurrent distinct uploads and concurrent searches; concurrent duplicate uploads result in only one indexed document. | `tests/test_storage.py::test_concurrent_duplicate_uploads_create_only_one_document`, `test_concurrent_queries_and_distinct_uploads_remain_consistent` |
| Corrupt or malformed uploads | Invalid PDF signatures, malformed Office ZIP/XML, unsupported encodings, and binary-looking text are rejected. This is format validation, not malware detection. | `tests/test_app.py::test_rejects_malformed_documents`, `test_upload_requires_file_signature`, `tests/test_ingestion.py::test_pptx_rejects_corrupt_zip_archive`, `test_pptx_rejects_invalid_slide_xml` |

## Suggested demo-video sequence

Use a fresh local account and harmless sample files. Keep the screen recording
on the actual running application/API, and show each response/status clearly.
Do not include real credentials, private source material, or actual service
secrets in the recording.

For each step, explain the reason for the design, not just the visible
request/response. Suggested narration:

- **Local embeddings by default:** make the app reproducible without sending
  documents to an external provider or requiring API credentials.
- **Token-aware chunks with overlap:** respect the embedding model's token
  budget while preserving some context across chunk boundaries.
- **SQLite registry plus Chroma:** use the relational registry for ownership,
  duplicate checks, and document lifecycle; use Chroma for vector similarity.
  Explain that two stores require cleanup/recovery because they do not share an
  atomic transaction.
- **Grounded citations and refusal:** expose retrieved evidence, validate
  citation IDs on the server, and refuse when evidence is unavailable rather
  than imply unsupported certainty.
- **Untrusted uploaded text:** extract text as data instead of executing it,
  and instruct Gemini not to follow embedded directions. Be clear this is not
  antivirus and cannot guarantee immunity to prompt injection.
- **Bounded retries/timeouts and local telemetry:** keep transient provider
  failures visible and bounded; collect timing/stage metrics without storing
  prompts or document text.

1. **Start and authenticate:** show `/health`, create/sign in to a demo account,
   then show that protected endpoints require a token if convenient.
2. **Upload formats and content:** upload one valid PDF plus TXT, Markdown,
   DOCX with a table/special characters, and PPTX with a table. Show the index
   result and source page/slide or section locations. Include a short
   non-English UTF-8 example.
3. **Reject bad/oversized files:** upload an empty or scanned PDF, a malformed
   Office file, and a file above the configured limit; show the client error
   and that no invalid document appears in the list.
4. **Duplicate and length boundaries:** upload an identical file twice and
   show `409`; show a too-long document being rejected or explain the
   configured size/text bound with the corresponding test.
5. **Empty and unsupported questions:** ask before uploading, then ask a
   question not covered by the corpus; show the refusal with no citations.
6. **Contradiction:** index two harmless files that make opposite statements
   about the same example policy, ask a neutral question, and show both
   positions and their independent source citations. This demonstrates
   handling, not automatic truth resolution.
7. **Deletion and access isolation:** delete one indexed document, ask about
   it again and show refusal/no citation. If time permits, sign in as another
   account and show the deleted/other user's documents are not listed.
8. **Provider failure and concurrency:** automated tests cover deterministic
   timeout/rate-limit and concurrent storage cases. To demonstrate live
   provider failures, use a controlled mock/fault-injection setup; do not
   intentionally exhaust a real provider quota. Show parallel requests only
   against harmless test data.
9. **Finish:** show the observability dashboard and the test command/result.

Some edge cases (especially real external-provider outages and simultaneous
HTTP traffic) are best demonstrated with a controlled test harness. Do not
claim a live outage or concurrency test unless it was actually run and recorded.
