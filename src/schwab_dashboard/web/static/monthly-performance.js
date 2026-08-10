const MONTHLY_TARGET_STORAGE_KEY = "callDesk.monthlyOptionTarget";

const formatTarget = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const initializeMonthlyPerformance = () => {
  const ledger = document.querySelector("[data-monthly-performance]");
  if (!ledger) return;

  const defaultTarget = Number(ledger.dataset.defaultTarget) || 3000;
  let target = defaultTarget;
  try {
    const storedTarget = Number(window.localStorage.getItem(MONTHLY_TARGET_STORAGE_KEY));
    if (Number.isFinite(storedTarget) && storedTarget >= 100) target = storedTarget;
  } catch (_) {
    // The server-provided target remains authoritative when storage is unavailable.
  }

  document.querySelectorAll("[data-workspace-monthly-target]").forEach((node) => {
    node.textContent = formatTarget.format(target);
  });

  const monthlyResults = (ledger.dataset.monthlyResults || "")
    .split(",")
    .map(Number)
    .filter(Number.isFinite);
  document.querySelectorAll("[data-workspace-months-hit]").forEach((node) => {
    node.textContent = `${monthlyResults.filter((cash) => cash >= target).length}/${monthlyResults.length}`;
  });

  ledger.querySelectorAll("[data-month-performance]").forEach((row) => {
    const optionCash = Number(row.dataset.optionCash) || 0;
    const progress = target > 0 ? Math.max(0, (optionCash / target) * 100) : 0;
    const label = row.querySelector("[data-month-progress]");
    const bar = row.querySelector("[data-month-progress-bar]");
    if (label) label.textContent = `${progress.toFixed(1)}%`;
    if (bar) bar.style.setProperty("--month-progress", `${progress}%`);
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeMonthlyPerformance, { once: true });
} else {
  initializeMonthlyPerformance();
}
