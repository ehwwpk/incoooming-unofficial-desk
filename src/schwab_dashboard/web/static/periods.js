const setText = (selector, value) => {
  document.querySelectorAll(selector).forEach((node) => {
    node.textContent = value;
  });
};

const setOptionalText = (selector, value, visible) => {
  document.querySelectorAll(selector).forEach((node) => {
    node.textContent = visible ? value : "";
    node.hidden = !visible;
  });
};

const setupPeriodConsole = () => {
  const consoleRoot = document.querySelector("[data-period-console]");
  const controlsRoot = document.querySelector("[data-period-controls]");
  if (!consoleRoot || !controlsRoot || consoleRoot.dataset.periodReady === "true") return;

  const periodButtons = [...controlsRoot.querySelectorAll("[data-period]")];
  const sheets = [...consoleRoot.querySelectorAll("[data-period-sheet]")];
  const windowCodes = { month: "4W", quarter: "QTR", ytd: "YTD", r365: "R365" };
  let selectedPeriod = "month";

  const updateActiveDesk = (sheet) => {
    if (!sheet) return;
    const key = sheet.dataset.periodSheet;
    setText("[data-active-window]", windowCodes[key] || sheet.dataset.windowLabel);
    setText("[data-active-range]", sheet.dataset.rangeLabel);
    setText("[data-active-option-label]", `OPTION CASH KEPT / ${sheet.dataset.windowLabel}`);
    setText("[data-active-option-cash]", sheet.dataset.optionCash);
    setText("[data-active-option-meta]", `${sheet.dataset.optionApr} annualized · after executed closing debits`);
    setText("[data-active-window-label]", sheet.dataset.windowLabel);
    setText("[data-active-dividend-cash]", sheet.dataset.dividends);
    setText("[data-active-total-label]", `TOTAL CASH RECEIVED / ${sheet.dataset.windowLabel}`);
    setText("[data-active-total-cash]", sheet.dataset.totalCash);
    setText("[data-active-total-meta]", `Option income plus dividends · ${sheet.dataset.totalApr} APR`);
    setText("[data-active-monthly-pace]", sheet.dataset.monthlyTotalAverage);
    const showMonthlyAverage = key === "r365";
    setOptionalText(
      "[data-active-option-average]",
      `1-MONTH AVG ${sheet.dataset.monthlyOptionAverage}`,
      showMonthlyAverage,
    );
    setOptionalText(
      "[data-active-total-average]",
      `1-MONTH AVG ${sheet.dataset.monthlyTotalAverage}`,
      showMonthlyAverage,
    );
    setText("[data-active-calls-contracts]", `${sheet.dataset.calls} / ${sheet.dataset.contracts}`);
    setText("[data-active-win-rate]", `${sheet.dataset.winRate} positive-cash completion rate`);
    setText("[data-active-capture-label]", `PREMIUM CAPTURE / ${sheet.dataset.windowLabel}`);
    setText("[data-active-capture-value]", sheet.dataset.capture);
    setText("[data-active-capture-meta]", `${sheet.dataset.buybackDrag} executed-debit drag`);
    document.querySelectorAll("[data-cash-series]").forEach((series) => {
      series.hidden = series.dataset.cashSeries !== key;
    });
    const activeSeries = document.querySelector(`[data-cash-series="${key}"]`);
    const grain = activeSeries?.dataset.seriesGrain || "CASH";
    setText("[data-cash-grain]", `${grain} · ${sheet.dataset.windowLabel}`);
    setText("[data-cash-footer]", `${grain} · EXECUTED CASH ONLY · MODEL THETA EXCLUDED`);
  };

  const updateUnderlyingCards = (activeSheetKey, windowLabel) => {
    document.querySelectorAll("[data-underlying-card]").forEach((card) => {
      const windowData = card.querySelector(`[data-name-window="${activeSheetKey}"]`);
      if (!windowData) return;
      const windowCode = windowCodes[activeSheetKey] || windowLabel;
      card.querySelector("[data-name-option-label]").textContent = `NET OPTION INCOME / ${windowLabel}`;
      card.querySelector("[data-name-option-cash]").textContent = windowData.dataset.optionCash;
      card.querySelector("[data-name-option-apr-label]").textContent = `OPTION INCOME APR / ${windowCode}`;
      card.querySelector("[data-name-option-apr]").textContent = windowData.dataset.optionApr;
      card.querySelector("[data-name-dividend-label]").textContent = `DIVIDENDS / ${windowCode}`;
      card.querySelectorAll("[data-name-dividends]").forEach((node) => {
        node.textContent = windowData.dataset.dividends;
      });
      card.querySelector("[data-name-capture-label]").textContent = `CAPTURE / ${windowCode}`;
      card.querySelector("[data-name-capture]").textContent = windowData.dataset.capture;
    });
  };

  const activate = () => {
    const activeSheetKey = selectedPeriod;
    const activeSheet = sheets.find((sheet) => sheet.dataset.periodSheet === activeSheetKey);
    sheets.forEach((sheet) => {
      sheet.hidden = sheet !== activeSheet;
    });
    periodButtons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.period === selectedPeriod));
    });
    updateActiveDesk(activeSheet);
    if (activeSheet) {
      updateUnderlyingCards(activeSheetKey, activeSheet.dataset.windowLabel);
    }
  };

  periodButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedPeriod = button.dataset.period;
      activate();
    });
  });
  document.addEventListener("keydown", (event) => {
    const tag = event.target?.tagName?.toLowerCase();
    if (["input", "textarea", "select"].includes(tag) || event.target?.isContentEditable) return;
    const periodShortcuts = { "1": "month", "2": "quarter", "3": "ytd", "4": "r365" };
    const annualShortcuts = { y: "ytd", r: "r365" };
    const sectionShortcuts = { F1: "portfolio", F2: "underlyings", F3: "income" };
    if (periodShortcuts[event.key]) {
      selectedPeriod = periodShortcuts[event.key];
      activate();
    } else if (annualShortcuts[event.key.toLowerCase()]) {
      selectedPeriod = annualShortcuts[event.key.toLowerCase()];
      activate();
    } else if (sectionShortcuts[event.key]) {
      event.preventDefault();
      document.getElementById(sectionShortcuts[event.key])?.scrollIntoView({ behavior: "smooth" });
    }
  });

  activate();
  consoleRoot.dataset.periodReady = "true";
};

