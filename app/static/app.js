const MODES = {
  chat: {
    label: "Chat",
    title: "Chat",
    placeholder: "Спросите о ML, Python, алгоритмах или коде…",
  },
  tutor: {
    label: "Tutor",
    title: "Tutor",
    placeholder: "Тема или вопрос для разбора…",
  },
  interviewer: {
    label: "Interviewer",
    title: "Interviewer",
    placeholder: "Укажите тему собеседования…",
  },
  practice: {
    label: "Practice",
    title: "Algorithm Practice",
    placeholder: "Тема, уровень или ваша попытка решения…",
  },
  code: {
    label: "Templates",
    title: "Code Templates",
    placeholder: "Какую ML-идею показать компактным шаблоном?",
  },
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

const LEARNING_AXES = [
  { id: "recall", short: "R", label: "Recall" },
  { id: "explain", short: "E", label: "Explain" },
  { id: "apply", short: "A", label: "Apply" },
  { id: "diagnose", short: "D", label: "Diagnose" },
];

const LEVEL_LABELS = {
  unseen: "нет evidence",
  needs_work: "нужно разобрать",
  developing: "формируется",
  reliable: "надёжно",
  strong: "сильно",
};

const EVIDENCE_LABELS = {
  deterministic: "автопроверка",
  rubric: "проверка по рубрике",
  agent: "наблюдение агента",
  self_report: "самооценка",
};

const appState = {
  mode: "chat",
  view: "chat",
  sessionId: crypto.randomUUID(),
  sending: false,
  status: null,
  messagesStarted: false,
  followOutput: true,
  activeSkillId: null,
  activeSkillTitle: "",
  learningOverview: null,
  selectedSkillId: null,
  lastReview: null,
};

const elements = {
  conversation: document.querySelector("#conversation"),
  welcome: document.querySelector("#welcome"),
  emptyStateMeta: document.querySelector("#empty-state-meta"),
  modeTitle: document.querySelector("#mode-title"),
  learningButton: document.querySelector("#learning-button"),
  learningBadge: document.querySelector("#learning-nav-badge"),
  learningView: document.querySelector("#learning-view"),
  learningStats: document.querySelector("#learning-stats"),
  learningError: document.querySelector("#learning-error"),
  learningRefresh: document.querySelector("#learning-refresh"),
  roadmapList: document.querySelector("#roadmap-list"),
  roadmapSources: document.querySelector("#roadmap-sources"),
  roadmapSourceList: document.querySelector("#roadmap-source-list"),
  skillPanel: document.querySelector("#skill-panel"),
  composer: document.querySelector("#composer"),
  composerWrap: document.querySelector("#composer-wrap"),
  composerHint: document.querySelector("#composer-hint"),
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
  jumpToLatest: document.querySelector("#jump-to-latest"),
};

function toast(message) {
  const item = document.createElement("div");
  item.className = "toast";
  item.textContent = message;
  elements.toastRegion.append(item);
  setTimeout(() => item.remove(), 4200);
}

function escapeHtml(value) {
  return value
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
  const withInline = blockReplaced.replace(
    /(^|[^\\$])\$([^$\n]+?)\$/g,
    (_, prefix, formula) => {
      const index = slots.push({ formula, display: false }) - 1;
      return `${prefix}<span class="math-slot" data-math-index="${index}"></span>`;
    },
  );
  return { markdown: withInline, slots };
}

function sanitizeHtml(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  const forbidden = new Set([
    "SCRIPT",
    "STYLE",
    "IFRAME",
    "OBJECT",
    "EMBED",
    "FORM",
    "INPUT",
    "TEXTAREA",
    "BUTTON",
    "META",
    "LINK",
  ]);
  template.content.querySelectorAll("*").forEach((node) => {
    if (forbidden.has(node.tagName)) {
      node.remove();
      return;
    }
    [...node.attributes].forEach((attribute) => {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || name === "style") {
        node.removeAttribute(attribute.name);
      }
      if (name === "href" && !/^(https?:|mailto:|#)/i.test(attribute.value)) {
        node.removeAttribute(attribute.name);
      }
    });
  });
  return template.innerHTML;
}

function wrapLooseCallouts(target) {
  const markerPattern =
    /^\s*\[!(SUMMARY|NOTE|TIP|WARNING|EXAMPLE|QUESTION|SUCCESS)\](?:\s+|$)/i;
  target.querySelectorAll("p").forEach((paragraph) => {
    if (paragraph.closest("blockquote")) return;
    if (!markerPattern.test(paragraph.textContent)) return;

    const markerOnly = paragraph.textContent.replace(markerPattern, "").trim() === "";
    const quote = document.createElement("blockquote");
    paragraph.replaceWith(quote);
    quote.append(paragraph);

    const following = quote.nextElementSibling;
    if (markerOnly && following?.tagName === "P") quote.append(following);
  });
}

function enhanceCallouts(target) {
  target.querySelectorAll("blockquote").forEach((quote) => {
    const firstParagraph = quote.querySelector(":scope > p");
    if (!firstParagraph) return;

    const walker = document.createTreeWalker(firstParagraph, NodeFilter.SHOW_TEXT);
    const markerNode = walker.nextNode();
    const match = markerNode?.nodeValue?.match(
      /^\s*\[!(SUMMARY|NOTE|TIP|WARNING|EXAMPLE|QUESTION|SUCCESS)\](?:[ \t]+([^\n]*))?/i,
    );
    if (!match) return;

    const type = match[1].toLowerCase();
    const config = CALLOUT_TYPES[type];
    const explicitTitle = match[2]?.trim();
    markerNode.nodeValue = markerNode.nodeValue.slice(match[0].length);

    const nextNode = markerNode.nextSibling;
    if (!markerNode.nodeValue.trim()) markerNode.remove();
    if (nextNode?.nodeName === "BR") nextNode.remove();
    firstParagraph
      .querySelectorAll("strong:empty, em:empty")
      .forEach((node) => node.remove());

    const title = document.createElement("div");
    title.className = "callout-title";
    title.dataset.icon = config.icon;
    title.textContent = explicitTitle || config.label;

    quote.classList.add("callout", `callout-${type}`);
    quote.prepend(title);

    if (!firstParagraph.textContent.trim() && !firstParagraph.children.length) {
      firstParagraph.remove();
    }
  });
}

function renderMarkdown(markdown, target) {
  const { markdown: prepared, slots } = prepareMath(markdown);
  const rendered =
    window.marked?.parse(prepared, { gfm: true, breaks: true }) ??
    `<p>${escapeHtml(markdown)}</p>`;
  target.innerHTML = sanitizeHtml(rendered);
  wrapLooseCallouts(target);
  enhanceCallouts(target);

  target.querySelectorAll(".math-slot").forEach((slot) => {
    const item = slots[Number(slot.dataset.mathIndex)];
    if (!item || !window.katex) return;
    try {
      window.katex.render(item.formula.trim(), slot, {
        displayMode: item.display,
        throwOnError: false,
        strict: false,
      });
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
    const language = [...code.classList]
      .find((item) => item.startsWith("language-"))
      ?.replace("language-", "");
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
  appState.view = "chat";
  if (mode !== "tutor") {
    appState.activeSkillId = null;
    appState.activeSkillTitle = "";
  }
  updateComposerContext();
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  elements.learningButton.classList.remove("active");
  elements.learningView.classList.add("hidden");
  elements.conversation.classList.remove("hidden");
  elements.composerWrap.classList.remove("hidden");
  const config = MODES[mode];
  elements.modeTitle.textContent = config.title;
  elements.input.placeholder = config.placeholder;
  elements.sidebar.classList.remove("open");
}

function showLearning() {
  appState.view = "learning";
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.classList.remove("active");
  });
  elements.learningButton.classList.add("active");
  elements.conversation.classList.add("hidden");
  elements.composerWrap.classList.add("hidden");
  elements.jumpToLatest.classList.add("hidden");
  elements.learningView.classList.remove("hidden");
  elements.modeTitle.textContent = "Learning";
  elements.sidebar.classList.remove("open");
  loadLearningOverview(!appState.learningOverview);
}

function updateComposerContext() {
  elements.composerHint.textContent = appState.activeSkillId
    ? `Учебный контекст: ${appState.activeSkillTitle}`
    : "Enter · Shift+Enter для новой строки";
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function skillStatus(skill) {
  if (skill.due) return "Пора повторить";
  if (skill.active_errors?.length) return "Есть повторяющийся пробел";
  if (!skill.evidence_count) return "Не начато";
  return `${skill.evidence_count} ${pluralizeRu(skill.evidence_count, "наблюдение", "наблюдения", "наблюдений")}`;
}

function renderLearningOverview(payload) {
  appState.learningOverview = payload;
  elements.learningError.classList.toggle("hidden", payload.available);
  if (!payload.available) {
    elements.learningError.textContent = payload.error || "Учебный каталог недоступен.";
    elements.roadmapList.innerHTML = `
      <div class="learning-loading">Добавьте валидный _meta/LEARNING_CATALOG.md в vault.</div>
    `;
    elements.learningStats.replaceChildren();
    elements.roadmapSources.classList.add("hidden");
    return;
  }

  elements.learningError.classList.add("hidden");
  const summary = payload.summary;
  elements.learningStats.innerHTML = `
    <div class="learning-stat"><strong>${summary.skills_started}</strong><small>начато из ${summary.skills_total}</small></div>
    <div class="learning-stat"><strong>${summary.due_count}</strong><small>повторить</small></div>
    <div class="learning-stat"><strong>${summary.weak_count}</strong><small>проверить</small></div>
  `;

  if (summary.due_count) {
    elements.learningBadge.textContent = summary.due_count;
    elements.learningBadge.classList.remove("hidden");
  } else {
    elements.learningBadge.classList.add("hidden");
  }

  const skills = new Map(payload.skills.map((skill) => [skill.id, skill]));
  elements.roadmapList.innerHTML = payload.stages
    .map((stage) => {
      const cards = stage.skill_ids
        .map((skillId) => skills.get(skillId))
        .filter(Boolean)
        .map((skill) => {
          const dots = LEARNING_AXES.map((axis) => {
            const level = skill.axes[axis.id]?.level || "unseen";
            return `<span class="axis-dot ${level}" title="${axis.label}: ${LEVEL_LABELS[level]}">${axis.short}</span>`;
          }).join("");
          const active = skill.id === appState.selectedSkillId ? " active" : "";
          return `
            <button class="skill-card-button${active}" data-skill-id="${escapeHtml(skill.id)}" type="button">
              <span>
                <span class="skill-card-title">${escapeHtml(skill.title)}</span>
                <span class="skill-card-status">${escapeHtml(skillStatus(skill))}</span>
              </span>
              <span class="axis-dots" aria-label="Грани навыка">${dots}</span>
            </button>
          `;
        })
        .join("");
      return `
        <section class="roadmap-stage">
          <header class="roadmap-stage-header">
            <strong>${escapeHtml(stage.title)}</strong>
            <p>${escapeHtml(stage.description)}</p>
          </header>
          <div class="stage-skills">${cards}</div>
        </section>
      `;
    })
    .join("");

  elements.roadmapList.querySelectorAll("[data-skill-id]").forEach((button) => {
    button.addEventListener("click", () => loadLearningSkill(button.dataset.skillId));
  });

  elements.roadmapSourceList.innerHTML = payload.sources
    .map(
      (source) => `
        <div class="roadmap-source-item">
          <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.title)}</a>
          <small>${escapeHtml(source.organization)} · ${escapeHtml(source.audience)}</small>
        </div>
      `,
    )
    .join("");
  elements.roadmapSources.classList.toggle("hidden", payload.sources.length === 0);
}

async function loadLearningOverview(force = false) {
  if (appState.learningOverview && !force) {
    renderLearningOverview(appState.learningOverview);
    return;
  }
  elements.learningRefresh.disabled = true;
  try {
    renderLearningOverview(await apiJson("/api/learning/overview"));
  } catch (error) {
    renderLearningOverview({ available: false, error: error.message });
  } finally {
    elements.learningRefresh.disabled = false;
  }
}

function axisCards(profile) {
  return LEARNING_AXES.map((axis) => {
    const state = profile.axes[axis.id];
    const score = state.score === null ? "—" : `${Math.round(state.score * 100)}%`;
    return `
      <div class="axis-card ${state.level}">
        <b>${axis.label}</b>
        <span>${score}</span>
        <small>${escapeHtml(LEVEL_LABELS[state.level])} · ${state.evidence_count}</small>
      </div>
    `;
  }).join("");
}

function evidenceHtml(events) {
  if (!events.length) {
    return `<div class="evidence-empty">Evidence пока нет. Обычный чат сюда ничего не записывает.</div>`;
  }
  return events
    .map((event) => {
      const dismissed = event.dismissed_at ? " dismissed" : "";
      const action = event.dismissed_at ? "Вернуть" : "Не учитывать";
      const date = new Date(event.created_at).toLocaleDateString("ru-RU", {
        day: "2-digit",
        month: "short",
      });
      return `
        <div class="evidence-item${dismissed}">
          <div>
            <div class="evidence-meta">
              <span>${escapeHtml(EVIDENCE_LABELS[event.evidence_kind] || event.evidence_kind)}</span>
              <span>· ${escapeHtml(event.axis)}</span>
              <span>· ${Math.round(event.score * 100)}%</span>
              <span>· уверенность ${Math.round(event.confidence * 100)}%</span>
              <span>· ${date}</span>
            </div>
            ${event.note ? `<p>${escapeHtml(event.note)}</p>` : ""}
          </div>
          <button class="evidence-action" data-event-id="${event.id}" data-dismissed="${Boolean(event.dismissed_at)}" type="button">${action}</button>
        </div>
      `;
    })
    .join("");
}

function reviewResultHtml(review) {
  if (!review) return "";
  const criteria = review.criteria
    .map(
      (criterion) =>
        `<li><strong>${escapeHtml(criterion.id)}</strong>: ${Math.round(criterion.credit * 100)}%${criterion.comment ? ` — ${escapeHtml(criterion.comment)}` : ""}</li>`,
    )
    .join("");
  return `
    <div class="diagnostic-result">
      <strong>Проверка по рубрике · ${Math.round(review.score * 100)}%</strong>
      <div>${escapeHtml(review.feedback)}</div>
      <ul>${criteria}</ul>
    </div>
  `;
}

function renderSkillDetail(payload) {
  const { skill, profile, evidence } = payload;
  const diagnostic = skill.diagnostics[0];
  const notes = skill.note_paths
    .map((path) => escapeHtml(path.split("/").pop().replace(/\.md$/i, "")))
    .join(" · ");
  const activeErrors = profile.active_errors.length
    ? profile.active_errors.map((item) => escapeHtml(item.code)).join(", ")
    : "нет повторяющихся ошибок";
  const lastReview =
    appState.lastReview?.skillId === skill.id ? appState.lastReview.review : null;
  elements.skillPanel.innerHTML = `
    <header class="skill-detail-header">
      <span class="skill-detail-kicker">${escapeHtml(skill.stage_id)} · ${profile.evidence_count} evidence</span>
      <h3>${escapeHtml(skill.title)}</h3>
      <p>${escapeHtml(skill.description)}</p>
      <div class="skill-actions">
        <button class="learning-action primary" id="ask-tutor-for-skill" type="button">Разобрать с Tutor</button>
        <button class="learning-action" id="back-to-roadmap" type="button">К карте</button>
      </div>
    </header>

    <section class="skill-section">
      <h4>Что должно получаться</h4>
      <ul class="skill-outcomes">${skill.outcomes.map((outcome) => `<li>${escapeHtml(outcome)}</li>`).join("")}</ul>
      <div class="skill-note-paths">В vault: ${notes}</div>
    </section>

    <section class="skill-section">
      <h4>Четыре грани</h4>
      <div class="axis-grid">${axisCards(profile)}</div>
      <div class="skill-note-paths">Повторяющиеся наблюдения: ${activeErrors}</div>
    </section>

    <section class="skill-section">
      <h4>Диагностика · ${escapeHtml(diagnostic.axis)}</h4>
      <div class="diagnostic-card">
        <p>${escapeHtml(diagnostic.prompt)}</p>
        <details class="diagnostic-rubric">
          <summary>Показать критерии проверки</summary>
          <ul>${diagnostic.rubric.map((item) => `<li>${escapeHtml(item.description)} · ${Math.round(item.weight * 100)}%</li>`).join("")}</ul>
        </details>
        <textarea id="diagnostic-answer" maxlength="20000" placeholder="Сформулируйте ответ своими словами…"></textarea>
        <div class="diagnostic-footer">
          <small>Проверяет локальная модель. Запись имеет среднюю уверенность и её можно удалить.</small>
          <button class="learning-action primary" id="submit-diagnostic" type="button">Проверить ответ</button>
        </div>
        <div id="diagnostic-result">${reviewResultHtml(lastReview)}</div>
      </div>
    </section>

    <section class="skill-section">
      <h4>Быстрая самооценка · ${escapeHtml(diagnostic.axis)}</h4>
      <div class="self-rating">
        <button class="self-rating-button" data-self-score="0.25" type="button">Пока не понимаю</button>
        <button class="self-rating-button" data-self-score="0.6" type="button">Понимаю частично</button>
        <button class="self-rating-button" data-self-score="0.85" type="button">Могу объяснить</button>
      </div>
    </section>

    <section class="skill-section">
      <h4>Из чего рассчитан прогресс</h4>
      <div class="evidence-list">${evidenceHtml(evidence)}</div>
    </section>
  `;

  document.querySelectorAll(".skill-card-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.skillId === skill.id);
  });
  elements.skillPanel.querySelector("#ask-tutor-for-skill").addEventListener("click", () => {
    startTutorForSkill(skill);
  });
  elements.skillPanel.querySelector("#back-to-roadmap").addEventListener("click", () => {
    appState.selectedSkillId = null;
    elements.skillPanel.innerHTML = `
      <div class="skill-panel-empty"><span>ML</span><h3>Выберите навык</h3><p>Прогресс строится только по видимым evidence.</p></div>
    `;
    renderLearningOverview(appState.learningOverview);
  });
  elements.skillPanel.querySelector("#submit-diagnostic").addEventListener("click", () => {
    submitDiagnostic(skill, diagnostic);
  });
  elements.skillPanel.querySelectorAll("[data-self-score]").forEach((button) => {
    button.addEventListener("click", () => {
      submitSelfReport(skill, diagnostic.axis, Number(button.dataset.selfScore), button);
    });
  });
  elements.skillPanel.querySelectorAll("[data-event-id]").forEach((button) => {
    button.addEventListener("click", () => toggleEvidence(button));
  });
}

async function loadLearningSkill(skillId) {
  appState.selectedSkillId = skillId;
  elements.skillPanel.innerHTML = `<div class="learning-loading">Загружаю навык…</div>`;
  if (appState.learningOverview?.available) renderLearningOverview(appState.learningOverview);
  try {
    renderSkillDetail(await apiJson(`/api/learning/skills/${encodeURIComponent(skillId)}`));
  } catch (error) {
    elements.skillPanel.innerHTML = `<div class="learning-error">${escapeHtml(error.message)}</div>`;
  }
}

async function submitDiagnostic(skill, diagnostic) {
  const answer = elements.skillPanel.querySelector("#diagnostic-answer").value.trim();
  const button = elements.skillPanel.querySelector("#submit-diagnostic");
  const result = elements.skillPanel.querySelector("#diagnostic-result");
  if (!answer) {
    result.innerHTML = `<div class="diagnostic-result">Сначала напишите ответ своими словами.</div>`;
    return;
  }
  button.disabled = true;
  button.textContent = "Проверяю…";
  try {
    const payload = await apiJson("/api/learning/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skill_id: skill.id,
        diagnostic_id: diagnostic.id,
        answer,
      }),
    });
    appState.lastReview = { skillId: skill.id, review: payload.review };
    await loadLearningOverview(true);
    await loadLearningSkill(skill.id);
  } catch (error) {
    result.innerHTML = `<div class="learning-error">${escapeHtml(error.message)}</div>`;
    button.disabled = false;
    button.textContent = "Проверить ответ";
  }
}

