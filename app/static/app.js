async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

async function loadDocuments() {
  const documents = await api("/documents");
  const list = document.querySelector("#documents");
  list.innerHTML = "";
  if (!documents.length) {
    const empty = document.createElement("li");
    empty.textContent = "No documents uploaded yet.";
    list.append(empty);
    return;
  }
  for (const doc of documents) {
    const li = document.createElement("li");
    li.textContent = `${doc.filename} (${doc.chunk_count} chunks) `;
    const button = document.createElement("button");
    button.textContent = "Delete";
    button.onclick = async () => {
      try { await api(`/documents/${doc.id}`, { method: "DELETE" }); await loadDocuments(); }
      catch (error) { alert(error.message); }
    };
    li.append(button);
    list.append(li);
  }
}

document.querySelector("#upload-form").onsubmit = async (event) => {
  event.preventDefault();
  const file = document.querySelector("#file").files[0];
  if (!file) return;
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  button.textContent = "Uploading...";
  const form = new FormData();
  form.append("file", file);
  try {
    await api("/documents", { method: "POST", body: form });
    await loadDocuments();
    event.currentTarget.reset();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Upload";
  }
};

document.querySelector("#ask-form").onsubmit = async (event) => {
  event.preventDefault();
  const question = document.querySelector("#question").value;
  const answer = document.querySelector("#answer");
  const chunks = document.querySelector("#chunks");
  const citations = document.querySelector("#citations");
  const chunkCount = document.querySelector("#chunk-count");
  const button = document.querySelector("#ask-button");
  answer.textContent = "Thinking...";
  answer.className = "";
  chunks.innerHTML = "";
  citations.innerHTML = "";
  chunkCount.textContent = "Retrieving chunks...";
  button.disabled = true;
  try {
    const result = await api("/questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    answer.textContent = result.answer;
    chunkCount.textContent = `${result.retrieved_chunks.length} chunk(s) retrieved.`;
    result.citations.forEach((citation, index) => {
      const item = document.createElement("li");
      item.textContent = `[${index + 1}] ${citation.filename}, ${
        citation.page == null ? citation.section || "location unavailable" : `page ${citation.page}`
      } (retrieval rank ${citation.rank})`;
      citations.append(item);
    });
    result.retrieved_chunks.forEach((chunk) => {
      const div = document.createElement("div");
      div.className = "chunk";
      const location = chunk.page == null
        ? chunk.section || "location unavailable"
        : `page ${chunk.page}`;
      div.textContent = `Rank ${chunk.rank} | ${chunk.filename}, ${location} | similarity ${chunk.score.toFixed(3)} | chunk ${chunk.chunk_id}\n${chunk.text}`;
      chunks.append(div);
    });
  } catch (error) {
    answer.textContent = error.message;
    answer.className = "error";
    chunkCount.textContent = "Retrieval details unavailable.";
  } finally {
    button.disabled = false;
  }
};

loadDocuments().catch((error) => alert(error.message));
