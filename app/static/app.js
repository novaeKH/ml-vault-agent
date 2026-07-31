const MODES = {
  chat: { label: "Chat", title: "Chat", placeholder: "Спросите о ML, Python, алгоритмах или коде…" },
  tutor: { label: "Tutor", title: "Tutor", placeholder: "Тема или вопрос для разбора…" },
  interviewer: { label: "Interviewer", title: "Interviewer", placeholder: "Укажите тему собеседования…" },
  practice: { label: "Practice", title: "Algorithm Practice", placeholder: "Тема, уровень или ваша попытка решения…" },
  code: { label: "Code Tutor", title: "Code Tutor", placeholder: "Вставьте код или опишите ошибку…" },
  code_builder: { label: "Code Builder", title: "Code Builder", placeholder: "Опишите полный скрипт или проект, который нужно собрать…" },
};

const CALLOUT_TYPES = {
  summary: { label: "Коротко", icon: "✦" },
  note: { label: "Важно", icon: "i" },
  tip: { label: "Совет", icon: "→" },
  warning: { label: "Обратите внимание", icon: "!" },
  example: { label: "Пример", icon: "<>" },
  question: { label: "Вопрос", icon: "?" },
  success: { label: "Верно", icon: "✓" },
};

const appState = {
  mode: "chat",
  sessionId: crypto.randomUUID(),
  sending: false,
  status: null,
  messagesStarted: false,
};

const elements = {
  conversation: document.querySelector("#conversation"),
  welcome: document.querySelector("#welcome"),
  emptyStateMeta: document.querySelector("#empty-state-meta"),
  modeTitle: document.querySelector("#mode-title"),
  composer: document.querySelector("#composer"),
  input: document.querySelector("#message-input"),
  send: document.querySelector("#send-button"),
  newChat: document.querySelector("#new-chat-button"),
  settingsButton: document.querySelector("#settings-button"),
  settingsDrawer: document.querySelector("#settings-drawer"),
  closeSettings: document.querySelector("#close-settings"),
  backdrop: document.querySelector("#backdrop"),
  settingsForm: document.querySelector("#settings-form"),
  candidateList: document.querySelector("#candidate-list"),
  installedModels: document.querySelector("#installed-models"),
  reindex: document.querySelector("#reindex-button"),
  fullReindex: document.querySelector("#full-reindex-button"),
  vaultDot: document.querySelector("#vault-dot"),
  vaultName: document.querySelector("#vault-name"),
  indexSummary: document.querySelector("#index-summary"),
  indexProgress: document.querySelector("#index-progress"),
  runtimeStatus: document.querySelector("#runtime-status"),
  setupNote: document.querySelector("#setup-note"),
  toastRegion: document.querySelector("#toast-region"),
  sidebar: document.querySelector("#sidebar"),
  mobileMenu: document.querySelector("#mobile-menu"),
};

function toast(message) {
  const item = document.createElement("div");
  item.className = "toast";
  item.textContent = message;
  elements.toastRegion.append(item);
  setTimeout(() => item.remove(), 4200);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pluralizeRu(value, one, few, many) {
  const mod100 = value % 100;
  const mod10 = value % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

function prepareMath(markdown) {
  const slots = [];
  const blockReplaced = markdown.replace(/\$\$([\s\S]*?)\$\$/g, (_, formula) => {
    const index = slots.push({ formula, display: true }) - 1;
    return `\n\n<span class="math-slot math-block" data-math-index="${index}"></span>\n\n`;
  });
  const withInline = blockReplaced.replace(/(^|[^\\$])\$([^$\n]+?)\$/g, (_, prefix, formula) => {
    const index = slots.push({ formula, display: false }) - 1;
    return `${prefix}<span class="math-slot" data-math-index="${index}"></span>`;
  });
  return { markdown: withInline, slots };
}

function sanitizeHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  const forbidden = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "TEXTAREA", "BUTTON", "META", "LINK"]);
  template.content.querySelectorAll("*").forEach((node) => {
    if (forbidden.has(node.tagName)) {
      node.remove();
      return;
    }
    [...node.attributes].forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || name === "style") node.removeAttribute(attribute.name);
      if (name === "href" && !/^(https?:|mailto:|#)/i.test(attribute.value)) node.removeAttribute(attribute.name);
    });
  });
  return template.innerHTML;
}