async function submitSelfReport(skill, axis, score, button) {
  button.disabled = true;
  try {
    await apiJson("/api/learning/evidence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skill_id: skill.id,
        axis,
        score,
        activity_id: "dashboard-self-report",
        note: "Явная самооценка из Learning dashboard.",
      }),
    });
    toast("Самооценка добавлена как evidence с низкой уверенностью.");
    await loadLearningOverview(true);
    await loadLearningSkill(skill.id);
  } catch (error) {
    toast(error.message);
    button.disabled = false;
  }
}

async function toggleEvidence(button) {
  const eventId = button.dataset.eventId;
  const isDismissed = button.dataset.dismissed === "true";
  button.disabled = true;
  try {
    const payload = await apiJson(`/api/learning/evidence/${eventId}/dismiss`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dismissed: !isDismissed }),
    });
    await loadLearningOverview(true);
    await loadLearningSkill(payload.evidence.skill_id);
  } catch (error) {
    toast(error.message);
    button.disabled = false;
  }
}

function startTutorForSkill(skill) {
  appState.activeSkillId = skill.id;
  appState.activeSkillTitle = skill.title;
  updateComposerContext();
  selectMode("tutor");
  elements.input.value = `Помоги мне разобраться с навыком «${skill.title}». Начни с короткой проверки моей текущей модели понимания, затем объясняй только обнаруженный пробел.`;
  resizeInput();
  elements.input.focus();
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
  article.innerHTML = `
    <div class="message-avatar">ВЫ</div>
    <div>
      <p class="message-meta">Вы</p>
      <div class="message-content"></div>
    </div>
  `;
  article.querySelector(".message-content").textContent = text;
  list.append(article);
  return article;
}

