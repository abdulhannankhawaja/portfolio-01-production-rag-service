# AI Usage

## Tools and models

- **Coding assistant:** Copilot SDK in VS Code. It was used to inspect the
  project, compare implementation with the supplied project prompt, edit code
  and documentation, and run tests/evaluation.
- **Application embedding model:** `intfloat/e5-small-v2`, downloaded and run
  locally for embeddings and tokenization.
- **Application answer model:** deterministic local extractive baseline by
  default. Gemini is an optional provider; no live Gemini evaluation result is
  claimed here.
- **Optional embedding provider:** Cohere can be configured, but no live
  Cohere-based project evaluation is claimed here.
- **Configuration:** application provider/model settings, temperature,
  timeouts, retries, and embedding choice are controlled through environment
  settings documented in `.env.example`. No credentials are recorded here.

The coding assistant, the local embedding model, and the optional application
LLM are separate components. The assistant's model is not used as an
application API.

## Prompt and transcript

The supplied project instructions and rubric were used as the development
requirements. User requests included reviewing those requirements, continuing
implementation, checking the repository against the supplied prompt, and
correcting gaps. This file is a summary, not a transcript or a complete prompt
archive. The user must export and attach the complete AI chat history required
for submission; no chat export is included or reconstructed in this repository.

## Review responsibility

AI assistance does not substitute for checking the code, evaluation labels,
answers, or citations. The checked-in evaluation evidence remains limited to
the automated checks described in [EVAL.md](./EVAL.md); user review and
human-graded answer evidence are outstanding.
