/* ═══════════════════════════════════════════════════════════
   AI Research Assistant — Frontend Application
   ═══════════════════════════════════════════════════════════ */

"use strict";

// ─── Configure marked.js ────────────────────────────────────
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
});

// ─── Application State ─────────────────────────────────────
const state = {
  papers: [],
  selectedPaper: null,
  paperChatHistory: {},   // paperKey → [{role, content}]
  pdfReady: false,
  pdfChunks: 0,
  pdfTrace: null,
  generatedCode: "",
  codeLanguage: "python",
  currentTab: "search",
  reportText: "",
  pdfSummaryText: "",
};

// ─── DOM Helpers ────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const show = (id) => $( id )?.classList.remove("hidden");
const hide = (id) => $( id )?.classList.add("hidden");

// ─── Toast Notifications ────────────────────────────────────
function toast(msg, type = "info", duration = 3500) {
  const wrap = $("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const icons = { success: "fa-circle-check", error: "fa-circle-xmark", info: "fa-circle-info" };
  el.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${msg}</span>`;
  wrap.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove());
  }, duration);
}

// ─── Loading State on Buttons ───────────────────────────────
function setLoading(btnId, loading, originalHTML) {
  const btn = $(btnId);
  if (!btn) return;
  if (loading) {
    btn._original = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> Working…`;
    btn.disabled = true;
  } else {
    btn.innerHTML = originalHTML !== undefined ? originalHTML : btn._original || btn.innerHTML;
    btn.disabled = false;
  }
}

// ─── Render Markdown safely ─────────────────────────────────
function renderMD(text) {
  try { return marked.parse(String(text)); } catch { return String(text); }
}

// ─── Show AI output in a container ─────────────────────────
function showOutput(elId, html, raw) {
  const el = $(elId);
  if (!el) return;
  el.innerHTML = html;
  el.classList.remove("hidden");
  // Re-run highlight on any <code> blocks
  el.querySelectorAll("pre code").forEach(hljs.highlightElement);
}

// ─── API fetch wrapper ──────────────────────────────────────
async function apiFetch(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* ═══════════════════════════════════════════════════════════
   TAB SWITCHING
   ═══════════════════════════════════════════════════════════ */
function switchTab(tab) {
  state.currentTab = tab;
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.setAttribute("aria-selected", b.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `panel-${tab}`);
  });
  if (tab === "compare") populateCompareSelects();
}

/* ═══════════════════════════════════════════════════════════
   TAB 1 — SEARCH PAPERS
   ═══════════════════════════════════════════════════════════ */
async function searchPapers() {
  const topic = $("search-input").value.trim();
  if (!topic) { toast("Please enter a search topic", "error"); return; }

  setLoading("search-btn", true);
  $("search-results").innerHTML = buildSkeletons(4);
  hide("paper-detail");

  try {
    const data = await apiFetch("/api/search", { topic });
    state.papers = data.papers || [];
    renderResults(state.papers);
    if (state.papers.length === 0) {
      $("search-results").innerHTML = emptyState("No papers found", "Try a different search term.");
    } else {
      toast(`Found ${state.papers.length} papers`, "success");
      if (state.currentTab === "compare") populateCompareSelects();
    }
  } catch (err) {
    $("search-results").innerHTML = emptyState("Search failed", err.message);
    toast(err.message, "error");
  } finally {
    setLoading("search-btn", false, `<i class="fas fa-search"></i> Search`);
  }
}

function buildSkeletons(n) {
  return `<div class="results-grid">${Array.from({ length: n }, () => `
    <div class="paper-card">
      <div class="skeleton" style="height:1.1rem;width:85%;border-radius:6px"></div>
      <div class="skeleton" style="height:.8rem;width:55%;border-radius:6px;margin-top:.3rem"></div>
      <div class="skeleton" style="height:.7rem;width:40%;border-radius:6px;margin-top:.3rem"></div>
    </div>`).join("")}</div>`;
}

function emptyState(title, sub) {
  return `<div class="empty-state">
    <div class="empty-icon"><i class="fas fa-magnifying-glass"></i></div>
    <h3>${title}</h3><p>${sub}</p>
  </div>`;
}