function addAssistantMessage() {
  const list = ensureMessageList();
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = `
    <div class="message-avatar">ML</div>
    <div>
      <p class="message-meta">${escapeHtml(MODES[appState.mode].label)}</p>
      <div class="message-content">
        <div class="thinking-indicator"><span></span><span></span><span></span></div>
      </div>
      <div class="message-sources"></div>
    </div>
  `;
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

function isNearConversationBottom() {
  const remaining =
    elements.conversation.scrollHeight -
    elements.conversation.scrollTop -
    elements.conversation.clientHeight;
  return remaining <= 96;
}

function updateJumpToLatest() {
  const shouldShow = appState.messagesStarted && !isNearConversationBottom();
  elements.jumpToLatest.classList.toggle("hidden", !shouldShow);
}

function scrollToBottom(force = false) {
  if (force) appState.followOutput = true;
  if (!appState.followOutput) {
    updateJumpToLatest();
    return;
  }
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
  elements.jumpToLatest.classList.add("hidden");
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || appState.sending) return;
  if (!appState.status?.configured) {
    openSettings();
    toast("Сначала выберите Obsidian vault.");
    return;
  }

  appState.sending = true;
  appState.followOutput = true;
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
  let renderTimer = null;
  let lastRenderedAt = 0;
  const renderAnswer = () => {
    renderMarkdown(answer, content);
    lastRenderedAt = Date.now();
    scrollToBottom();
  };
  const scheduleRender = () => {
    if (renderTimer !== null) return;
    const delay = Math.max(0, 80 - (Date.now() - lastRenderedAt));
    renderTimer = setTimeout(() => {
      renderTimer = null;
      renderAnswer();
    }, delay);
  };

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: appState.sessionId,
        message,
        mode: appState.mode,
        skill_id: appState.activeSkillId,
      }),
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
        if (event.type === "error") throw new Error(event.message);
      }
      if (done) break;
    }
    if (renderTimer !== null) clearTimeout(renderTimer);
    renderTimer = null;
    renderMarkdown(answer || "Ответ не получен.", content);
    renderSources(sourceContainer, sources);
  } catch (error) {
    content.innerHTML = `<div class="error-card">${escapeHtml(error.message)}</div>`;
  } finally {
    if (renderTimer !== null) clearTimeout(renderTimer);
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
  fetch("/api/session/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: appState.sessionId }),
  }).catch(() => {});
  appState.sessionId = crypto.randomUUID();
  appState.messagesStarted = false;
  appState.followOutput = true;
  appState.activeSkillId = null;
  appState.activeSkillTitle = "";
  updateComposerContext();
  selectMode("chat");
  document.querySelector(".message-list")?.remove();
  elements.welcome.classList.remove("hidden");
  elements.jumpToLatest.classList.add("hidden");
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
  document.querySelector("#embedding-model").value = settings.embedding_model;
  document.querySelector("#top-k").value = settings.top_k;
  document.querySelector("#temperature").value = settings.temperature;
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
    button.addEventListener("click", () => {
      document.querySelector("#vault-path").value = candidate;
    });
    elements.candidateList.append(button);
  });
}

