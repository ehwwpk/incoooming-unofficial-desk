(() => {
  const cards = [...document.querySelectorAll("[data-underlying-card]")];
  if (!cards.length) return;

  const setFocus = (activeCard) => {
    for (const card of cards) {
      const active = card === activeCard;
      card.dataset.chartFocus = String(active);
      const button = card.querySelector("[data-chart-focus]");
      if (button) {
        button.setAttribute("aria-pressed", String(active));
        button.textContent = active ? "EXIT FOCUS" : "FOCUS";
      }
    }
    if (activeCard) {
      document.body.dataset.chartFocus = activeCard.dataset.underlyingCard;
      activeCard.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      delete document.body.dataset.chartFocus;
    }
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  };

  for (const card of cards) {
    const button = card.querySelector("[data-chart-focus]");
    button?.addEventListener("click", () => {
      setFocus(card.dataset.chartFocus === "true" ? null : card);
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.dataset.chartFocus) setFocus(null);
  });
})();
