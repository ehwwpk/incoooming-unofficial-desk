const TARGET_STORAGE_KEY = "callDesk.monthlyOptionTarget";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const setText = (selector, value) => {
  document.querySelectorAll(selector).forEach((node) => {
    node.textContent = value;
  });
};

const percent = (value) => `${value.toFixed(1)}%`;

const setupTargetEditor = () => {
  const objective = document.querySelector("[data-objective-console]");
  if (!objective) return;

  const input = objective.querySelector("[data-target-input]");
  const reset = objective.querySelector("[data-target-reset]");
  const defaultTarget = Number(objective.dataset.defaultTarget) || 3000;
  const rollingAverage = Number(objective.dataset.rollingAverage) || 0;
  const monthlyResults = (objective.dataset.monthlyResults || "")
    .split(",")
    .map(Number)
    .filter(Number.isFinite);

  const normalize = (value) => Math.min(1000000, Math.max(100, value));

  const update = (rawTarget, persist = true) => {
    const target = normalize(Number(rawTarget) || defaultTarget);
    const targetLabel = currency.format(target);
    const gap = target - rollingAverage;
    const progress = target > 0 ? (rollingAverage / target) * 100 : 0;
    const monthsHit = monthlyResults.filter((result) => result >= target).length;

    setText("[data-target-display]", targetLabel);
    setText("[data-target-pace-label]", targetLabel);
    setText("[data-months-target-label]", targetLabel);
    setText("[data-header-target]", `${targetLabel}/MO`);
    setText("[data-months-hit]", `${monthsHit}/${monthlyResults.length}`);
    setText("[data-objective-progress]", percent(progress));
    setText(
      "[data-target-gap]",
      `${currency.format(Math.abs(gap))} / month ${gap >= 0 ? "below" : "above"} target`,
    );

    document.querySelectorAll("[data-objective-progress-bar]").forEach((bar) => {
      bar.style.setProperty("--objective-progress", `${Math.min(progress, 100)}%`);
    });
    document.querySelectorAll("[data-period-sheet]").forEach((sheet) => {
      const runRate = Number(sheet.dataset.monthlyRunRate) || 0;
      const sheetProgress = target > 0 ? Math.max(0, (runRate / target) * 100) : 0;
      const progressLabel = sheet.querySelector("[data-target-progress]");
      const progressBar = sheet.querySelector("[data-target-progress-bar]");
      if (progressLabel) progressLabel.textContent = percent(sheetProgress);
      if (progressBar) {
        progressBar.style.setProperty("--period-progress", `${Math.min(sheetProgress, 100)}%`);
      }
    });

    if (input && document.activeElement !== input) input.value = String(target);
    if (persist) {
      try {
        window.localStorage.setItem(TARGET_STORAGE_KEY, String(target));
      } catch (_) {
        // The dashboard still works when browser storage is unavailable.
      }
    }
  };

  let initialTarget = defaultTarget;
  try {
    const storedTarget = Number(window.localStorage.getItem(TARGET_STORAGE_KEY));
    if (Number.isFinite(storedTarget) && storedTarget >= 100) initialTarget = storedTarget;
  } catch (_) {
    // Use the server-provided default when browser storage is unavailable.
  }
  update(initialTarget, false);
  if (input) input.value = String(normalize(initialTarget));

  input?.addEventListener("input", () => {
    const nextTarget = Number(input.value);
    if (Number.isFinite(nextTarget) && nextTarget >= 100 && nextTarget <= 1000000) {
      update(nextTarget);
    }
  });
  input?.addEventListener("change", () => {
    const nextTarget = normalize(Number(input.value) || defaultTarget);
    input.value = String(nextTarget);
    update(nextTarget);
  });
  reset?.addEventListener("click", () => {
    try {
      window.localStorage.removeItem(TARGET_STORAGE_KEY);
    } catch (_) {
      // Reset still updates the page when browser storage is unavailable.
    }
    if (input) input.value = String(defaultTarget);
    update(defaultTarget, false);
  });
};

