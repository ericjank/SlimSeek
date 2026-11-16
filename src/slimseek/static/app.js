const elements = {
  providerStatus: document.querySelector("#provider-status"),
  documentCount: document.querySelector("#document-count"),
  documentList: document.querySelector("#document-list"),
  dropZone: document.querySelector("#drop-zone"),
  fileInput: document.querySelector("#file-input"),
  selectedFile: document.querySelector("#selected-file"),
  uploadButton: document.querySelector("#upload-button"),
  uploadMessage: document.querySelector("#upload-message"),
  queryForm: document.querySelector("#query-form"),
  question: document.querySelector("#question"),
  topK: document.querySelector("#top-k"),
  queryButton: document.querySelector("#query-button"),
  queryMessage: document.querySelector("#query-message"),
  answerSection: document.querySelector("#answer-section"),
  answer: document.querySelector("#answer"),
  sources: document.querySelector("#sources"),
  welcome: document.querySelector("#welcome"),
};

let selectedFile = null;

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map(item => item.msg).join("；");
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function setMessage(element, text, type = "") {
  element.textContent = text;
  element.className = `inline-message ${type}`;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function createDocumentItem(document) {
  const container = window.document.createElement("article");
  container.className = "document-item";

  const icon = window.document.createElement("span");
  icon.className = "file-icon";
  const extension = document.filename.split(".").pop();
  icon.textContent = extension.slice(0, 4).toUpperCase();

  const info = window.document.createElement("div");
  info.className = "document-info";
  const name = window.document.createElement("p");
  name.className = "document-name";
  name.textContent = document.filename;
  name.title = document.filename;
  const meta = window.document.createElement("span");
  meta.className = "document-meta";
  meta.textContent = `${formatSize(document.size)} · ${document.chunk_count} 个片段`;
  info.append(name, meta);

  const remove = window.document.createElement("button");
  remove.className = "delete-document";
  remove.type = "button";
  remove.title = `删除 ${document.filename}`;
  remove.setAttribute("aria-label", `删除 ${document.filename}`);
  remove.textContent = "×";
  remove.addEventListener("click", async () => {
    if (!window.confirm(`确定删除“${document.filename}”及其索引吗？`)) return;
    remove.disabled = true;
    try {
      await request(`/api/documents/${document.id}`, { method: "DELETE" });
      await Promise.all([loadDocuments(), loadHealth()]);
      elements.answerSection.hidden = true;
      elements.welcome.hidden = false;
    } catch (error) {
      window.alert(error.message);
      remove.disabled = false;
    }
  });

  container.append(icon, info, remove);
  return container;
}

async function loadDocuments() {
  try {
    const documents = await request("/api/documents");
    elements.documentCount.textContent = documents.length;
    elements.documentList.replaceChildren();
    if (!documents.length) {
      const empty = document.createElement("p");
      empty.className = "empty-documents";
      empty.textContent = "还没有文档，从上方导入第一份资料。";
      elements.documentList.append(empty);
      return;
    }
    documents.forEach(item => elements.documentList.append(createDocumentItem(item)));
  } catch (error) {
    setMessage(elements.uploadMessage, error.message, "error");
  }
}

async function loadHealth() {
  try {
    const health = await request("/api/health");
    elements.providerStatus.textContent = `${health.provider === "openai" ? "OpenAI 兼容" : "Ollama"} · ${health.chat_model}`;
    elements.providerStatus.title = `嵌入模型：${health.embedding_model}\n生成模型：${health.chat_model}`;
    elements.providerStatus.className = "provider-status ready";
  } catch (error) {
    elements.providerStatus.textContent = "服务连接失败";
    elements.providerStatus.className = "provider-status error";
  }
}

function chooseFile(file) {
  selectedFile = file || null;
  elements.uploadButton.disabled = !selectedFile;
  elements.selectedFile.hidden = !selectedFile;
  elements.selectedFile.textContent = selectedFile ? `${selectedFile.name} · ${formatSize(selectedFile.size)}` : "";
  setMessage(elements.uploadMessage, "");
}

elements.dropZone.addEventListener("click", () => elements.fileInput.click());
elements.dropZone.addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    elements.fileInput.click();
  }
});
elements.fileInput.addEventListener("change", () => chooseFile(elements.fileInput.files[0]));
["dragenter", "dragover"].forEach(type => elements.dropZone.addEventListener(type, event => {
  event.preventDefault();
  elements.dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach(type => elements.dropZone.addEventListener(type, event => {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
}));
elements.dropZone.addEventListener("drop", event => chooseFile(event.dataTransfer.files[0]));

elements.uploadButton.addEventListener("click", async () => {
  if (!selectedFile) return;
  const form = new FormData();
  form.append("file", selectedFile);
  elements.uploadButton.disabled = true;
  setMessage(elements.uploadMessage, "正在解析文档并建立索引…");
  try {
    const document = await request("/api/documents", { method: "POST", body: form });
    setMessage(elements.uploadMessage, `已导入 ${document.filename}，共 ${document.chunk_count} 个片段。`, "success");
    elements.fileInput.value = "";
    chooseFile(null);
    setMessage(elements.uploadMessage, `已导入 ${document.filename}，共 ${document.chunk_count} 个片段。`, "success");
    await Promise.all([loadDocuments(), loadHealth()]);
  } catch (error) {
    setMessage(elements.uploadMessage, error.message, "error");
  } finally {
    elements.uploadButton.disabled = !selectedFile;
  }
});

function renderSources(citations) {
  elements.sources.replaceChildren();
  if (!citations.length) return;
  const heading = document.createElement("h3");
  heading.textContent = `来源 · ${citations.length}`;
  elements.sources.append(heading);
  citations.forEach((citation, index) => {
    const details = document.createElement("details");
    details.className = "source-item";
    const summary = document.createElement("summary");
    const location = citation.page_start ? `第 ${citation.page_start} 页` : `片段 ${citation.chunk_index + 1}`;
    summary.textContent = `[${index + 1}] ${citation.filename} · ${location} · `;
    const score = document.createElement("span");
    score.className = "source-score";
    score.textContent = `相关度 ${(citation.score * 100).toFixed(0)}%`;
    summary.append(score);
    const text = document.createElement("p");
    text.textContent = citation.text;
    details.append(summary, text);
    elements.sources.append(details);
  });
}

elements.queryForm.addEventListener("submit", async event => {
  event.preventDefault();
  const question = elements.question.value.trim();
  if (!question) {
    setMessage(elements.queryMessage, "请输入问题。", "error");
    return;
  }
  elements.queryButton.disabled = true;
  setMessage(elements.queryMessage, "正在检索并生成回答…");
  elements.answerSection.hidden = true;
  elements.welcome.hidden = false;
  try {
    const result = await request("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: Number(elements.topK.value) }),
    });
    elements.answer.textContent = result.answer;
    renderSources(result.citations);
    elements.answerSection.hidden = false;
    elements.welcome.hidden = true;
    setMessage(elements.queryMessage, "");
  } catch (error) {
    setMessage(elements.queryMessage, error.message, "error");
  } finally {
    elements.queryButton.disabled = false;
  }
});

loadHealth();
loadDocuments();