function enhanceCallouts(target) {
  target.querySelectorAll("blockquote").forEach((quote) => {
    const firstParagraph = quote.querySelector(":scope > p");
    if (!firstParagraph) return;
    const walker = document.createTreeWalker(firstParagraph, NodeFilter.SHOW_TEXT);
    const markerNode = walker.nextNode();
    const match = markerNode?.nodeValue?.match(/^\s*\[!(SUMMARY|NOTE|TIP|WARNING|EXAMPLE|QUESTION|SUCCESS)\](?:[ \t]+([^\n]*))?/i);
    if (!match) return;
    const type = match[1].toLowerCase();
    const config = CALLOUT_TYPES[type];
    markerNode.nodeValue = markerNode.nodeValue.slice(match[0].length);
    const nextNode = markerNode.nextSibling;
    if (!markerNode.nodeValue.trim()) markerNode.remove();
    if (nextNode?.nodeName === "BR") nextNode.remove();
    const title = document.createElement("div");
    title.className = "callout-title";
    title.dataset.icon = config.icon;
    title.textContent = match[2]?.trim() || config.label;
    quote.classList.add("callout", `callout-${type}`);
    quote.prepend(title);
    if (!firstParagraph.textContent.trim() && !firstParagraph.children.length) firstParagraph.remove();
  });
}

function renderMarkdown(markdown, target) {
  const { markdown: prepared, slots } = prepareMath(markdown);
  const rendered = window.marked?.parse(prepared, { gfm: true, breaks: true }) ?? `<p>${escapeHtml(markdown)}</p>`;
  target.innerHTML = sanitizeHtml(rendered);
  enhanceCallouts(target);

  target.querySelectorAll(".math-slot").forEach((slot) => {
    const item = slots[Number(slot.dataset.mathIndex)];
    if (!item || !window.katex) return;
    try {
      window.katex.render(item.formula.trim(), slot, { displayMode: item.display, throwOnError: false, strict: false });
    } catch {
      slot.textContent = item.display ? `$$${item.formula}$$` : `$${item.formula}$`;
    }
  });

  target.querySelectorAll("pre > code").forEach((code) => {
    if (window.hljs) window.hljs.highlightElement(code);
    const pre = code.parentElement;
    if (pre.parentElement?.classList.contains("code-wrap")) return;
    const wrap = document.createElement("div");
    wrap.className = "code-wrap";
    pre.replaceWith(wrap);
    wrap.append(pre);
    const language = [...code.classList].find((item) => item.startsWith("language-"))?.replace("language-", "");
    const label = document.createElement("span");
    label.className = "code-label";
    label.textContent = language || "code";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "copy-code";
    copy.textContent = "копировать";
    copy.addEventListener("click", async () => {
      await navigator.clipboard.writeText(code.textContent);
      copy.textContent = "готово";
      setTimeout(() => (copy.textContent = "копировать"), 1200);
    });
    wrap.append(label, copy);
  });

  target.querySelectorAll("a").forEach((link) => {
    link.target = "_blank";
    link.rel = "noreferrer";
  });
}

function selectMode(mode) {
  appState.mode = mode;
  document.querySelectorAll(".mode-button").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  const config = MODES[mode];
  elements.modeTitle.textContent = config.title;
  elements.input.placeholder = config.placeholder;
  elements.sidebar.classList.remove("open");
}

function ensureMessageList() {
  if (appState.messagesStarted) return document.querySelector(".message-list");
  elements.welcome.classList.add("hidden");
  const list = document.createElement("div");
  list.className = "message-list";
  elements.conversation.append(list);
  appState.messagesStarted = true;
  return list;
}

function addUserMessage(text) {
  const list = ensureMessageList();
  const article = document.createElement("article");
  article.className = "message user";
  article.innerHTML = `<div class="message-avatar">ВЫ</div><div><p class="message-meta">Вы</p><div class="message-content"></div></div>`;
  article.querySelector(".message-content").textContent = text;
  list.append(article);
  return article;
}

function addAssistantMessage() {
  const list = ensureMessageList();
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = `<div class="message-avatar">ML</div><div><p class="message-meta">${escapeHtml(MODES[appState.mode].label)}</p><div class="message-content"><div class="thinking-indicator"><span></span><span></span><span></span></div></div><div class="message-actions"></div><div class="message-sources"></div></div>`;
  list.append(article);
  return article;
}