const setupPeriodConsole = () => {
  const consoleRoot = document.querySelector("[data-period-console]");
  if (!consoleRoot || consoleRoot.dataset.periodReady === "true") return;

  const periodButtons = [...consoleRoot.querySelectorAll("[data-period]")];
  const annualButtons = [...consoleRoot.querySelectorAll("[data-annual]")];
  const sheets = [...consoleRoot.querySelectorAll("[data-period-sheet]")];
  const annualControls = consoleRoot.querySelector("[data-annual-controls]");
  const quarterHistory = consoleRoot.querySelector("[data-quarter-history]");
  const windowCodes = { week: "1W", month: "4W", quarter: "13W", ytd: "YTD", r365: "R365" };
  let annualMode = "ytd";
  let selectedPeriod = "month";

  const updateActiveDesk = (sheet) => {
    if (!sheet) return;
    const key = sheet.dataset.periodSheet;
    setText("[data-active-window]", windowCodes[key] || sheet.dataset.windowLabel);
    setText("[data-active-range]", sheet.dataset.rangeLabel);
    setText("[data-active-option-label]", `NET OPTION INCOME / ${sheet.dataset.windowLabel}`);
    setText("[data-active-option-cash]", sheet.dataset.optionCash);
    setText("[data-active-option-meta]", `${sheet.dataset.optionApr} APR / ${sheet.dataset.gross} premium received`);
    setText("[data-active-total-label]", `TOTAL STRATEGY INCOME / ${sheet.dataset.windowLabel}`);
    setText("[data-active-total-cash]", sheet.dataset.totalCash);
    setText("[data-active-total-meta]", `${sheet.dataset.totalApr} APR / includes ${sheet.dataset.dividends} dividend income`);
    setText("[data-active-calls-contracts]", `${sheet.dataset.calls} / ${sheet.dataset.contracts}`);
    setText("[data-active-win-rate]", `${sheet.dataset.winRate} completed win rate`);
    setText("[data-active-capture-label]", `PREMIUM CAPTURE / ${sheet.dataset.windowLabel}`);
    setText("[data-active-capture-value]", sheet.dataset.capture);
  };

  const updateUnderlyingCards = (activeSheetKey, windowLabel) => {
    document.querySelectorAll("[data-underlying-card]").forEach((card) => {
      const windowData = card.querySelector(`[data-name-window="${activeSheetKey}"]`);
      if (!windowData) return;
      const windowCode = windowCodes[activeSheetKey] || windowLabel;
      card.querySelector("[data-name-option-label]").textContent = `NET OPTION INCOME / ${windowLabel}`;
      card.querySelector("[data-name-option-cash]").textContent = windowData.dataset.optionCash;
      card.querySelector("[data-name-option-apr-label]").textContent = `NET OPTION APR / ${windowCode}`;
      card.querySelector("[data-name-option-apr]").textContent = windowData.dataset.optionApr;
      card.querySelector("[data-name-dividend-label]").textContent = `DIVIDENDS / ${windowCode}`;
      card.querySelector("[data-name-dividends]").textContent = windowData.dataset.dividends;
      card.querySelector("[data-name-capture-label]").textContent = `CAPTURE / ${windowCode}`;
      card.querySelector("[data-name-capture]").textContent = windowData.dataset.capture;
    });
  };

  const activate = () => {
    const activeSheetKey = selectedPeriod === "annual" ? annualMode : selectedPeriod;
    const activeSheet = sheets.find((sheet) => sheet.dataset.periodSheet === activeSheetKey);
    sheets.forEach((sheet) => {
      sheet.hidden = sheet !== activeSheet;
    });
    periodButtons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.period === selectedPeriod));
    });
    annualButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.annual === annualMode));
    });
    if (annualControls) annualControls.hidden = selectedPeriod !== "annual";
    if (quarterHistory) quarterHistory.hidden = selectedPeriod !== "annual";
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
  annualButtons.forEach((button) => {
    button.addEventListener("click", () => {
      annualMode = button.dataset.annual;
      activate();
    });
  });

  document.addEventListener("keydown", (event) => {
    const tag = event.target?.tagName?.toLowerCase();
    if (["input", "textarea", "select"].includes(tag) || event.target?.isContentEditable) return;
    const periodShortcuts = { "1": "week", "2": "month", "3": "quarter", "4": "annual" };
    const annualShortcuts = { y: "ytd", r: "r365" };
    const sectionShortcuts = { F1: "portfolio", F2: "underlyings", F3: "income", F4: "records" };
    if (periodShortcuts[event.key]) {
      selectedPeriod = periodShortcuts[event.key];
      activate();
    } else if (annualShortcuts[event.key.toLowerCase()]) {
      annualMode = annualShortcuts[event.key.toLowerCase()];
      selectedPeriod = "annual";
      activate();
    } else if (sectionShortcuts[event.key]) {
      event.preventDefault();
      document.getElementById(sectionShortcuts[event.key])?.scrollIntoView({ behavior: "smooth" });
    }
  });

  setupTargetEditor();
  activate();
  consoleRoot.dataset.periodReady = "true";
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
  setupPeriodConsole();
  setupRecordWorkspace();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupDashboardInteractions, { once: true });
} else {
  setupDashboardInteractions();
}