function updateStatusUi(status) {
  const previousVault = appState.status?.vault_path;
  appState.status = status;
  if (previousVault && previousVault !== status.vault_path) {
    appState.learningOverview = null;
    appState.selectedSkillId = null;
  }
  elements.vaultName.textContent = status.vault_name || "Vault не выбран";
  elements.vaultDot.className = `status-dot ${status.configured ? "ready" : "warning"}`;
  const { files, chunks } = status.index;
  const sectionLabel = pluralizeRu(chunks, "раздел", "раздела", "разделов");
  const noteLabel = pluralizeRu(files, "заметка", "заметки", "заметок");
  elements.emptyStateMeta.textContent = status.configured
    ? `${status.vault_name} · ${chunks} ${sectionLabel}`
    : "Vault не выбран";
  elements.indexSummary.textContent = status.indexing.running
    ? "Обновление индекса…"
    : chunks
      ? `${files} ${noteLabel} · ${chunks} ${sectionLabel}`
      : "Индекс ещё не создан";
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
  elements.setupNote.classList.toggle(
    "hidden",
    status.ollama.chat_model_ready && status.ollama.embedding_model_ready,
  );
  fillSettings(status);

  if (status.indexing.error) toast(`Ошибка индексации: ${status.indexing.error}`);
}

