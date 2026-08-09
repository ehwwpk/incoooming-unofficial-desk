(() => {
  const panel = document.querySelector("[data-nibwick-popover]");
  const notes = [...document.querySelectorAll("[data-nibwick-note]")];
  const stage = document.querySelector("[data-nibwick-stage]");
  const nibwick = document.querySelector("[data-nibwick]");
  const badge = document.querySelector("[data-nibwick-alert-badge]");
  const closeButton = panel?.querySelector("[data-nibwick-close]");
  if (!panel || !notes.length || !stage || !nibwick || !badge || !closeButton) return;

  const position = panel.querySelector("[data-nibwick-note-position]");
  const panelTitle = panel.querySelector("[data-nibwick-panel-title]");
  const announcement = document.querySelector("[data-nibwick-announcement]");
  const seenSymbols = new Set();
  let activeIndex = 0;
  let returnFocus = null;
  let linkedCard = null;

  const clearLinkedCard = () => {
    if (!linkedCard) return;
    delete linkedCard.dataset.nibwickLinked;
    linkedCard.removeAttribute("aria-describedby");
    linkedCard = null;
  };

  const linkActiveCard = () => {
    clearLinkedCard();
    if (panel.hidden) return;
    linkedCard = document.getElementById(notes[activeIndex].dataset.alertTarget);
    if (!linkedCard) return;
    linkedCard.dataset.nibwickLinked = "true";
    linkedCard.setAttribute("aria-describedby", "nibwick-panel-title");
  };

  const positionPanel = () => {
    if (panel.hidden) return;
    const source = returnFocus instanceof HTMLElement ? returnFocus : nibwick;
    const sourceRect = source.getBoundingClientRect();
    const panelHeight = panel.getBoundingClientRect().height;
    const sourceCenter = sourceRect.top + sourceRect.height / 2;
    const panelTop = Math.min(
      Math.max(72, sourceCenter - 42),
      Math.max(72, window.innerHeight - panelHeight - 12),
    );
    const tipPosition = Math.min(Math.max(20, sourceCenter - panelTop), panelHeight - 20);
    panel.style.setProperty("--nibwick-popover-top", `${panelTop}px`);
    panel.style.setProperty("--nibwick-tip-y", `${tipPosition}px`);
  };

  const setExpanded = (expanded) => {
    nibwick.setAttribute("aria-expanded", String(expanded));
    badge.setAttribute("aria-expanded", String(expanded));
  };

  const showNote = (index) => {
    activeIndex = (index + notes.length) % notes.length;
    notes.forEach((note, noteIndex) => {
      note.hidden = noteIndex !== activeIndex;
    });
    if (position) position.textContent = `${activeIndex + 1} / ${notes.length}`;
    const symbol = notes[activeIndex].dataset.alertSymbol;
    panel.dataset.activeSymbol = symbol;
    if (panelTitle) panelTitle.textContent = `Nibwick noticed ${symbol}`;
    linkActiveCard();
    positionPanel();
  };

  const showSymbol = (symbol) => {
    const index = notes.findIndex((note) => note.dataset.alertSymbol === symbol);
    if (index >= 0) showNote(index);
    return index >= 0;
  };

  const openPanel = (trigger) => {
    returnFocus = trigger instanceof HTMLElement ? trigger : nibwick;
    panel.hidden = false;
    document.body.dataset.nibwickPopoverOpen = "true";
    delete stage.dataset.attention;
    setExpanded(true);
    linkActiveCard();
    positionPanel();
    closeButton.focus({ preventScroll: true });
    document.dispatchEvent(
      new CustomEvent("nibwick:panel-state", { detail: { open: true } }),
    );
  };

  const closePanel = (restoreFocus = true) => {
    if (panel.hidden) return;
    panel.hidden = true;
    clearLinkedCard();
    delete document.body.dataset.nibwickPopoverOpen;
    setExpanded(false);
    document.dispatchEvent(
      new CustomEvent("nibwick:panel-state", { detail: { open: false } }),
    );
    if (restoreFocus && returnFocus instanceof HTMLElement) {
      returnFocus.focus({ preventScroll: true });
    }
  };

  const togglePanel = (trigger) => {
    if (panel.hidden) openPanel(trigger);
    else closePanel();
  };

  const signalSymbol = (symbol) => {
    if (seenSymbols.has(symbol) || !showSymbol(symbol) || !panel.hidden) return;
    seenSymbols.add(symbol);
    stage.dataset.attention = "true";
    badge.setAttribute("aria-label", `Open Nibwick's ${symbol} note`);
    if (announcement) announcement.textContent = `Nibwick has a note about ${symbol}.`;
    document.dispatchEvent(
      new CustomEvent("nibwick:react", { detail: { kind: "notice", symbol } }),
    );
  };

  panel.querySelector("[data-nibwick-note-prev]")?.addEventListener("click", () => {
    showNote(activeIndex - 1);
  });
  panel.querySelector("[data-nibwick-note-next]")?.addEventListener("click", () => {
    showNote(activeIndex + 1);
  });
  panel.querySelectorAll("[data-nibwick-show-name]").forEach((link) => {
    link.addEventListener("click", () => {
      const activeNote = link.closest("[data-nibwick-note]");
      const targetId = activeNote?.dataset.alertTarget;
      const symbol = activeNote?.dataset.alertSymbol;
      const targetCard = targetId ? document.getElementById(targetId) : null;
      if (symbol) seenSymbols.add(symbol);
      if (targetCard) {
        targetCard.dataset.nibwickArrival = "true";
        window.setTimeout(() => delete targetCard.dataset.nibwickArrival, 2400);
      }
      closePanel(false);
    });
  });
  closeButton.addEventListener("click", () => closePanel());
  badge.addEventListener("click", () => togglePanel(badge));
  document.addEventListener("nibwick:toggle-notes", (event) => {
    togglePanel(event.detail?.trigger || nibwick);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });
  document.addEventListener("click", (event) => {
    if (
      panel.hidden ||
      !(event.target instanceof Element) ||
      event.target.closest("[data-nibwick-popover], [data-nibwick], [data-nibwick-alert-badge]")
    ) {
      return;
    }
    closePanel(false);
  });
  window.addEventListener("resize", positionPanel, { passive: true });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) signalSymbol(entry.target.dataset.underlyingCard);
        }
      },
      { rootMargin: "-20% 0px -65% 0px", threshold: 0 },
    );
    for (const card of document.querySelectorAll("[data-underlying-card]")) {
      if (notes.some((note) => note.dataset.alertSymbol === card.dataset.underlyingCard)) {
        observer.observe(card);
      }
    }
  }

  showNote(0);
  setExpanded(false);
})();
