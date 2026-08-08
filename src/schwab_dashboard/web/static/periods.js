const setupPeriodConsole = () => {
  const consoleRoot = document.querySelector("[data-period-console]");
  if (!consoleRoot) return;

  const periodButtons = [...consoleRoot.querySelectorAll("[data-period]")];
  const annualButtons = [...consoleRoot.querySelectorAll("[data-annual]")];
  const sheets = [...consoleRoot.querySelectorAll("[data-period-sheet]")];
  const annualControls = consoleRoot.querySelector("[data-annual-controls]");
  const quarterHistory = consoleRoot.querySelector("[data-quarter-history]");
  let annualMode = "ytd";
  let selectedPeriod = "quarter";

  const activate = () => {
    const activeSheet = selectedPeriod === "annual" ? annualMode : selectedPeriod;
    sheets.forEach((sheet) => {
      sheet.hidden = sheet.dataset.periodSheet !== activeSheet;
    });
    periodButtons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.period === selectedPeriod));
    });
    annualButtons.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.annual === annualMode));
    });
    if (annualControls) annualControls.hidden = selectedPeriod !== "annual";
    if (quarterHistory) quarterHistory.hidden = selectedPeriod !== "annual";
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

  activate();
  consoleRoot.dataset.periodReady = "true";
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupPeriodConsole, { once: true });
} else {
  setupPeriodConsole();
}
