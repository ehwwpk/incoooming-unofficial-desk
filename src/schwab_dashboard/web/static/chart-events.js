(() => {
  const triggers = [...document.querySelectorAll("[data-chart-event-trigger]")];
  if (!triggers.length) return;

  const dollars = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const strikes = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
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
  const parseDay = (value) => {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  };
  const dateKey = (value) => {
    const year = value.getFullYear();
    const month = `${value.getMonth() + 1}`.padStart(2, "0");
    const day = `${value.getDate()}`.padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  const moveDays = (value, amount) => {
    const result = new Date(value);
    result.setDate(result.getDate() + amount);
    return result;
  };
  const daysBetween = (start, end) => Math.round((end - start) / 86400000);
  const set = (root, selector, value) => {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  };
  const setFirstFactDetail = (popover, label, value) => {
    const node = popover.querySelector("[data-event-fact-one-detail]");
    if (!node) return;
    node.textContent = label && value ? `${label} ${value}` : "";
    node.hidden = !node.textContent;
  };
  const hideTerm = (popover) => {
    const term = popover.querySelector("[data-event-term]");
    if (term) term.hidden = true;
  };
  const hideValue = (popover) => {
    const value = popover.querySelector("[data-event-value]");
    if (value) value.hidden = true;
  };
  const populateValue = (popover, trigger) => {
    const meter = popover.querySelector("[data-event-value]");
    const ratio = number(trigger.dataset.optionValuePercent);
    const optionValue = number(trigger.dataset.optionValuePerShare);
    const entryCredit = number(trigger.dataset.premiumPerShare);
    if (!meter || !trigger.dataset.optionValuePercent || entryCredit <= 0) {
      hideValue(popover);
      return;
    }

    const outcome = (trigger.dataset.outcome || "").toUpperCase();
    const checkpoints = {
      OPEN: "NOW",
      EXPIRED: "AT EXPIRY",
      CLOSED: "CLOSE COST",
      ROLLED: "ROLL COST",
    };
    const checkpoint = checkpoints[outcome] || "AT RESOLUTION";
    meter.hidden = false;
    meter.classList.toggle("is-over-entry", ratio > 100);
    meter.classList.toggle("is-under-entry", ratio <= 100);
    meter.style.setProperty("--value-progress", `${ratio}%`);
    meter.setAttribute(
      "aria-label",
      `Option value was ${ratio.toFixed(1)} percent of premium received: ${money(optionValue)} per share ${checkpoint.toLowerCase()}, compared with ${money(entryCredit)} per share received`,
    );
    set(meter, "[data-event-value-percent]", `${ratio.toFixed(1)}%`);
    set(
      meter,
      "[data-event-value-overrun]",
      ratio > 100 ? `+${(ratio - 100).toFixed(1)}% OVER` : "ENTRY 100%",
    );
    set(
      meter,
      "[data-event-value-detail]",
      `${money(optionValue)}/SH ${checkpoint} · ${money(entryCredit)}/SH RECEIVED`,
    );
  };
  const populateTerm = (popover, trigger) => {
    const term = popover.querySelector("[data-event-term]");
    const track = popover.querySelector("[data-event-term-track]");
    const entryDte = Math.max(0, Math.round(number(trigger.dataset.entryDte)));
    if (!term || !track || !trigger.dataset.expiresOn || entryDte === 0) {
      hideTerm(popover);
      return;
    }

    const expiresOn = parseDay(trigger.dataset.expiresOn);
    const soldOn = moveDays(expiresOn, -entryDte);
    const resolutionTypes = new Set(["closed", "expired", "assigned"]);
    const resolvedOn = trigger.dataset.resolvedOn
      || (resolutionTypes.has(trigger.dataset.eventType) ? trigger.dataset.date : "");
    const checkpoint = parseDay(resolvedOn || popover.dataset.asOf);
    const elapsedDays = Math.min(entryDte, Math.max(0, daysBetween(soldOn, checkpoint)));
    const daysLeft = Math.max(0, daysBetween(checkpoint, expiresOn));
    const progress = Math.min(100, Math.max(0, elapsedDays / entryDte * 100));
    const outcome = (trigger.dataset.outcome || trigger.dataset.eventType).toUpperCase();

    term.hidden = false;
    term.style.setProperty("--term-progress", `${progress}%`);
    track.setAttribute("aria-valuenow", `${Math.round(progress)}`);
    set(term, "[data-event-term-start]", `SOLD ${shortDate(dateKey(soldOn)).toUpperCase()}`);
    set(
      term,
      "[data-event-term-status]",
      resolvedOn ? `${outcome} AT ${Math.round(progress)}%` : `${Math.round(progress)}% TERM USED`,
    );
    set(
      term,
      "[data-event-term-end]",
      `EXP ${shortDate(trigger.dataset.expiresOn).toUpperCase()} · ${daysLeft}D ${resolvedOn ? "REMAINED" : "LEFT"}`,
    );
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

    const campaignId = trigger.dataset.campaignId;
    canvas.dataset.eventFocus = campaignId;
    canvas.querySelectorAll("[data-campaign-id], [data-lifecycle-id]").forEach((node) => {
      const nodeId = node.dataset.campaignId;
      if (nodeId === campaignId) node.dataset.eventActive = "true";
    });
    markerCard(trigger)?.querySelectorAll("[data-chart-ledger-event]").forEach((node) => {
      const nodeId = node.dataset.campaignId;
      if (nodeId === campaignId) node.dataset.eventActive = "true";
    });
  };

  const populateOption = (popover, trigger, symbol) => {
    const type = trigger.dataset.eventType;
    const outcome = (trigger.dataset.outcome || type).toUpperCase();
    const isOpenRoll = type === "rolled" && outcome === "OPEN";
    const contracts = number(trigger.dataset.contracts);
    const grossPremium = number(trigger.dataset.grossPremium);
    const buybackCost = number(trigger.dataset.buybackCost);
    const netCash = number(trigger.dataset.netCash);
    const campaign = trigger.dataset.campaignLabel;
    const side = trigger.dataset.optionSide === "put" ? "P" : "C";
    const heading = `${campaign}.${trigger.dataset.campaignLeg || 1} · ${eventTitles[type] || type.toUpperCase()} · ${shortDate(trigger.dataset.date)}`;
    const contract = `${contracts}× ${symbol} $${strikes.format(number(trigger.dataset.strike))}${side} · EXP ${shortDate(trigger.dataset.expiresOn)}`;
    let cashText = `${signedMoney(grossPremium)} received · ${money(trigger.dataset.premiumPerShare)}/sh`;
    let cashClass = "positive";
    let footer = "OPEN PREMIUM EVENT";

    if (type === "expired") {
      cashText = `${money(grossPremium)} kept · no close debit`;
      footer = `CAMPAIGN RESOLUTION · ${signedMoney(netCash)} LEG NET`;
    } else if (type === "closed" || (type === "rolled" && !isOpenRoll)) {
      cashText = `${signedMoney(-buybackCost)} close · ${signedMoney(netCash)} leg net`;
      cashClass = buybackCost > 0 ? "negative" : "positive";
      footer = `CAMPAIGN RESOLUTION · ${trigger.dataset.outcome.toUpperCase()}`;
    } else if (type === "assigned") {
      const multiplier = number(trigger.dataset.contractMultiplier || 100);
      const deliveredShares = trigger.dataset.assignmentShares
        ? number(trigger.dataset.assignmentShares)
        : contracts * multiplier;
      cashText = trigger.dataset.optionSide === "put"
        ? `${money(grossPremium)} kept · ${deliveredShares} shares acquired`
        : `${money(grossPremium)} kept · ${deliveredShares} shares called away`;
      footer = "CAMPAIGN RESOLUTION · ASSIGNED";
    } else if (isOpenRoll) {
      cashText = `${signedMoney(grossPremium)} received · ${money(trigger.dataset.premiumPerShare)}/sh`;
      footer = "OPEN ROLL LEG";
    } else if (trigger.dataset.linkedResolutionSequence) {
      footer = `LATER RESOLVED · ${trigger.dataset.outcome.toUpperCase()}`;
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
    const resolutionLabels = {
      Expired: "AT EXPIRATION",
      Assigned: "AT ASSIGNMENT",
      Closed: "AT CLOSE",
      Rolled: "AT ROLL",
    };
    setFirstFactDetail(
      popover,
      resolutionLabels[trigger.dataset.outcome],
      trigger.dataset.underlyingAtResolution
        ? money(trigger.dataset.underlyingAtResolution)
        : "",
    );
    set(popover, "[data-event-fact-two-label]", "STRIKE BUFFER");
    set(popover, "[data-event-fact-two-value]", `${number(trigger.dataset.strikeBuffer).toFixed(1)}%`);
    set(popover, "[data-event-fact-three-label]", "ENTRY TERM");
    set(popover, "[data-event-fact-three-value]", `${trigger.dataset.entryDte} DTE`);
    populateTerm(popover, trigger);
    populateValue(popover, trigger);
    set(
      popover,
      "[data-event-popover-link]",
      `${footer} · ${campaign} ${signedMoney(trigger.dataset.campaignNetCash)} · ${(trigger.dataset.campaignConfidence || "unknown").replaceAll("_", " ").toUpperCase()} LINK`,
    );
  };

  const populateShare = (popover, trigger, symbol) => {
    const action = trigger.dataset.shareTrade.toUpperCase();
    const grossBuys = number(trigger.dataset.grossBuys);
    const grossSells = number(trigger.dataset.grossSells);
    const heading = action === "FLAT" ? "SHARE ACTIVITY NETTED FLAT" : `NET SHARES ${action === "BUY" ? "BOUGHT" : "SOLD"}`;
    set(popover, "[data-event-popover-heading]", `${heading} · ${shortDate(trigger.dataset.date)}`);
    set(popover, "[data-event-popover-contract]", `${trigger.dataset.shares} NET ${symbol} SHARES`);
    const cash = popover.querySelector("[data-event-popover-cash]");
    if (cash) {
      cash.textContent = `${money(trigger.dataset.price)}/share`;
      cash.className = action === "BUY" ? "negative" : action === "SELL" ? "positive" : "";
    }
    set(popover, "[data-event-fact-one-label]", "ACTION");
    set(popover, "[data-event-fact-one-value]", action === "FLAT" ? "NET FLAT" : action);
    setFirstFactDetail(popover, "", "");
    set(popover, "[data-event-fact-two-label]", "PRICE");
    set(popover, "[data-event-fact-two-value]", money(trigger.dataset.price));
    set(popover, "[data-event-fact-three-label]", "DATE");
    set(popover, "[data-event-fact-three-value]", shortDate(trigger.dataset.date));
    hideTerm(popover);
    hideValue(popover);
    set(popover, "[data-event-popover-link]", `${grossBuys} BOUGHT · ${grossSells} SOLD · ONE DAILY INVENTORY MARKER`);
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
  document.querySelectorAll("[data-chart-shares]").forEach((button) => {
    button.addEventListener("click", () => {
      const chart = button.closest("[data-chart-workspace]");
      const showing = chart?.dataset.showShares === "true";
      if (!chart) return;
      chart.dataset.showShares = showing ? "false" : "true";
      button.setAttribute("aria-pressed", showing ? "false" : "true");
      button.textContent = showing ? "SHARES OFF" : "SHARES ON";
      if (showing && activeTrigger?.dataset.eventKind === "share") closeEvent();
    });
  });
})();