function renderSources(container, sources) {
  if (!sources?.length) return;
  const details = document.createElement("details");
  details.className = "sources";
  const summary = document.createElement("summary");
  summary.textContent = `Источники · ${sources.length}`;
  const list = document.createElement("div");
  list.className = "source-list";
  sources.forEach((source) => {
    const item = document.createElement("div");
    item.className = "source-item";
    const title = document.createElement("strong");
    title.textContent = `${source.title} · ${source.heading}`;
    const excerpt = document.createElement("p");
    excerpt.textContent = source.excerpt;
    const path = document.createElement("small");
    path.textContent = source.file_path;
    item.append(title, excerpt, path);
    list.append(item);
  });
  details.append(summary, list);
  container.append(details);
}

function addAnswerActions(article, rawAnswer, validation) {
  const actions = article.querySelector(".message-actions");
  if (!rawAnswer) return;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "copy-answer";
  copy.textContent = "Копировать весь ответ";
  copy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(rawAnswer);
    copy.textContent = "Скопировано";
    setTimeout(() => (copy.textContent = "Копировать весь ответ"), 1200);
  });
  actions.append(copy);

  if (validation?.found_python) {
    const badge = document.createElement("span");
    badge.className = `validation-badge ${validation.syntax_valid ? "ok" : "warning"}`;
    badge.textContent = validation.syntax_valid ? "Python: синтаксис проверен" : "Python: найдена синтаксическая ошибка";
    actions.append(badge);
  }
}

function addWarning(article, message) {
  const warning = document.createElement("div");
  warning.className = "generation-warning";
  warning.textContent = message;
  article.querySelector(".message-actions").before(warning);
}

function scrollToBottom() {
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || appState.sending) return;
  if (!appState.status?.configured && appState.mode !== "code_builder") {
    openSettings();
    toast("Сначала выберите Obsidian vault.");
    return;
  }

  appState.sending = true;
  elements.send.disabled = true;
  addUserMessage(message);
  const assistant = addAssistantMessage();
  const content = assistant.querySelector(".message-content");
  const sourceContainer = assistant.querySelector(".message-sources");
  elements.input.value = "";
  resizeInput();
  scrollToBottom();

  let answer = "";
  let sources = [];
  let validation = null;
  const warnings = [];
  let renderQueued = false;
  const scheduleRender = () => {
    if (renderQueued) return;
    renderQueued = true;
    requestAnimationFrame(() => {
      renderMarkdown(answer, content);
      renderQueued = false;
      scrollToBottom();
    });
  };

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: appState.sessionId, message, mode: appState.mode }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "sources") sources = event.sources;
        if (event.type === "token") {
          answer += event.content;
          scheduleRender();
        }
        if (event.type === "thinking" && !answer) {
          content.innerHTML = `<div class="thinking-indicator"><span></span><span></span><span></span></div>`;
        }
        if (event.type === "validation") validation = event;
        if (event.type === "warning") warnings.push(event.message);
        if (event.type === "error") throw new Error(event.message);
      }
      if (done) break;
    }
    renderMarkdown(answer || "Ответ не получен.", content);
    warnings.forEach((warning) => addWarning(assistant, warning));
    addAnswerActions(assistant, answer, validation);
    renderSources(sourceContainer, sources);
  } catch (error) {
    content.replaceChildren();
    const card = document.createElement("div");
    card.className = "error-card";
    card.textContent = error.message;
    content.append(card);
  } finally {
    appState.sending = false;
    elements.send.disabled = false;
    scrollToBottom();
    elements.input.focus();
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
}

function resetChat() {
  fetch("/api/session/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: appState.sessionId }) }).catch(() => {});
  appState.sessionId = crypto.randomUUID();
  appState.messagesStarted = false;
  document.querySelector(".message-list")?.remove();
  elements.welcome.classList.remove("hidden");
  elements.input.value = "";
  resizeInput();
  elements.input.focus();
}

function openSettings() {
  elements.settingsDrawer.classList.add("open");
  elements.settingsDrawer.setAttribute("aria-hidden", "false");
  elements.backdrop.classList.remove("hidden");
}

function closeSettings() {
  elements.settingsDrawer.classList.remove("open");
  elements.settingsDrawer.setAttribute("aria-hidden", "true");
  elements.backdrop.classList.add("hidden");
}

function fillSettings(status) {
  const settings = status.settings;
  document.querySelector("#vault-path").value = settings.vault_path || "";
  document.querySelector("#chat-model").value = settings.chat_model;
  document.querySelector("#code-model").value = settings.code_model;
  document.querySelector("#embedding-model").value = settings.embedding_model;
  document.querySelector("#top-k").value = settings.top_k;
  document.querySelector("#temperature").value = settings.temperature;
  document.querySelector("#code-max-attempts").value = settings.code_max_attempts;
  document.querySelector("#ollama-url").value = settings.ollama_url;

  elements.installedModels.replaceChildren();
  status.ollama.models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    elements.installedModels.append(option);
  });

  elements.candidateList.replaceChildren();
  status.candidates.forEach((candidate) => {
    if (candidate === settings.vault_path) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "candidate-button";
    button.textContent = `Найден vault: ${candidate}`;
    button.title = candidate;
    button.addEventListener("click", () => (document.querySelector("#vault-path").value = candidate));
    elements.candidateList.append(button);
  });
}

