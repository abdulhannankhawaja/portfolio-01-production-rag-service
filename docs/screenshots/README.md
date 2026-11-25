# Screenshot gallery

This gallery catalogs the screenshots currently stored in this folder. Select
an image to open its full-size version. Captures show different iterations of
the app: some are older layouts and show only PDF/DOCX support. Use the running
application and [main setup guide](../../README.md) as the source of truth for
current behavior.

Before sharing screenshots publicly, check that they do not reveal real
credentials, private document content, or personal information. These images
are visual references and are not, on their own, evidence of a current
deployment or independently verified behavior.

Static screenshots do not demonstrate edge-case handling. Use the
[edge-case demo checklist](../EDGE_CASES.md) to record the actual interactions
for a video; this repository does not include that recording.

## Sign in and account creation

| Screen | Description |
|---|---|
| [Sign in](#sign-in) | Sign-in form in the account screen. |
| [Create account](#create-account) | Account creation form with the password length hint. |

### Sign in

<a href="./login%20page.png"><img src="./login%20page.png" alt="Sign-in screen for the private knowledge workspace" width="720"></a>

### Create account

<a href="./create%20account.png"><img src="./create%20account.png" alt="Create-account screen for the private knowledge workspace" width="720"></a>

## Browser workspace

| Image | What it shows |
|---|---|
| [Updated workspace](#updated-workspace) | Document list, upload panel, and question composer. |
| [Grounded response with passages](#grounded-response-with-retrieved-passages) | Answer, source citation, and expanded retrieved passages. |
| [Response and citation view](#response-and-citation-view) | Earlier response layout with citations and retrieved chunks. |
| [Legacy RAG results view](#legacy-rag-results-view) | Earlier, narrow-screen app view with a response and ranked chunks. |
| [Observability dashboard](#observability-dashboard) | Request metrics and recent request traces. |

### Updated workspace

<a href="./Updated_Frontend.png"><img src="./Updated_Frontend.png" alt="Browser workspace with document list, upload control, and question composer" width="900"></a>

### Grounded response with retrieved passages

<a href="./Detailed%20Response%20with%20retrieved%20passages%20and%20citations.png"><img src="./Detailed%20Response%20with%20retrieved%20passages%20and%20citations.png" alt="Grounded answer with citation and expanded retrieved passages" width="900"></a>

### Response and citation view

<a href="./The%20Response%20Using%20Rag%20Service.png"><img src="./The%20Response%20Using%20Rag%20Service.png" alt="Earlier response view showing the answer, citation, and retrieved chunks" width="520"></a>

### Legacy RAG results view

This is a narrow, older UI capture; its visual layout and supported-format
label may not match the current frontend.

<a href="./Rag%20Service%20Results.jpeg"><img src="./Rag%20Service%20Results.jpeg" alt="Earlier narrow-screen RAG answer and retrieved-passage view" width="360"></a>

### Observability dashboard

<a href="./Observability%20Feature.png"><img src="./Observability%20Feature.png" alt="Observability dashboard with latency, request counts, token usage, and traces" width="900"></a>

## API documentation

### Swagger UI

The Swagger capture is a long, older API-docs screenshot. It illustrates the
interactive API layout; use `/docs` on a running service for the current route
list, schemas, and responses.

<a href="./Swagger%20UI%20All%20requests.jpeg"><img src="./Swagger%20UI%20All%20requests.jpeg" alt="Long screenshot of the API's interactive Swagger documentation" width="360"></a>
