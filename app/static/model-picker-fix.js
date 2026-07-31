(() => {
  const form = document.querySelector("#settings-form");
  const drawer = document.querySelector("#settings-drawer");
  const codeModelInput = document.querySelector("#code-model");
  const chatModelInput = document.querySelector("#chat-model");
  const embeddingModelInput = document.querySelector("#embedding-model");

  if (!form || !drawer || !codeModelInput) return;

  const modelInputs = [chatModelInput, codeModelInput, embeddingModelInput].filter(Boolean);
  let settingsDirty = false;
  let draftValues = {};

  function captureDraft() {
    draftValues = Object.fromEntries(modelInputs.map((input) => [input.id, input.value]));
  }

  function restoreDraft() {
    modelInputs.forEach((input) => {
      if (Object.hasOwn(draftValues, input.id)) input.value = draftValues[input.id];
    });
  }

  function markDirty() {
    settingsDirty = true;
    captureDraft();
  }

  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);

  const panel = document.createElement("section");
  panel.className = "installed-model-picker";
  panel.innerHTML = `
    <div class="installed-model-picker__header">
      <strong>Установленные модели Ollama</strong>
      <button type="button" class="installed-model-picker__refresh">Обновить</button>
    </div>
    <div class="installed-model-picker__list"></div>
    <small>Нажмите на модель, чтобы выбрать её для Code Builder.</small>
  `;
  codeModelInput.closest(".field")?.after(panel);

  const list = panel.querySelector(".installed-model-picker__list");
  const refreshButton = panel.querySelector(".installed-model-picker__refresh");

  function renderModels(models) {
    list.replaceChildren();
    const uniqueModels = [...new Set((models || []).filter(Boolean))].sort();

    if (!uniqueModels.length) {
      const empty = document.createElement("span");
      empty.className = "installed-model-picker__empty";
      empty.textContent = "Backend пока не получил список моделей от Ollama.";
      list.append(empty);
      return;
    }

    uniqueModels.forEach((model) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "installed-model-picker__model";
      button.textContent = model;
      button.classList.toggle("selected", codeModelInput.value === model);
      button.addEventListener("click", () => {
        codeModelInput.value = model;
        markDirty();
        list.querySelectorAll("button").forEach((item) => {
          item.classList.toggle("selected", item.textContent === model);
        });
      });
      list.append(button);
    });
  }

  const originalFillSettings = window.fillSettings;
  if (typeof originalFillSettings === "function") {
    window.fillSettings = function patchedFillSettings(status) {
      const preserveDraft = settingsDirty && drawer.classList.contains("open");
      if (preserveDraft) captureDraft();
      originalFillSettings(status);
      if (preserveDraft) restoreDraft();
      else captureDraft();
      renderModels(status?.ollama?.models || []);
    };
  }

  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    refreshButton.textContent = "Обновляю…";
    try {
      if (typeof window.fetchStatus === "function") await window.fetchStatus();
    } finally {
      refreshButton.disabled = false;
      refreshButton.textContent = "Обновить";
    }
  });

  const drawerObserver = new MutationObserver(() => {
    if (!drawer.classList.contains("open")) {
      settingsDirty = false;
      draftValues = {};
    }
  });
  drawerObserver.observe(drawer, { attributes: true, attributeFilter: ["class"] });

  const style = document.createElement("style");
  style.textContent = `
    .installed-model-picker {
      display: grid;
      gap: 9px;
      margin: -8px 0 18px;
      padding: 11px;
      border: 1px solid var(--line-soft);
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.42);
    }
    .installed-model-picker__header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .installed-model-picker__header strong {
      font-size: 10px;
    }
    .installed-model-picker__refresh,
    .installed-model-picker__model {
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--ink-muted);
      background: transparent;
      cursor: pointer;
      font: inherit;
    }
    .installed-model-picker__refresh {
      padding: 5px 8px;
      font-size: 9px;
    }
    .installed-model-picker__list {
      display: grid;
      gap: 6px;
      max-height: 170px;
      overflow-y: auto;
    }
    .installed-model-picker__model {
      padding: 8px 9px;
      overflow: hidden;
      font-size: 10px;
      text-align: left;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .installed-model-picker__model:hover,
    .installed-model-picker__model.selected {
      border-color: var(--green);
      color: var(--green);
      background: rgba(29, 111, 84, 0.06);
    }
    .installed-model-picker__empty,
    .installed-model-picker small {
      color: var(--ink-muted);
      font-size: 9px;
      line-height: 1.4;
    }
  `;
  document.head.append(style);

  captureDraft();
  if (typeof window.fetchStatus === "function") window.fetchStatus();
})();
