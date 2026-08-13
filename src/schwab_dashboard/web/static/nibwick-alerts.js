(() => {
  const panel = document.querySelector("[data-nibwick-popover]");
  const notes = [...document.querySelectorAll("[data-nibwick-note]")];
  const stage = document.querySelector("[data-nibwick-stage]");
  const nibwick = document.querySelector("[data-nibwick]");
  const badge = document.querySelector("[data-nibwick-alert-badge]");
  const summaryTriggers = [...document.querySelectorAll("[data-nibwick-summary]")];
  const closeButton = panel?.querySelector("[data-nibwick-close]");
  if (!panel || !notes.length || !stage || !nibwick || !badge || !closeButton) return;

  const position = panel.querySelector("[data-nibwick-note-position]");
  const panelTitle = panel.querySelector("[data-nibwick-panel-title]");
  const headerSymbol = panel.querySelector("[data-nibwick-header-symbol]");
  const headerLevel = panel.querySelector("[data-nibwick-header-level]");
  const announcement = document.querySelector("[data-nibwick-announcement]");
  const activeCountElement = badge.querySelector("[data-nibwick-active-count]");
  const rosterButtons = [...panel.querySelectorAll("[data-nibwick-note-jump]")];
  const stateStorageKey = "incoooming:nibwick-alert-state:v1";
  const currentAlertIds = new Set(notes.map((note) => note.dataset.alertId));
  const readAlertIds = new Set();
  const alertState = {};
  const seenSymbols = new Set();
  let activeIndex = 0;
  let returnFocus = null;
  let linkedCard = null;
  let pendingSymbolIndex = null;

  try {
    const storedState = JSON.parse(window.localStorage.getItem(stateStorageKey) || "{}");
    if (storedState && typeof storedState === "object") {
      Object.entries(storedState).forEach(([alertId, value]) => {
        if (!currentAlertIds.has(alertId) || !value || typeof value !== "object") return;
        if (value.status === "snoozed" && Number(value.until) <= Date.now()) return;
        alertState[alertId] = value;
        readAlertIds.add(alertId);
      });
    }
  } catch {
    // A blocked session store should not prevent notes from working.
  }

  const persistReadState = () => {
    try {
      window.localStorage.setItem(stateStorageKey, JSON.stringify(alertState));
    } catch {
      // Read state can remain in memory when browser storage is unavailable.
    }
  };

  const renderUnreadState = () => {
    const unreadCount = notes.filter((note) => !readAlertIds.has(note.dataset.alertId)).length;
    const nextUnreadNote = notes.find((note) => !readAlertIds.has(note.dataset.alertId));
    const symbols = [...new Set(notes.map((note) => note.dataset.alertSymbol))];
    badge.hidden = false;
    badge.dataset.newCount = String(unreadCount);
    if (activeCountElement) activeCountElement.textContent = String(notes.length);
    badge.setAttribute(
      "aria-label",
      `Open Nibwick's ${notes.length} active ${notes.length === 1 ? "note" : "notes"}; ${unreadCount} new`,
    );
    rosterButtons.forEach((button) => {
      const note = notes[Number(button.dataset.alertIndex)];
      const reviewed = note ? readAlertIds.has(note.dataset.alertId) : false;
      button.dataset.reviewState = reviewed ? "reviewed" : "new";
      const state = button.querySelector("[data-nibwick-roster-state]");
      if (state) state.textContent = reviewed ? "SEEN" : "NEW";
    });
    summaryTriggers.forEach((trigger) => {
      const count = trigger.querySelector("[data-nibwick-summary-count]");
      const detail = trigger.querySelector("[data-nibwick-summary-detail]");
      if (count) count.textContent = `${notes.length} ACTIVE`;
      if (detail) {
        detail.textContent = nextUnreadNote
          ? `${unreadCount} NEW · ${nextUnreadNote.dataset.alertSymbol} · ${nextUnreadNote.dataset.alertHeadline || "Desk note"}`
          : `SEEN · ${symbols.join(" · ")} STILL ACTIVE`;
      }
      trigger.setAttribute(
        "aria-label",
        `Open ${notes.length} active Nibwick ${notes.length === 1 ? "note" : "notes"}; ${unreadCount} new`,
      );
    });
    stage.dataset.notesRead = unreadCount === 0 ? "true" : "false";
    if (unreadCount === 0) {
      delete stage.dataset.attention;
      if (announcement) announcement.textContent = `All ${notes.length} active Nibwick notes reviewed.`;
    }
  };

  const markNoteRead = (index) => {
    const alertId = notes[index]?.dataset.alertId;
    if (!alertId || readAlertIds.has(alertId)) return;
    readAlertIds.add(alertId);
    alertState[alertId] = { status: "read", updatedAt: Date.now() };
    persistReadState();
    renderUnreadState();
  };

  const setResolution = (status) => {
    const alertId = notes[activeIndex]?.dataset.alertId;
    if (!alertId) return;
    readAlertIds.add(alertId);
    alertState[alertId] = {
      status,
      updatedAt: Date.now(),
      ...(status === "snoozed" ? { until: Date.now() + 24 * 60 * 60 * 1000 } : {}),
    };
    persistReadState();
    renderUnreadState();
    closePanel();
  };

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
    summaryTriggers.forEach((trigger) => {
      trigger.setAttribute("aria-expanded", String(expanded));
    });
  };

  const showNote = (index) => {
    activeIndex = (index + notes.length) % notes.length;
    notes.forEach((note, noteIndex) => {
      note.hidden = noteIndex !== activeIndex;
    });
    if (position) position.textContent = `${activeIndex + 1} / ${notes.length}`;
    const activeNote = notes[activeIndex];
    const symbol = activeNote.dataset.alertSymbol;
    panel.dataset.activeSymbol = symbol;
    panel.dataset.activeLevel = activeNote.dataset.alertLevel;
    if (panelTitle) panelTitle.textContent = activeNote.dataset.alertHeadline || "Desk note";
    if (headerSymbol) headerSymbol.textContent = symbol;
    if (headerLevel) {
      headerLevel.textContent = activeNote.dataset.alertLevelLabel;
      headerLevel.className = `nibwick-popover-level ${activeNote.dataset.alertLevel}`;
    }
    rosterButtons.forEach((button, buttonIndex) => {
      if (buttonIndex === activeIndex) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    });
    if (!panel.hidden) markNoteRead(activeIndex);
    linkActiveCard();
    positionPanel();
  };

  const openPanel = (trigger) => {
    returnFocus = trigger instanceof HTMLElement ? trigger : nibwick;
    panel.hidden = false;
    document.body.dataset.nibwickPopoverOpen = "true";
    delete stage.dataset.attention;
    const nextUnreadIndex = notes.findIndex((note) => !readAlertIds.has(note.dataset.alertId));
    const requestedIndex = returnFocus === nibwick || returnFocus === badge ? pendingSymbolIndex : null;
    showNote(requestedIndex ?? (nextUnreadIndex >= 0 ? nextUnreadIndex : activeIndex));
    pendingSymbolIndex = null;
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
      const focusTarget = returnFocus === badge && badge.hidden ? nibwick : returnFocus;
      focusTarget.focus({ preventScroll: true });
    }
  };

  const togglePanel = (trigger) => {
    if (panel.hidden) openPanel(trigger);
    else closePanel();
  };

  const signalSymbol = (symbol) => {
    const index = notes.findIndex((note) => note.dataset.alertSymbol === symbol);
    if (
      index < 0 ||
      readAlertIds.has(notes[index].dataset.alertId) ||
      seenSymbols.has(symbol) ||
      !panel.hidden
    ) {
      return;
    }
    pendingSymbolIndex = index;
    seenSymbols.add(symbol);
    stage.dataset.attention = "true";
    badge.setAttribute("aria-label", `Open Nibwick's ${symbol} note`);
    if (announcement) announcement.textContent = `Nibwick has a note about ${symbol}.`;
    document.dispatchEvent(
      new CustomEvent("nibwick:react", { detail: { kind: "notice", symbol } }),
    );
  };

  panel.querySelectorAll("[data-nibwick-note-prev]").forEach((button) => {
    button.addEventListener("click", () => showNote(activeIndex - 1));
  });
  panel.querySelectorAll("[data-nibwick-note-next]").forEach((button) => {
    button.addEventListener("click", () => showNote(activeIndex + 1));
  });
  rosterButtons.forEach((button) => {
    button.addEventListener("click", () => showNote(Number(button.dataset.alertIndex)));
  });
  panel.querySelectorAll("[data-nibwick-show-name]").forEach((link) => {
    link.addEventListener("click", () => {
      const activeNote = link.closest("[data-nibwick-note]");
      const targetId = activeNote?.dataset.alertTarget;
      const symbol = activeNote?.dataset.alertSymbol;
      const targetCard = targetId ? document.getElementById(targetId) : null;
      if (symbol) seenSymbols.add(symbol);
      markNoteRead(activeIndex);
      if (targetCard) {
        targetCard.dataset.nibwickArrival = "true";
        window.setTimeout(() => delete targetCard.dataset.nibwickArrival, 2400);
      }
      closePanel(false);
    });
  });
  panel.querySelectorAll("[data-nibwick-ack]").forEach((button) => {
    button.addEventListener("click", () => setResolution("acknowledged"));
  });
  panel.querySelectorAll("[data-nibwick-roll-review]").forEach((link) => {
    link.addEventListener("click", () => {
      markNoteRead(activeIndex);
    });
  });
  panel.querySelectorAll("[data-nibwick-snooze]").forEach((button) => {
    button.addEventListener("click", () => setResolution("snoozed"));
  });
  closeButton.addEventListener("click", () => closePanel());
  badge.addEventListener("click", () => togglePanel(badge));
  summaryTriggers.forEach((trigger) => {
    trigger.addEventListener("click", () => togglePanel(trigger));
  });
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
      event.target.closest("[data-nibwick-popover], [data-nibwick], [data-nibwick-alert-badge], [data-nibwick-summary]")
    ) {
      return;
    }
    closePanel(false);
  });
  window.addEventListener("resize", positionPanel, { passive: true });
  panel.querySelectorAll("details").forEach((details) => {
    details.addEventListener("toggle", positionPanel);
  });

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
  renderUnreadState();
  setExpanded(false);
})();
