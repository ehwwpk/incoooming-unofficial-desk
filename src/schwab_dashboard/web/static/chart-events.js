(() => {
  const triggers = [...document.querySelectorAll("[data-chart-event-trigger]")];
  if (!triggers.length) return;

  const dollars = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const dates = new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit" });
  const eventTitles = {
    sale: "PREMIUM COLLECTED",
    expired: "EXPIRED WORTHLESS",
    closed: "BOUGHT CLOSED",
    rolled: "ROLLED",
    assigned: "SHARES CALLED AWAY",
  };

  let activeTrigger = null;
  let activeSource = null;

  const number = (value) => Number.parseFloat(value || "0");
  const money = (value) => dollars.format(number(value));
  const signedMoney = (value) => {
    const amount = number(value);
    if (amount > 0) return `+${dollars.format(amount)}`;
    if (amount < 0) return `−${dollars.format(Math.abs(amount))}`;
    return dollars.format(0);
  };
  const shortDate = (value) => {
    const [year, month, day] = value.split("-").map(Number);
    return dates.format(new Date(year, month - 1, day));
  };
  const set = (root, selector, value) => {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  };

  const markerCard = (trigger) => trigger.closest("[data-underlying-card]");
  const markerCanvas = (trigger) => trigger.closest(".price-path-canvas");

  const clearFocus = (canvas) => {
    if (!canvas) return;
    delete canvas.dataset.eventFocus;
    canvas.querySelectorAll("[data-event-active]").forEach((node) => {
      delete node.dataset.eventActive;
    });
    canvas.closest("[data-underlying-card]")
      ?.querySelectorAll("[data-chart-ledger-event][data-event-active]")
      .forEach((node) => delete node.dataset.eventActive);
  };

  const applyFocus = (trigger) => {
    const canvas = markerCanvas(trigger);
    if (!canvas) return;
    clearFocus(canvas);

    if (trigger.dataset.eventKind === "share") {
      canvas.dataset.eventFocus = `share-${trigger.dataset.date}`;
      trigger.dataset.eventActive = "true";
      return;
    }

    const lifecycleId = trigger.dataset.lifecycleId;
    canvas.dataset.eventFocus = lifecycleId;
    canvas.querySelectorAll("[data-lifecycle-id]").forEach((node) => {
      if (node.dataset.lifecycleId === lifecycleId) node.dataset.eventActive = "true";
    });
    markerCard(trigger)?.querySelectorAll("[data-chart-ledger-event]").forEach((node) => {
      if (node.dataset.lifecycleId === lifecycleId) node.dataset.eventActive = "true";
    });
  };

  const populateOption = (popover, trigger, symbol) => {
    const type = trigger.dataset.eventType;
    const contracts = number(trigger.dataset.contracts);
    const grossPremium = number(trigger.dataset.grossPremium);
    const buybackCost = number(trigger.dataset.buybackCost);
    const netCash = number(trigger.dataset.netCash);
    const heading = `#${trigger.dataset.eventSequence} · ${eventTitles[type] || type.toUpperCase()} · ${shortDate(trigger.dataset.date)}`;
    const contract = `${contracts}× ${symbol} ${money(trigger.dataset.strike)}C · EXP ${shortDate(trigger.dataset.expiresOn)}`;
    let cashText = `${signedMoney(grossPremium)} received · ${money(trigger.dataset.premiumPerShare)}/sh`;
    let cashClass = "positive";
    let footer = "OPEN PREMIUM EVENT";

    if (type === "expired") {
      cashText = `${money(grossPremium)} kept · no close debit`;
      footer = `RESOLVES PREMIUM EVENT #${trigger.dataset.linkedSaleSequence} · ${signedMoney(netCash)} NET OPTION CASH`;
    } else if (type === "closed" || type === "rolled") {
      cashText = `${signedMoney(-buybackCost)} close · ${signedMoney(netCash)} leg net`;
      cashClass = buybackCost > 0 ? "negative" : "positive";
      footer = `RESOLVES PREMIUM EVENT #${trigger.dataset.linkedSaleSequence} · ${trigger.dataset.outcome.toUpperCase()}`;
    } else if (type === "assigned") {
      cashText = `${money(grossPremium)} kept · ${contracts * 100} shares called away`;
      footer = `RESOLVES PREMIUM EVENT #${trigger.dataset.linkedSaleSequence} · ASSIGNED`;
    } else if (trigger.dataset.linkedResolutionSequence) {
      footer = `LATER RESOLVED → #${trigger.dataset.linkedResolutionSequence} ${trigger.dataset.outcome.toUpperCase()}`;
    }

    set(popover, "[data-event-popover-heading]", heading);
    set(popover, "[data-event-popover-contract]", contract);
    const cash = popover.querySelector("[data-event-popover-cash]");
    if (cash) {
      cash.textContent = cashText;
      cash.className = cashClass;
    }
    set(popover, "[data-event-fact-one-label]", "STOCK AT SALE");
    set(popover, "[data-event-fact-one-value]", money(trigger.dataset.underlyingAtSale));
    set(popover, "[data-event-fact-two-label]", "STRIKE BUFFER");
    set(popover, "[data-event-fact-two-value]", `${number(trigger.dataset.strikeBuffer).toFixed(1)}%`);
    set(popover, "[data-event-fact-three-label]", "ENTRY TERM");
    set(popover, "[data-event-fact-three-value]", `${trigger.dataset.entryDte} DTE`);
    set(popover, "[data-event-popover-link]", footer);
  };

  const populateShare = (popover, trigger, symbol) => {
    const action = trigger.dataset.shareTrade.toUpperCase();
    set(popover, "[data-event-popover-heading]", `SHARES ${action === "BUY" ? "BOUGHT" : "SOLD"} · ${shortDate(trigger.dataset.date)}`);
    set(popover, "[data-event-popover-contract]", `${trigger.dataset.shares} ${symbol} SHARES`);
    const cash = popover.querySelector("[data-event-popover-cash]");
    if (cash) {
      cash.textContent = `${money(trigger.dataset.price)}/share`;
      cash.className = action === "BUY" ? "negative" : "positive";
    }
    set(popover, "[data-event-fact-one-label]", "ACTION");
    set(popover, "[data-event-fact-one-value]", action);
    set(popover, "[data-event-fact-two-label]", "PRICE");
    set(popover, "[data-event-fact-two-value]", money(trigger.dataset.price));
    set(popover, "[data-event-fact-three-label]", "DATE");
    set(popover, "[data-event-fact-three-value]", shortDate(trigger.dataset.date));
    set(popover, "[data-event-popover-link]", "UNDERLYING INVENTORY EVENT");
  };

  const positionPopover = (trigger, popover) => {
    const canvas = markerCanvas(trigger);
    const visual = trigger.querySelector(":scope > b") || trigger;
    if (!canvas) return;
    const canvasRect = canvas.getBoundingClientRect();
    const visualRect = visual.getBoundingClientRect();
    const centerX = visualRect.left + visualRect.width / 2 - canvasRect.left;
    const centerY = visualRect.top + visualRect.height / 2 - canvasRect.top;
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    const margin = 8;
    const gap = 14;
    const useRight = centerX + gap + width <= canvasRect.width - margin;
    const left = useRight ? centerX + gap : centerX - width - gap;
    const top = Math.min(
      Math.max(margin, centerY - height / 2),
      Math.max(margin, canvasRect.height - height - margin),
    );
    popover.style.left = `${Math.max(margin, left)}px`;
    popover.style.top = `${top}px`;
    popover.dataset.side = useRight ? "right" : "left";
  };

  const closeEvent = ({ restoreFocus = false } = {}) => {
    if (!activeTrigger) return;
    const popover = markerCanvas(activeTrigger)?.querySelector("[data-chart-event-popover]");
    activeTrigger.setAttribute("aria-expanded", "false");
    if (popover) popover.hidden = true;
    clearFocus(markerCanvas(activeTrigger));
    const source = activeSource;
    activeTrigger = null;
    activeSource = null;
    if (restoreFocus) source?.focus();
  };

  const openEvent = (trigger, source = trigger) => {
    if (activeTrigger === trigger) {
      closeEvent();
      return;
    }
    closeEvent();
    const card = markerCard(trigger);
    const popover = markerCanvas(trigger)?.querySelector("[data-chart-event-popover]");
    if (!card || !popover) return;
    const symbol = card.dataset.underlyingCard;
    if (trigger.dataset.eventKind === "share") populateShare(popover, trigger, symbol);
    else populateOption(popover, trigger, symbol);
    popover.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    applyFocus(trigger);
    activeTrigger = trigger;
    activeSource = source;
    positionPopover(trigger, popover);
  };

  for (const trigger of triggers) {
    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      openEvent(trigger);
    });
    trigger.addEventListener("pointerleave", () => delete trigger.dataset.tooltipDismissed);
    trigger.addEventListener("focusout", () => delete trigger.dataset.tooltipDismissed);
  }

  document.querySelectorAll("[data-chart-ledger-event]").forEach((ledgerEvent) => {
    ledgerEvent.addEventListener("click", () => {
      const card = ledgerEvent.closest("[data-underlying-card]");
      const marker = [...(card?.querySelectorAll("[data-chart-event-trigger][data-event-sequence]") || [])]
        .find((node) => node.dataset.eventSequence === ledgerEvent.dataset.eventSequence);
      if (marker) openEvent(marker, ledgerEvent);
    });
  });

  document.querySelectorAll("[data-chart-event-close]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      closeEvent({ restoreFocus: true });
    });
  });
  document.addEventListener("pointerdown", (event) => {
    if (!activeTrigger) return;
    const popover = markerCanvas(activeTrigger)?.querySelector("[data-chart-event-popover]");
    if (!activeTrigger.contains(event.target) && !popover?.contains(event.target)) closeEvent();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (activeTrigger) closeEvent({ restoreFocus: true });
    else if (event.target.matches?.("[data-chart-event-trigger]")) event.target.dataset.tooltipDismissed = "true";
  });
  const reposition = () => {
    if (!activeTrigger) return;
    const popover = markerCanvas(activeTrigger)?.querySelector("[data-chart-event-popover]");
    if (popover) positionPopover(activeTrigger, popover);
  };
  window.addEventListener("resize", reposition, { passive: true });
  document.addEventListener("option-event-layout", reposition);
  document.addEventListener("position-detail-toggle", () => closeEvent());
})();
