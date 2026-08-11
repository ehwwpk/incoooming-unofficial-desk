(() => {
  const root = document.querySelector("[data-results-cash]");
  if (!root) return;

  const buttons = [...root.querySelectorAll("[data-results-cash-period]")];
  const series = [...root.querySelectorAll("[data-results-cash-series]")];
  const grainLabel = root.querySelector("[data-results-cash-grain-label]");
  let selected = "ytd";

  const activate = (key, { focus = false } = {}) => {
    if (!series.some((item) => item.dataset.resultsCashSeries === key)) return;
    selected = key;
    buttons.forEach((button) => {
      const active = button.dataset.resultsCashPeriod === selected;
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
      if (active && focus) button.focus();
    });
    series.forEach((item) => {
      item.hidden = item.dataset.resultsCashSeries !== selected;
    });
    const activeSeries = series.find((item) => item.dataset.resultsCashSeries === selected);
    const activeButton = buttons.find((button) => button.dataset.resultsCashPeriod === selected);
    if (grainLabel && activeSeries && activeButton) {
      grainLabel.textContent = `${activeSeries.dataset.resultsCashGrain} · ${activeButton.textContent.split(" · ")[0]}`;
    }
  };

  buttons.forEach((button, index) => {
    button.addEventListener("click", () => activate(button.dataset.resultsCashPeriod));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const offset = event.key === "ArrowRight" ? 1 : -1;
      const next = buttons[(index + offset + buttons.length) % buttons.length];
      activate(next.dataset.resultsCashPeriod, { focus: true });
    });
  });

  activate(selected);
})();