const setupCommandJump = () => {
  const input = document.querySelector("[data-command-input]");
  if (!input || input.dataset.commandReady === "true") return;

  const sectionTargets = {
    desk: "portfolio",
    portfolio: "portfolio",
    names: "underlyings",
    stocks: "underlyings",
    income: "income",
    cash: "income",
    risk: "risk",
    records: "records",
    log: "records",
  };

  const jump = () => {
    const query = input.value.trim();
    if (!query) return;
    const normalized = query.toLowerCase();
    const normalizedSymbol = query.toUpperCase();
    const symbolTarget = Array.from(
      document.querySelectorAll("[data-underlying-card]"),
    ).find((node) => node.dataset.underlyingCard === normalizedSymbol);
    const target = symbolTarget || document.getElementById(sectionTargets[normalized]);
    if (!target) {
      input.setAttribute("aria-invalid", "true");
      return;
    }
    input.removeAttribute("aria-invalid");
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    input.select();
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") jump();
    if (event.key === "Escape") input.blur();
  });
  input.addEventListener("input", () => input.removeAttribute("aria-invalid"));
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      input.focus();
      input.select();
    }
  });
  input.dataset.commandReady = "true";
};

const setupFunctionRail = () => {
  const links = [...document.querySelectorAll("[data-rail-link]")];
  if (!links.length) return;
  const targets = links
    .map((link) => ({ link, target: document.getElementById(link.dataset.railLink) }))
    .filter(({ target }) => target);

  const select = (activeId) => {
    links.forEach((link) => {
      if (link.dataset.railLink === activeId) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  };

  const sync = () => {
    const atDocumentEnd =
      window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 24;
    if (atDocumentEnd) {
      const finalTarget = targets.at(-1)?.target.id;
      if (finalTarget) select(finalTarget);
      return;
    }
    const threshold = window.scrollY + 150;
    let activeId = targets[0]?.target.id;
    targets.forEach(({ target }) => {
      if (target.offsetTop <= threshold) activeId = target.id;
    });
    if (activeId) select(activeId);
  };

  links.forEach((link) => link.addEventListener("click", () => select(link.dataset.railLink)));
  window.addEventListener("scroll", sync, { passive: true });
  sync();
};

const setupRecordWorkspace = () => {
  const workspace = document.querySelector("[data-records-workspace]");
  if (!workspace || workspace.dataset.recordReady === "true") return;

  const buttons = [...workspace.querySelectorAll("[data-record-tab]")];
  const panes = [...workspace.querySelectorAll("[data-record-pane]")];
  let selectedRecord = "history";

  const activateRecord = (key) => {
    selectedRecord = key;
    buttons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.recordTab === selectedRecord));
    });
    panes.forEach((pane) => {
      pane.hidden = pane.dataset.recordPane !== selectedRecord;
    });
  };

  buttons.forEach((button) => {
    button.addEventListener("click", () => activateRecord(button.dataset.recordTab));
  });

  document.addEventListener("keydown", (event) => {
    const tag = event.target?.tagName?.toLowerCase();
    if (["input", "textarea", "select"].includes(tag) || event.target?.isContentEditable) return;
    const recordShortcuts = { F5: "books", F6: "history", F7: "positions" };
    if (!recordShortcuts[event.key]) return;
    event.preventDefault();
    workspace.open = true;
    activateRecord(recordShortcuts[event.key]);
    workspace.scrollIntoView({ behavior: "smooth" });
  });

  activateRecord(selectedRecord);
  workspace.dataset.recordReady = "true";
};

const setupDashboardInteractions = () => {
  setupCommandJump();
  setupFunctionRail();
  setupPeriodConsole();
  setupRecordWorkspace();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupDashboardInteractions, { once: true });
} else {
  setupDashboardInteractions();
}