function renderResults(papers) {
  const grid = document.createElement("div");
  grid.className = "results-grid";

  papers.forEach((p, i) => {
    const card = document.createElement("div");
    card.className = "paper-card";
    card.style.animationDelay = `${i * 0.06}s`;
    card.onclick = () => openPaperDetail(i);

    const src = (p.source || "").toLowerCase().includes("arxiv") ? "arxiv" : "scholar";
    const srcLabel = src === "arxiv" ? "arXiv" : "Semantic Scholar";
    const authorsStr = formatAuthors(p.authors);
    const citationBadge = p.citations > 0
      ? `<span class="badge badge-cite"><i class="fas fa-quote-left"></i> ${p.citations}</span>` : "";

    card.innerHTML = `
      <div class="paper-card-title">${escHtml(p.title)}</div>
      <div class="paper-card-meta">
        <span class="badge badge-${src}">${srcLabel}</span>
        ${p.year ? `<span class="badge badge-year"><i class="fas fa-calendar-alt"></i> ${p.year}</span>` : ""}
        ${citationBadge}
      </div>
      <div class="paper-card-authors"><i class="fas fa-user-group" style="margin-right:.3rem"></i>${escHtml(authorsStr)}</div>`;

    grid.appendChild(card);
  });

  const info = document.createElement("div");
  info.className = "results-info";
  info.innerHTML = `<i class="fas fa-layer-group"></i> Showing ${papers.length} paper${papers.length !== 1 ? "s" : ""} from Semantic Scholar &amp; arXiv`;

  $("search-results").innerHTML = "";
  $("search-results").appendChild(info);
  $("search-results").appendChild(grid);
}