async function fetchStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const status = await response.json();
    updateStatusUi(status);
    if (!status.configured) openSettings();
  } catch (error) {
    elements.runtimeStatus.querySelector(".status-dot").className = "status-dot warning";
    elements.runtimeStatus.querySelector("span:last-child").textContent =
      "Backend недоступен";
  }
}

async function requestReindex(force = false) {
  const response = await fetch("/api/reindex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Не удалось запустить reindex.");
  toast(force ? "Запущена полная переиндексация." : "Проверяю изменённые заметки.");
  await fetchStatus();
}

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => selectMode(button.dataset.mode));
});
elements.learningButton.addEventListener("click", showLearning);
elements.learningRefresh.addEventListener("click", () => loadLearningOverview(true));

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(elements.input.value);
});

elements.input.addEventListener("input", resizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(elements.input.value);
  }
});

elements.conversation.addEventListener(
  "scroll",
  () => {
    appState.followOutput = isNearConversationBottom();
    updateJumpToLatest();
  },
  { passive: true },
);
elements.jumpToLatest.addEventListener("click", () => scrollToBottom(true));

elements.newChat.addEventListener("click", resetChat);
elements.settingsButton.addEventListener("click", openSettings);
elements.closeSettings.addEventListener("click", closeSettings);
elements.backdrop.addEventListener("click", () => {
  closeSettings();
  elements.sidebar.classList.remove("open");
});
elements.mobileMenu.addEventListener("click", () => {
  elements.sidebar.classList.toggle("open");
});
elements.reindex.addEventListener("click", () => {
  requestReindex(false).catch((error) => toast(error.message));
});
elements.fullReindex.addEventListener("click", () => {
  requestReindex(true).catch((error) => toast(error.message));
});

elements.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    vault_path: document.querySelector("#vault-path").value.trim(),
    chat_model: document.querySelector("#chat-model").value.trim(),
    embedding_model: document.querySelector("#embedding-model").value.trim(),
    top_k: Number(document.querySelector("#top-k").value),
    temperature: Number(document.querySelector("#temperature").value),
    ollama_url: document.querySelector("#ollama-url").value.trim(),
  };
  try {
    const response = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Не удалось сохранить.");
    closeSettings();
    toast("Настройки сохранены.");
    appState.learningOverview = null;
    appState.selectedSkillId = null;
    await fetchStatus();
  } catch (error) {
    toast(error.message);
  }
});

selectMode("chat");
updateComposerContext();
resizeInput();
fetchStatus();
setInterval(fetchStatus, 12_000);
