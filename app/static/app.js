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
  const form = new FormData();
  form.append("file", file);
  try { await api("/documents", { method: "POST", body: form }); await loadDocuments(); }
  catch (error) { alert(error.message); }
};

document.querySelector("#ask-form").onsubmit = async (event) => {
  event.preventDefault();
  const question = document.querySelector("#question").value;
  const answer = document.querySelector("#answer");
  const chunks = document.querySelector("#chunks");
  answer.textContent = "Thinking...";
  chunks.innerHTML = "";
  try {
    const result = await api("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    answer.textContent = result.answer;
    for (const chunk of result.retrieved_chunks) {
      const div = document.createElement("div");
      div.className = "chunk";
      div.textContent = `[${chunk.chunk_index + 1}] ${chunk.filename}, page ${chunk.page ?? "N/A"} (score ${chunk.score.toFixed(3)})\n${chunk.text}`;
      chunks.append(div);
    }
  } catch (error) {
    answer.textContent = error.message;
    answer.className = "error";
  }
};

loadDocuments().catch((error) => alert(error.message));