function openPaperDetail(index) {
  const p = state.papers[index];
  if (!p) return;
  state.selectedPaper = p;

  const src = (p.source || "").toLowerCase().includes("arxiv") ? "arxiv" : "scholar";
  const srcLabel = src === "arxiv" ? "arXiv" : "Semantic Scholar";

  $("detail-title").textContent = p.title || "";
  $("detail-authors").textContent = "Authors: " + (formatAuthors(p.authors) || "Unknown");
  $("detail-abstract").textContent = p.abstract || "No abstract available.";

  const badgeContainer = $("detail-badges");
  badgeContainer.innerHTML = `
    <span class="badge badge-${src}">${srcLabel}</span>
    ${p.year  ? `<span class="badge badge-year"><i class="fas fa-calendar-alt"></i> ${p.year}</span>` : ""}
    ${p.venue ? `<span class="badge badge-year">${escHtml(p.venue)}</span>` : ""}
    ${p.citations > 0 ? `<span class="badge badge-cite"><i class="fas fa-quote-left"></i> ${p.citations} citations</span>` : ""}`;

  const urlEl = $("detail-url");
  if (p.url) {
    urlEl.href = p.url;
    urlEl.style.display = "inline-flex";
  } else {
    urlEl.style.display = "none";
  }

  // Reset action areas
  hide("report-output");
  hide("download-report-btn");
  $("paper-chat").innerHTML = "";
  $("paper-q-input").value = "";
  state.reportText = "";

  // Init chat history for this paper
  const key = paperKey(p);
  if (!state.paperChatHistory[key]) state.paperChatHistory[key] = [];
  renderPaperChat(key);

  show("paper-detail");
  $("paper-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closePaperDetail() {
  hide("paper-detail");
  $("search-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function generateReport() {
  if (!state.selectedPaper) return;
  setLoading("report-btn", true);
  hide("report-output");
  hide("download-report-btn");

  try {
    const data = await apiFetch("/api/paper-report", state.selectedPaper);
    state.reportText = data.report || "";
    showOutput("report-output", renderMD(state.reportText));
    show("download-report-btn");
    toast("Report generated", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading("report-btn", false, `<i class="fas fa-wand-magic-sparkles"></i> Generate Report`);
  }
}

function downloadReport() {
  if (!state.reportText) return;
  downloadFile(state.reportText, "paper_report.md", "text/markdown");
}

async function askPaperQuestion() {
  if (!state.selectedPaper) return;
  const q = $("paper-q-input").value.trim();
  if (!q) { toast("Please enter a question", "error"); return; }

  const key = paperKey(state.selectedPaper);
  const history = state.paperChatHistory[key] || [];

  appendMiniChat(key, "user", q);
  $("paper-q-input").value = "";

  // typing indicator
  const typingId = "paper-typing";
  appendTypingIndicator("paper-chat", typingId);

  try {
    const data = await apiFetch("/api/paper-question", {
      paper: state.selectedPaper,
      question: q,
      history,
    });
    removeTypingIndicator(typingId);
    appendMiniChat(key, "ai", data.answer || "");
  } catch (err) {
    removeTypingIndicator(typingId);
    toast(err.message, "error");
  }
}

function paperKey(p) {
  return `${p.title}|${p.source || ""}`;
}

function appendMiniChat(key, role, content) {
  if (!state.paperChatHistory[key]) state.paperChatHistory[key] = [];
  state.paperChatHistory[key].push({ role, content });
  renderPaperChat(key);
}

function renderPaperChat(key) {
  const container = $("paper-chat");
  const history = state.paperChatHistory[key] || [];
  container.innerHTML = history.map((msg) => `
    <div class="mini-msg ${msg.role === "user" ? "user" : "ai"}">
      <div class="mini-avatar"><i class="fas ${msg.role === "user" ? "fa-user" : "fa-robot"}"></i></div>
      <div class="mini-bubble">${renderMD(msg.content)}</div>
    </div>`).join("");
  container.scrollTop = container.scrollHeight;
}

/* ═══════════════════════════════════════════════════════════
   TAB 2 — PDF Q&A
   ═══════════════════════════════════════════════════════════ */
function handleDrop(e) {
  e.preventDefault();
  $("upload-zone").classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) uploadPDF(file);
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) uploadPDF(file);
}

async function uploadPDF(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    toast("Only PDF files are allowed", "error");
    return;
  }

  const status = $("upload-status");
  status.className = "upload-status";
  status.textContent = "Uploading and processing...";
  $("pdf-input").disabled = true;

  const formData = new FormData();
  formData.append("pdf", file);

  try {
    const res = await fetch("/api/pdf-upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload failed");

    state.pdfReady = true;
    state.pdfChunks = data.chunks;
    status.className = "upload-status success";
    status.innerHTML = `<i class="fas fa-circle-check"></i> Ready — ${data.chunks} chunks extracted`;
    $("pdf-ready-text").textContent = `${file.name} — ${data.chunks} chunks ready`;

    // Reset previous results
    hide("pdf-answer");
    hide("pdf-rag-trace");
    state.pdfTrace = null;
    hide("pdf-summary-output");
    hide("download-pdf-summary-btn");
    $("pdf-question").value = "";
    state.pdfSummaryText = "";

    show("pdf-qa-section");
    toast("PDF processed successfully!", "success");
  } catch (err) {
    status.className = "upload-status error";
    status.textContent = err.message;
    toast(err.message, "error");
  } finally {
    $("pdf-input").disabled = false;
  }
}

async function askPDFQuestion() {
  const q = $("pdf-question").value.trim();
  if (!q) { toast("Please enter a question", "error"); return; }
  if (!state.pdfReady) { toast("Please upload a PDF first", "error"); return; }

  hide("pdf-answer");
  hide("pdf-rag-trace");
  state.pdfTrace = null;
  const spinner = document.createElement("div");
  spinner.className = "ai-output";
  spinner.innerHTML = `<span class="spinner"></span> Searching through the document…`;
  $("pdf-answer").replaceWith(spinner);
  spinner.id = "pdf-answer";

  try {
    const data = await apiFetch("/api/pdf-question", { question: q });
    showOutput("pdf-answer", renderMD(data.answer || ""));
    state.pdfTrace = data.trace || null;
    renderPDFTrace(state.pdfTrace);
    toast("Answer ready", "success");
  } catch (err) {
    showOutput("pdf-answer", `<span style="color:#f87171">${err.message}</span>`);
    hide("pdf-rag-trace");
    toast(err.message, "error");
  }
}