function updateStatusUi(status) {
  appState.status = status;
  elements.vaultName.textContent = status.vault_name || "Vault не выбран";
  elements.vaultDot.className = `status-dot ${status.configured ? "ready" : "warning"}`;
  const { files, chunks } = status.index;
  elements.emptyStateMeta.textContent = status.configured ? `${status.vault_name} · ${chunks} ${pluralizeRu(chunks, "раздел", "раздела", "разделов")}` : "Vault не выбран";
  elements.indexSummary.textContent = status.indexing.running ? "Обновление индекса…" : chunks ? `${files} ${pluralizeRu(files, "заметка", "заметки", "заметок")} · ${chunks} ${pluralizeRu(chunks, "раздел", "раздела", "разделов")}` : "Индекс ещё не создан";
  elements.indexProgress.classList.toggle("hidden", !status.indexing.running);
  elements.reindex.disabled = status.indexing.running;

  const dot = elements.runtimeStatus.querySelector(".status-dot");
  const label = elements.runtimeStatus.querySelector("span:last-child");
  if (!status.ollama.available) {
    dot.className = "status-dot warning";
    label.textContent = "Ollama не запущена";
  } else if (!status.ollama.chat_model_ready) {
    dot.className = "status-dot warning";
    label.textContent = "Нужна модель ответа";
  } else {
    dot.className = "status-dot ready";
    label.textContent = status.settings.chat_model;
  }
  elements.setupNote.classList.toggle("hidden", status.ollama.chat_model_ready && status.ollama.code_model_ready && status.ollama.embedding_model_ready);
  fillSettings(status);
  if (status.indexing.error) toast(`Ошибка индексации: ${status.indexing.error}`);
}

async function fetchStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    updateStatusUi(await response.json());
  } catch {
    elements.runtimeStatus.querySelector(".status-dot").className = "status-dot warning";
    elements.runtimeStatus.querySelector("span:last-child").textContent = "Backend недоступен";
  }
}

async function requestReindex(force = false) {
  const response = await fetch("/api/reindex", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ force }) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Не удалось запустить reindex.");
  toast(force ? "Запущена полная переиндексация." : "Проверяю изменённые заметки.");
  await fetchStatus();
}

document.querySelectorAll(".mode-button").forEach((button) => button.addEventListener("click", () => selectMode(button.dataset.mode)));
elements.composer.addEventListener("submit", (event) => { event.preventDefault(); sendMessage(elements.input.value); });
elements.input.addEventListener("input", resizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(elements.input.value); }
});
elements.newChat.addEventListener("click", resetChat);
elements.settingsButton.addEventListener("click", openSettings);
elements.closeSettings.addEventListener("click", closeSettings);
elements.backdrop.addEventListener("click", () => { closeSettings(); elements.sidebar.classList.remove("open"); });
elements.mobileMenu.addEventListener("click", () => elements.sidebar.classList.toggle("open"));
elements.reindex.addEventListener("click", () => requestReindex(false).catch((error) => toast(error.message)));
elements.fullReindex.addEventListener("click", () => requestReindex(true).catch((error) => toast(error.message)));

elements.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    vault_path: document.querySelector("#vault-path").value.trim(),
    chat_model: document.querySelector("#chat-model").value.trim(),
    code_model: document.querySelector("#code-model").value.trim(),
    embedding_model: document.querySelector("#embedding-model").value.trim(),
    top_k: Number(document.querySelector("#top-k").value),
    temperature: Number(document.querySelector("#temperature").value),
    code_max_attempts: Number(document.querySelector("#code-max-attempts").value),
    ollama_url: document.querySelector("#ollama-url").value.trim(),
  };
  try {
    const response = await fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Не удалось сохранить.");
    closeSettings();
    toast("Настройки сохранены.");
    await fetchStatus();
  } catch (error) {
    toast(error.message);
  }
});

selectMode("chat");
resizeInput();
fetchStatus();
setInterval(fetchStatus, 6000);