async function generatePDFSummary() {
  if (!state.pdfReady) { toast("Please upload a PDF first", "error"); return; }
  setLoading("pdf-summary-btn", true);
  hide("pdf-summary-output");
  hide("download-pdf-summary-btn");

  try {
    const data = await apiFetch("/api/pdf-summary", {});
    state.pdfSummaryText = data.summary || "";
    showOutput("pdf-summary-output", renderMD(state.pdfSummaryText));
    show("download-pdf-summary-btn");
    toast("Summary generated", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading("pdf-summary-btn", false, `<i class="fas fa-wand-magic-sparkles"></i> Generate Summary`);
  }
}

function downloadPDFSummary() {
  if (!state.pdfSummaryText) return;
  downloadFile(state.pdfSummaryText, "pdf_summary.md", "text/markdown");
}

/* ═══════════════════════════════════════════════════════════
   TAB 4 — CODE GENERATOR
   ═══════════════════════════════════════════════════════════ */
async function generateCode() {
  const task = $("code-task").value.trim();
  const language = $("code-language").value;

  if (!task) { toast("Please describe a coding task", "error"); return; }

  setLoading("gen-code-btn", true);
  hide("code-output-section");

  try {
    const data = await apiFetch("/api/generate-code", { task, language });
    state.generatedCode = data.code || "";
    state.codeLanguage = language;

    if (data.trace && data.trace.chat_log) {
      show("code-agent-trace");
      const chatContainer = $("agent-chat-log");
      chatContainer.innerHTML = ""; // Clear old
      data.trace.chat_log.forEach(msg => {
        const bubble = document.createElement("div");
        const isQa = msg.role.includes("QA");
        bubble.style.cssText = `
          padding: 10px 15px; 
          border-radius: 8px; 
          background: ${isQa ? '#3a2024' : '#1e293b'}; 
          border-left: 4px solid ${isQa ? '#ef4444' : '#3b82f6'};
          font-size: 13px;
        `;
        const header = document.createElement("strong");
        header.style.display = "block";
        header.style.marginBottom = "5px";
        header.style.color = isQa ? "#fca5a5" : "#93c5fd";
        header.textContent = msg.role;
        
        const content = document.createElement("div");
        content.style.whiteSpace = "pre-wrap";
        content.textContent = msg.message;
        
        bubble.appendChild(header);
        bubble.appendChild(content);
        chatContainer.appendChild(bubble);
      });
    } else {
      hide("code-agent-trace");
    }

    const langLabels = {
      python: "🐍 Python", javascript: "🌐 JavaScript",
      typescript: "🔷 TypeScript", java: "☕ Java", cpp: "⚙️ C++",
    };
    $("code-lang-badge").textContent = langLabels[language] || language;

    const codeEl = $("generated-code");
    codeEl.textContent = state.generatedCode;
    codeEl.removeAttribute("data-highlighted");

    // Strip fenced code block wrappers if present
    const clean = state.generatedCode.replace(/^```[\w]*\n?/, "").replace(/\n?```$/, "");
    codeEl.textContent = clean;
    hljs.highlightElement(codeEl);

    show("code-output-section");
    toast("Code generated!", "success");
    $("code-output-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading("gen-code-btn", false, `<i class="fas fa-wand-magic-sparkles"></i> Generate Code`);
  }
}

function copyCode() {
  const text = $("generated-code").textContent;
  navigator.clipboard.writeText(text).then(() => {
    toast("Code copied to clipboard!", "success");
  }).catch(() => toast("Copy failed", "error"));
}

function downloadCode() {
  const extMap = {
    python: "py", javascript: "js", typescript: "ts",
    java: "java", cpp: "cpp",
  };
  const ext = extMap[state.codeLanguage] || "txt";
  const text = $("generated-code").textContent;
  downloadFile(text, `generated_code.${ext}`, "text/plain");
}

/* ═══════════════════════════════════════════════════════════
   TAB 5 — COMPARE PAPERS
   ═══════════════════════════════════════════════════════════ */
function populateCompareSelects() {
  if ($("auto-compare-topic") && !$("auto-compare-topic").value.trim()) {
    const topic = $("search-input")?.value?.trim() || "";
    $("auto-compare-topic").value = topic;
  }

  if (state.papers.length < 2) {
    hide("compare-setup");
    show("compare-no-papers");
    return;
  }
  show("compare-setup");
  hide("compare-no-papers");

  const options = state.papers.map((p, i) =>
    `<option value="${i}">${escHtml(p.title.slice(0, 80))}${p.title.length > 80 ? "…" : ""}</option>`
  ).join("");

  $("compare-p1").innerHTML = options;
  $("compare-p2").innerHTML = options;
  // Default second paper to different index
  if (state.papers.length > 1) $("compare-p2").value = "1";
}

async function comparePapers() {
  const i1 = parseInt($("compare-p1").value);
  const i2 = parseInt($("compare-p2").value);
  const aspect = $("compare-aspect").value;

  if (i1 === i2) { toast("Please select two different papers", "error"); return; }

  const p1 = state.papers[i1];
  const p2 = state.papers[i2];

  if (!p1?.abstract || !p2?.abstract) {
    toast("One or both papers lack an abstract for comparison", "error");
    return;
  }

  setLoading("compare-btn", true);
  hide("compare-result");

  try {
    const data = await apiFetch("/api/compare-papers", { paper1: p1, paper2: p2, aspect });
    showOutput("compare-result", renderMD(data.result || ""));
    toast("Comparison complete!", "success");
    $("compare-result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading("compare-btn", false, `<i class="fas fa-scale-balanced"></i> Compare Papers`);
  }
}

function shortText(value, maxLen = 120) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "-";
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 3).trim() + "...";
}

function renderListInline(items) {
  if (!Array.isArray(items) || items.length === 0) return "-";
  return items.map((i) => shortText(i, 80)).join("; ");
}

function renderStructuredRecordsTable(records) {
  if (!Array.isArray(records) || records.length === 0) {
    return "<p>No structured records were generated.</p>";
  }

  const rows = records.map((r) => `
    <tr>
      <td>${escHtml(shortText(r.title, 60))}</td>
      <td>${escHtml(shortText(r.problem, 130))}</td>
      <td>${escHtml(shortText(r.method, 130))}</td>
      <td>${escHtml(shortText(r.dataset, 80))}</td>
      <td>${escHtml(shortText(r.results, 130))}</td>
      <td>${escHtml(renderListInline(r.strengths))}</td>
      <td>${escHtml(renderListInline(r.limitations))}</td>
    </tr>
  `).join("");

  return `
    <div style="overflow-x:auto; margin-top: 1rem;">
      <table style="width:100%; border-collapse:collapse; font-size:0.88rem;">
        <thead>
          <tr>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Paper</th>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Problem</th>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Method</th>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Dataset</th>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Results</th>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Strengths</th>
            <th style="text-align:left; padding:8px; border-bottom:1px solid rgba(255,255,255,.18);">Limitations</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderAutoCompareResult(data) {
  const topic = escHtml(data.topic || "-");
  const topK = escHtml(data.top_k || "-");
  const aspect = escHtml(data.aspect || "overall quality");

  const structuredTable = renderStructuredRecordsTable(data.structured || []);
  const compareMd = renderMD(data.comparison_markdown || "");
  const plannerMd = renderMD(data.insights_markdown || "");

  return `
    <h3 style="margin-bottom: 0.4rem;">Auto Analysis: ${topic}</h3>
    <p style="margin-bottom: 0.9rem;"><strong>Papers:</strong> ${topK} &nbsp;|&nbsp; <strong>Aspect:</strong> ${aspect}</p>

    <h4>Structured Extraction (Reader Agent)</h4>
    ${structuredTable}

    <h4 style="margin-top:1.2rem;">Cross-Paper Comparison (Compare Agent)</h4>
    <div>${compareMd}</div>

    <h4 style="margin-top:1.2rem;">Final Insights (Planner Agent)</h4>
    <div>${plannerMd}</div>
  `;
}

function renderAutoCompareAgentLog(trace) {
  const wrap = $("auto-compare-agent-trace");
  const body = $("auto-compare-agent-log");

  if (!wrap || !body) return;

  const logs = Array.isArray(trace?.agent_log) ? trace.agent_log : [];
  if (logs.length === 0) {
    hide("auto-compare-agent-trace");
    return;
  }

  body.innerHTML = logs.map((entry) => `
    <div style="padding:10px 12px; border:1px solid rgba(255,255,255,.12); border-radius:10px; margin-bottom:10px; background:rgba(255,255,255,.04);">
      <div style="font-weight:700; margin-bottom:5px;">${escHtml(entry.role || "Agent")}</div>
      <div style="font-size:0.9rem; line-height:1.5;">${escHtml(entry.message || "")}</div>
    </div>
  `).join("");

  show("auto-compare-agent-trace");
}

async function compareTopPapersAuto() {
  const topicEl = $("auto-compare-topic");
  const topKEl = $("auto-compare-topk");
  const aspectEl = $("auto-compare-aspect");

  const topic = topicEl?.value?.trim() || $("search-input")?.value?.trim() || "";
  const topK = parseInt(topKEl?.value || "3", 10);
  const aspect = aspectEl?.value || "overall quality";

  if (!topic) {
    toast("Please enter a topic for auto comparison", "error");
    return;
  }

  setLoading("compare-auto-btn", true);
  hide("auto-compare-result");
  hide("auto-compare-agent-trace");

  try {
    const data = await apiFetch("/api/compare-top-papers", {
      topic,
      top_k: topK,
      aspect,
    });

    showOutput("auto-compare-result", renderAutoCompareResult(data));
    renderAutoCompareAgentLog(data.trace || {});

    toast("Auto comparison complete!", "success");
    $("auto-compare-result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    toast(err.message, "error");
  } finally {
    setLoading("compare-auto-btn", false, `<i class="fas fa-brain"></i> Auto Compare Top Papers`);
  }
}

/* ═══════════════════════════════════════════════════════════
   TYPING INDICATOR HELPERS
   ═══════════════════════════════════════════════════════════ */
function appendTypingIndicator(containerId, indicatorId) {
  const container = $(containerId);
  if (!container) return null;

  const wrap = document.createElement("div");
  wrap.id = indicatorId;

  wrap.className = "mini-msg ai";
  wrap.innerHTML = `
    <div class="mini-avatar"><i class="fas fa-robot"></i></div>
    <div class="typing-indicator"><span></span><span></span><span></span></div>`;

  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
  return wrap;
}

function removeTypingIndicator(id) {
  $(id)?.remove();
}

function formatChunkList(indices) {
  if (!Array.isArray(indices) || indices.length === 0) return "None";
  return indices.map((idx) => `#${idx}`).join(", ");
}

function renderPDFTrace(trace) {
  const wrap = $("pdf-rag-trace");
  const metaEl = $("pdf-trace-meta");
  const stagesEl = $("pdf-trace-stages");
  const finalEl = $("pdf-trace-final");

  if (!wrap || !metaEl || !stagesEl || !finalEl) return;
  if (!trace || typeof trace !== "object" || Object.keys(trace).length === 0) {
    hide("pdf-rag-trace");
    return;
  }

  const modeUsed = trace.mode_used || "unknown";
  const modeLabel = modeUsed === "hybrid" ? "Hybrid (BM25 + Dense + RRF)" : "Baseline keyword fallback";
  const rewritten = trace.query_rewritten ? "Yes" : "No";
  const fallback = trace.fallback_used ? "Yes" : "No";
  const chunkStats = `${trace.chunk_count_selected || 0} selected / ${trace.chunk_count_total || 0} total`;

  const queryUsed = trace.query_used || "-";

  metaEl.innerHTML = `
    <div class="trace-pill"><span>Mode</span><strong>${escHtml(modeLabel)}</strong></div>
    <div class="trace-pill"><span>Query Rewritten</span><strong>${rewritten}</strong></div>
    <div class="trace-pill"><span>Fallback Used</span><strong>${fallback}</strong></div>
    <div class="trace-pill"><span>Chunks</span><strong>${escHtml(chunkStats)}</strong></div>
    <div class="trace-pill trace-pill-wide"><span>Query Used</span><strong>${escHtml(queryUsed)}</strong></div>
  `;

  const stages = trace.stage_top_chunks || {};
  const stageRows = [
    ["BM25 top", formatChunkList(stages.bm25)],
    ["Dense top", formatChunkList(stages.dense)],
    ["RRF top", formatChunkList(stages.rrf)],
    ["Final used", formatChunkList(stages.final)],
  ];

  stagesEl.innerHTML = stageRows
    .map(([label, value]) => `<li><strong>${escHtml(label)}:</strong> ${escHtml(value)}</li>`)
    .join("");

  const finalChunks = Array.isArray(trace.final_chunk_snippets) ? trace.final_chunk_snippets : [];
  const finalIds = Array.isArray(stages.final) ? stages.final : [];

  if (finalChunks.length === 0) {
    finalEl.innerHTML = "<li>No final chunk snippets available.</li>";
  } else {
    finalEl.innerHTML = finalChunks
      .map((snippet, i) => {
        const chunkTag = finalIds[i] !== undefined ? `Chunk #${finalIds[i]}` : `Chunk ${i + 1}`;
        return `<li><strong>${escHtml(chunkTag)}:</strong> ${escHtml(snippet)}...</li>`;
      })
      .join("");
  }

  show("pdf-rag-trace");
}

/* ═══════════════════════════════════════════════════════════
   UTILITIES
   ═══════════════════════════════════════════════════════════ */
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatAuthors(authors) {
  if (!authors || authors.length === 0) return "Unknown Authors";
  if (authors.length <= 3) return authors.join(", ");
  return authors.slice(0, 2).join(", ") + " et al.";
}

function downloadFile(content, filename, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ═══════════════════════════════════════════════════════════
   SCROLL ANIMATIONS (Intersection Observer)
   ═══════════════════════════════════════════════════════════ */
function initScrollAnimations() {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry, i) => {
        if (entry.isIntersecting) {
          setTimeout(() => entry.target.classList.add("visible"), i * 100);
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
}

/* ─── Navbar shadow on scroll ───────────────────────────── */
function initNavbar() {
  window.addEventListener("scroll", () => {
    document.getElementById("navbar").classList.toggle("scrolled", window.scrollY > 20);
  }, { passive: true });
}

/* ─── Ripple effect on primary buttons ─────────────────── */
function initRipple() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-primary, .hero-cta");
    if (!btn) return;
    const ripple = document.createElement("span");
    const rect = btn.getBoundingClientRect();
    Object.assign(ripple.style, {
      position: "absolute",
      width: "0", height: "0",
      borderRadius: "50%",
      background: "rgba(255,255,255,0.3)",
      transform: "translate(-50%,-50%)",
      left: `${e.clientX - rect.left}px`,
      top:  `${e.clientY - rect.top}px`,
      animation: "rippleEffect .6s ease-out forwards",
      pointerEvents: "none",
    });
    if (getComputedStyle(btn).position === "static") btn.style.position = "relative";
    btn.style.overflow = "hidden";
    btn.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());
  });

  // Inject ripple keyframe
  const style = document.createElement("style");
  style.textContent = `@keyframes rippleEffect {
    to { width:200px; height:200px; opacity:0; }
  }`;
  document.head.appendChild(style);
}

/* ─── Keyboard shortcut: "/" to focus search ──────────── */
function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT" &&
        document.activeElement.tagName !== "TEXTAREA") {
      e.preventDefault();
      switchTab("search");
      $("search-input")?.focus();
    }
  });
}

/* ═══════════════════════════════════════════════════════════
   INIT
   ═══════════════════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  initScrollAnimations();
  initNavbar();
  initRipple();
  initKeyboardShortcuts();

  // Allow clicking the upload zone itself to open file picker
  $("upload-zone")?.addEventListener("click", (e) => {
    if (!e.target.closest("button")) {
      $("pdf-input").click();
    }
  });
});
