(() => {
  const root = document.querySelector("[data-radar-console]");
  if (!root) return;

  const form = root.querySelector("[data-radar-form]");
  const policyForm = root.querySelector("[data-radar-policy-form]");
  const symbolInput = root.querySelector("[data-radar-symbol]");
  const idle = root.querySelector("[data-radar-idle]");
  const loading = root.querySelector("[data-radar-loading]");
  const result = root.querySelector("[data-radar-result]");
  const candidates = root.querySelector("[data-radar-candidates]");
  const empty = root.querySelector("[data-radar-empty-result]");
  const rules = root.querySelector("[data-radar-rules]");
  const rulesToggle = root.querySelector("[data-radar-rules-toggle]");
  const saveButton = root.querySelector("[data-radar-save]");
  const rollPanel = root.querySelector("[data-radar-roll-handoff]");
  const rollClear = root.querySelector("[data-radar-roll-clear]");
  const rollReturn = root.querySelector("[data-radar-roll-return]");
  const rollSourcePicker = root.querySelector("[data-radar-roll-source-picker]");
  const rollSourceRun = root.querySelector("[data-radar-roll-source-run]");
  const policySummary = root.querySelector("[data-radar-policy-summary]");
  let currentProjection = null;
  let rollHandoff = null;
  let savedSymbols = new Set(
    [...root.querySelectorAll("[data-radar-saved-list] [data-radar-symbol-chip]")].map(
      (item) => item.dataset.radarSymbolChip,
    ),
  );

  const mode = () => form.elements.mode.value;
  const canonicalSymbol = () => symbolInput.value.trim().toUpperCase();
  const setText = (selector, value) => {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  };
  const number = (value, digits = 1) => {
    if (value === null || value === undefined || value === "") return "—";
    return Number(value).toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  };
  const money = (value, digits = 2) =>
    value === null || value === undefined ? "—" : `$${number(value, digits)}`;
  const strikeMoney = (value) => {
    if (value === null || value === undefined || value === "") return "—";
    return `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  };
  const percent = (value, digits = 1) =>
    value === null || value === undefined ? "—" : `${Number(value) >= 0 ? "+" : ""}${number(value, digits)}%`;
  const dateLabel = (value) => {
    if (!value) return "—";
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "2-digit", year: "numeric" }).format(
      new Date(`${value}T12:00:00`),
    );
  };
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const rollComparisonFor = (projection, candidate) =>
    projection?.roll_review?.comparisons?.find(
      (comparison) => comparison.option_symbol === candidate.option_symbol,
    ) || null;
  const signedMoney = (value, digits = 2) => {
    const numeric = Number(value);
    return `${numeric >= 0 ? "+" : "−"}${money(Math.abs(numeric), digits)}`;
  };

  const readRollHandoff = () => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("review") !== "roll") return null;
    const symbol = (params.get("symbol") || "").trim().toUpperCase();
    const sourceOptionSymbol = (params.get("source") || "").trim();
    const requestedMode = params.get("mode") || "covered_call";
    const targetExpiration = params.get("targetExpiration") || null;
    const targetStrikeRaw = params.get("targetStrike");
    const targetStrike = targetStrikeRaw ? Number(targetStrikeRaw) : null;
    const hasOneTargetPart = Boolean(targetExpiration) !== Boolean(targetStrikeRaw);
    const returnAnchor = (params.get("returnAnchor") || "").trim();
    const origin = params.get("from");
    const invalid = (
      !/^[A-Z0-9.-]{1,16}$/.test(symbol)
      || !sourceOptionSymbol
      || sourceOptionSymbol.length > 64
      || !["covered_call", "cash_secured_put"].includes(requestedMode)
      || hasOneTargetPart
      || (targetExpiration && !/^\d{4}-\d{2}-\d{2}$/.test(targetExpiration))
      || (targetStrike !== null && (!Number.isFinite(targetStrike) || targetStrike <= 0))
      || (returnAnchor && !/^roll-option-[a-z0-9-]{1,72}$/.test(returnAnchor))
    );
    return {
      symbol,
      sourceOptionSymbol,
      mode: requestedMode,
      targetExpiration,
      targetStrike,
      origin: origin === "nibwick"
        ? "NIBWICK → RADAR"
        : origin === "roll-board" ? "ROLL BOARD → RADAR" : "ROLL REVIEW",
      returnAnchor,
      error: invalid ? "This roll link is incomplete. Choose the open option again." : null,
    };
  };

  const renderPendingRoll = () => {
    if (!rollHandoff) return;
    rollPanel.hidden = false;
    rollPanel.dataset.rollStatus = "pending";
    setText("[data-radar-roll-origin]", rollHandoff.origin);
    if (rollReturn) {
      rollReturn.hidden = !rollHandoff.returnAnchor;
      rollReturn.href = rollHandoff.returnAnchor
        ? `/workspaces/risk?from=radar#${encodeURIComponent(rollHandoff.returnAnchor)}`
        : "/workspaces/risk";
    }
    setText("[data-radar-roll-status]", "VERIFYING OPEN OPTION");
    setText("[data-radar-roll-source]", "CHECKING CURRENT POSITION");
    setText("[data-radar-roll-target]", rollHandoff.error
      ? "MISSING ROLL DETAILS"
      : rollHandoff.targetExpiration
        ? `${strikeMoney(rollHandoff.targetStrike)}${rollHandoff.mode === "cash_secured_put" ? "P" : "C"} · ${dateLabel(rollHandoff.targetExpiration)}`
        : "SEARCHING LATER CONTRACTS");
    setText("[data-radar-roll-target-quote]", rollHandoff.targetExpiration
      ? "Refreshing the replacement bid"
      : "Loading the nearby listed ladder");
    setText("[data-radar-roll-math-label]", "TWO-LEG CHECK");
    setText("[data-radar-roll-net]", "WAITING FOR CHAIN");
    setText("[data-radar-roll-net-detail]", "Buy old at ask · sell new at bid");
  };

  const renderRollReview = (review, errorMessage = null) => {
    if (!rollHandoff) {
      rollPanel.hidden = true;
      return;
    }
    rollPanel.hidden = false;
    if (!review) {
      rollPanel.dataset.rollStatus = errorMessage ? "unavailable" : "pending";
      setText("[data-radar-roll-status]", errorMessage ? "ROLL CHECK STOPPED" : "VERIFYING OPEN OPTION");
      if (errorMessage) {
        setText("[data-radar-roll-net]", "NO COMPARISON");
        setText("[data-radar-roll-note]", errorMessage);
      }
      return;
    }
    const matched = review.status === "matched";
    const sourceFresh = review.source_quote_status === "fresh_chain";
    const hasCandidates = review.status !== "no_candidates";
    rollPanel.dataset.rollStatus = review.status;
    rollPanel.dataset.rollQuoteStatus = review.source_quote_status;
    setText(
      "[data-radar-roll-status]",
      matched
        ? sourceFresh ? "BOTH LEGS REFRESHED" : "TARGET REFRESHED · SOURCE FROM DESK"
        : hasCandidates ? "TARGET NOT RETURNED" : "NO ELIGIBLE REPLACEMENT",
    );
    const side = review.source_option_side === "put" ? "P" : "C";
    setText(
      "[data-radar-roll-source]",
      `${strikeMoney(review.source_strike)}${side} · ${dateLabel(review.source_expiration_date)} · ${review.source_contracts}X`,
    );
    setText(
      "[data-radar-roll-source-quote]",
      `${sourceFresh ? "Refreshed-chain" : "Latest desk"} buy-to-close ask · ${money(review.source_close_ask_per_share)}`,
    );
    setText("[data-radar-roll-target]", hasCandidates
      ? `${strikeMoney(review.target_strike)}${side} · ${dateLabel(review.target_expiration_date)}`
      : "NO CLEAN CHOICE RETURNED");
    setText(
      "[data-radar-roll-target-quote]",
      matched
        ? `Sell to open at ${money(review.target_bid_per_share)} bid`
        : hasCandidates ? "Not present in the refreshed comparison set" : "Try a wider term or review the open option later",
    );
    if (matched) {
      const net = Number(review.net_roll_per_share);
      const total = Number(review.net_roll_cash);
      setText(
        "[data-radar-roll-math-label]",
        sourceFresh ? "REFRESHED TWO-LEG MATH" : "MIXED-TIME CHECK",
      );
      setText(
        "[data-radar-roll-net]",
        `${net >= 0 ? "+" : "−"}${money(Math.abs(net))}/SH · ${total >= 0 ? "+" : "−"}${money(Math.abs(total), 0)}`,
      );
      setText(
        "[data-radar-roll-net-detail]",
        `${signedMoney(review.strike_lift_per_share)} strike · ${review.added_days >= 0 ? "+" : "−"}${Math.abs(review.added_days)} days`,
      );
      setText(
        "[data-radar-roll-note]",
        sourceFresh
          ? "Both legs were refreshed together. Review the highlighted contract; nothing here can place an order."
          : "The replacement quote was refreshed; the close ask is from your latest desk sync. Treat this net as planning math until both legs refresh together.",
      );
    } else if (hasCandidates) {
      setText("[data-radar-roll-math-label]", "TWO-LEG CHECK");
      setText("[data-radar-roll-net]", "NO FRESH MATCH");
      setText("[data-radar-roll-net-detail]", "The earlier Nibwick quote is not being reused");
      setText(
        "[data-radar-roll-note]",
        "The source option is still open, but Schwab did not return that exact replacement in this scan. Current alternatives remain below.",
      );
    } else {
      setText("[data-radar-roll-math-label]", "FRESH CHAIN CHECK");
      setText("[data-radar-roll-net]", "NO CLEAN ROLL");
      setText("[data-radar-roll-net-detail]", "No later directional contract cleared the current comparison rules");
      setText("[data-radar-roll-note]", "The source option is still open. Radar found no eligible replacement in this scan; that is a result, not a missing action.");
    }
  };

  const setBusy = (busy) => {
    idle.hidden = true;
    loading.hidden = !busy;
    result.hidden = busy;
    form.querySelector("[data-radar-run]").disabled = busy;
  };

  const request = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message || "The request could not be completed.");
    }
    return payload;
  };

  const syncPutRules = () => {
    const isPut = mode() === "cash_secured_put";
    root.querySelectorAll("[data-put-rule]").forEach((node) => {
      node.hidden = !isPut;
    });
    const roomLabel = root.querySelector("[data-radar-room-rule-label]");
    if (roomLabel) roomLabel.textContent = isPut ? "MIN DISCOUNT %" : "MIN ROOM %";
  };

  const loadPolicy = async () => {
    const symbol = canonicalSymbol();
    if (!symbol) return;
    try {
      const policy = await request(`/api/v1/radar/policies/${encodeURIComponent(symbol)}?mode=${mode()}`);
      Object.entries(policy).forEach(([key, value]) => {
        const field = policyForm.elements[key];
        if (field) field.value = value ?? "";
      });
    } catch (_) {
      // A lookup will surface actionable source errors; policy loading stays unobtrusive.
    }
  };

  const renderCandidate = (candidate, index, projection) => {
    const card = element(
      "article",
      `radar-candidate${candidate.clears_all_rules ? "" : " research-only"}`,
    );
    card.dataset.radarCandidateIndex = String(index);
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.setAttribute("aria-selected", "false");
    card.setAttribute(
      "aria-label",
      `Comparison ${index + 1}: ${strikeMoney(candidate.strike)} strike, ${candidate.days_to_expiration} days to expiration`,
    );
    const rollComparison = rollComparisonFor(projection, candidate);
    const candidateLabel = candidate.label
      ? candidate.label.replaceAll("_", " ").toUpperCase()
      : "ROLL CHOICE";
    const header = element("header");
    header.append(
      element("i", "radar-candidate-number", String(index + 1)),
      element(
        "b",
        "",
        rollComparison
          ? candidateLabel
          : candidate.clears_all_rules
            ? candidateLabel === "ROLL CHOICE" ? "CLEARED" : candidateLabel
            : "RESEARCH ONLY",
      ),
      element("span", "", `${dateLabel(candidate.expiration_date)} · ${candidate.days_to_expiration} DTE`),
    );
    const hero = element("div", "radar-candidate-hero");
    const strike = element("div");
    strike.append(
      element("span", "", mode() === "cash_secured_put" ? "STRIKE / DISCOUNT" : "STRIKE / ROOM"),
      element("strong", "", strikeMoney(candidate.strike)),
      element(
        "small",
        "",
        `${money(Math.abs(Number(candidate.room_dollars)), 2)} / ${number(Math.abs(Number(candidate.room_percent)), 1)}% ${mode() === "cash_secured_put" ? "below" : "above"} spot`,
      ),
    );
    const credit = element("div");
    credit.append(
      element("span", "", "1-CONTRACT BID CREDIT"),
      element("strong", "positive", money(candidate.premium_per_contract, 0)),
      element(
        "small",
        "radar-credit-pace",
        `${candidate.days_to_expiration} DTE · ${money(candidate.bid_credit_per_calendar_day, 2)} / CAL DAY`,
      ),
      element("small", "", `${money(candidate.bid)} bid · ${money(candidate.midpoint)} midpoint`),
    );
    hero.append(strike, credit);
    const rollStrip = rollComparison ? element("div", "radar-candidate-roll") : null;
    if (rollStrip) {
      const sourceSide = projection.roll_review.source_option_side === "put" ? "P" : "C";
      const net = Number(rollComparison.net_roll_per_share);
      const total = Number(rollComparison.net_roll_cash);
      rollStrip.dataset.rollTone = net > 0 ? "credit" : net < 0 ? "debit" : "flat";
      const economics = element("div");
      economics.append(
        element("span", "", `ROLL NET · ${projection.roll_review.source_contracts}X`),
        element(
          "strong",
          "",
          `${net > 0 ? "CREDIT" : net < 0 ? "DEBIT" : "FLAT"} ${signedMoney(net)}/SH · ${signedMoney(total, 0)} TOTAL`,
        ),
        element(
          "small",
          "",
          `BUY ${strikeMoney(projection.roll_review.source_strike)}${sourceSide} @ ${money(projection.roll_review.source_close_ask_per_share)} · SELL THIS @ ${money(rollComparison.bid_per_share)}`,
        ),
      );
      const change = element("div");
      change.append(
        element("span", "", "WHAT CHANGES"),
        element(
          "b",
          "",
          `${signedMoney(rollComparison.strike_change_per_share)} STRIKE · ${rollComparison.added_days >= 0 ? "+" : "−"}${Math.abs(rollComparison.added_days)} DAYS`,
        ),
        element(
          "small",
          "",
          `FROM ${strikeMoney(projection.roll_review.source_strike)}${sourceSide} · ${dateLabel(projection.roll_review.source_expiration_date)}`,
        ),
      );
      rollStrip.append(economics, change);
    }
    const grid = element("div", "radar-candidate-grid");
    const facts = [
      ["PREMIUM APR · SIMPLE", `${number(candidate.simple_annualized_rate_percent, 1)}%`],
      ["EXPECTED MOVE", candidate.expected_move === null ? "—" : money(candidate.expected_move)],
      ["ROOM / MOVE", candidate.strike_distance_in_moves === null ? "—" : `${number(candidate.strike_distance_in_moves, 2)}×`],
      ["CONTRACT DELTA", candidate.delta === null ? "—" : number(candidate.delta, 2)],
      ["IV", candidate.implied_volatility === null ? "—" : `${number(candidate.implied_volatility, 1)}%`],
      ["BID / ASK WIDTH", `${number(candidate.spread_percent, 1)}%`],
      ["OPEN INTEREST", candidate.open_interest ?? "—"],
      ["VOLUME", candidate.volume ?? "—"],
      [
        "READY SIZE",
        candidate.clears_all_rules
          ? `${candidate.eligible_contracts} contract${candidate.eligible_contracts === 1 ? "" : "s"}`
          : "0 · SETUP",
      ],
    ];
    facts.forEach(([label, value]) => {
      const cell = element("div");
      cell.append(element("span", "", label), element("b", "", String(value)));
      grid.append(cell);
    });
    const footer = element("footer", "", candidate.reasons.join(" · "));
    card.append(header, hero);
    if (rollStrip) card.append(rollStrip);
    card.append(grid, footer);
    return card;
  };

  const renderMethod = (projection) => {
    const body = root.querySelector("[data-radar-method-body]");
    body.replaceChildren();
    projection.candidates.forEach((candidate) => {
      candidate.gates.forEach((gate) => {
        const row = element("div", `radar-evidence ${gate.status}`);
        row.append(element("b", "", `${gate.status.toUpperCase()} · ${gate.label}`), element("span", "", gate.detail));
        body.append(row);
      });
    });
    if (!projection.candidates.length) {
      const row = element("div", "radar-evidence unknown");
      row.append(element("b", "", "NO CLEARING CONTRACT"), element("span", "", projection.reasons.join(" ")));
      body.append(row);
    }
  };

  const renderProjection = (projection) => {
    currentProjection = projection;
    loading.hidden = true;
    result.hidden = false;
    setText("[data-radar-verdict]", projection.verdict);
    setText("[data-radar-state]", projection.state.toUpperCase().replaceAll("_", " "));
    setText("[data-radar-kicker]", `${projection.symbol || "RADAR"} · ${projection.mode === "covered_call" ? "COVERED CALL" : "CASH-SECURED PUT"}`);
    setText("[data-radar-headline]", projection.headline);
    setText("[data-radar-reasons]", projection.reasons.join(" "));
    setText("[data-radar-observed]", projection.observed_at ? `QUOTE ${new Date(projection.observed_at).toLocaleString()}` : "NO QUOTE TIME");
    setText("[data-radar-spot]", money(projection.underlying_price));
    setText("[data-radar-symbol-label]", projection.symbol || "—");
    setText("[data-radar-five-day]", percent(projection.five_day_move_percent));
    setText("[data-radar-twenty-day]", percent(projection.twenty_day_move_percent));
    setText("[data-radar-range]", projection.range_position_percent === null ? "—" : `${number(projection.range_position_percent, 1)}%`);
    const size = projection.mode === "covered_call"
      ? projection.account.available_call_lots
      : Math.min(
          projection.policy.allowed_contracts,
          Math.max(0, ...projection.candidates.map((candidate) => candidate.eligible_contracts)),
        );
    setText("[data-radar-size]", `${size} LOT${size === 1 ? "" : "S"}`);
    setText(
      "[data-radar-size-note]",
      projection.mode === "covered_call"
        ? "UNCOMMITTED 100-SHARE LOTS"
        : `${money(projection.account.reserved_cash, 0)} ACCOUNT CASH · ${money(projection.policy.reserved_cash, 0)} POLICY`,
    );
    setText("[data-radar-rejected]", String(projection.rejected_count));
    saveButton.textContent = savedSymbols.has(projection.symbol) ? "★ SAVED" : "☆ SAVE TICKER";
    const warning = root.querySelector("[data-radar-warning]");
    warning.hidden = !projection.warnings.length;
    warning.textContent = projection.warnings.join(" · ");
    candidates.replaceChildren(
      ...projection.candidates.map(
        (candidate, index) => renderCandidate(candidate, index, projection),
      ),
    );
    empty.hidden = projection.candidates.length > 0;
    empty.textContent = projection.candidates.length ? "" : projection.reasons.join(" ");
    renderMethod(projection);
    window.IncooomingRadarMap?.render(root, projection);
    renderRollReview(
      projection.roll_review,
      rollHandoff && !projection.roll_review
        ? "Radar loaded the ticker, but the roll context did not arrive. Reopen this check from Nibwick."
        : null,
    );
    const isRollReview = Boolean(projection.roll_review);
    setText(
      "[data-radar-comparison-kicker]",
      isRollReview ? "NEARBY LISTED LADDER" : "CHAIN COMPARISONS",
    );
    setText(
      "[data-radar-comparison-title]",
      isRollReview
        ? `Later ${projection.mode === "cash_secured_put" ? "puts" : "calls"}`
        : "Comparisons",
    );
    if (
      policySummary
      && Number.isFinite(Number(projection.policy?.minimum_dte))
      && Number.isFinite(Number(projection.policy?.maximum_dte))
    ) {
      policySummary.textContent = isRollReview
        ? `${projection.mode === "cash_secured_put" ? "SAME OR LOWER STRIKES" : "HIGHER STRIKES"} · LATER EXPIRATIONS · NEARBY LISTED LADDER`
        : `${projection.policy.minimum_dte}–${projection.policy.maximum_dte} DTE · ${number(projection.policy.minimum_annualized_rate_percent, 1)}% MINIMUM SIMPLE APR · NO FILLER`;
    }
    root.querySelectorAll("[data-radar-candidate-index]").forEach((card) => {
      const candidate = projection.candidates[Number(card.dataset.radarCandidateIndex)];
      const isTarget = Boolean(
        rollHandoff
        && candidate
        && Number(candidate.strike) === rollHandoff.targetStrike
        && candidate.expiration_date === rollHandoff.targetExpiration
      );
      card.classList.toggle("is-roll-target", isTarget);
    });
    if (rollHandoff && projection.roll_review?.status === "matched") {
      const targetIndex = projection.candidates.findIndex(
        (candidate) => Number(candidate.strike) === Number(projection.roll_review.target_strike)
          && candidate.expiration_date === projection.roll_review.target_expiration_date,
      );
      if (targetIndex >= 0) window.IncooomingRadarMap?.select(root, targetIndex);
      setText(
        "[data-radar-size-note]",
        projection.mode === "covered_call"
          ? `SOURCE CALL RELEASES ${projection.roll_review.source_contracts} COVERED LOT${projection.roll_review.source_contracts === 1 ? "" : "S"} FOR THIS REVIEW`
          : `SOURCE PUT SETS THE CONTRACT SIZE FOR THIS ${projection.roll_review.source_contracts}X REVIEW`,
      );
    }
  };

  const renderFailure = (error) => {
    renderProjection({
      verdict: "DATA CHECK", state: "failed", symbol: canonicalSymbol(), mode: mode(),
      headline: error.message, reasons: ["Your account ledger and scheduled sync were not changed."],
      observed_at: null, underlying_price: null, five_day_move_percent: null,
      twenty_day_move_percent: null, range_position_percent: null, rejected_count: 0,
      account: { available_call_lots: 0 }, policy: { allowed_contracts: 0, reserved_cash: 0 },
      warnings: [], candidates: [],
    });
    renderRollReview(null, error.message);
  };

  const scan = async () => {
    const symbol = canonicalSymbol();
    if (!symbol) { symbolInput.focus(); return; }
    symbolInput.value = symbol;
    setBusy(true);
    try {
      const payload = { symbol, mode: mode() };
      if (rollHandoff && !rollHandoff.error) {
        payload.roll = {
          source_option_symbol: rollHandoff.sourceOptionSymbol,
        };
        if (rollHandoff.targetExpiration) {
          payload.roll.target_expiration = rollHandoff.targetExpiration;
          payload.roll.target_strike = rollHandoff.targetStrike;
        }
      }
      renderProjection(await request("/api/v1/radar/lookups", {
        method: "POST",
        body: JSON.stringify(payload),
      }));
    } catch (error) {
      renderFailure(error);
    } finally {
      form.querySelector("[data-radar-run]").disabled = false;
    }
  };

  form.addEventListener("submit", (event) => { event.preventDefault(); scan(); });
  form.addEventListener("change", () => { syncPutRules(); loadPolicy(); });
  symbolInput.addEventListener("blur", loadPolicy);
  root.addEventListener("click", (event) => {
    const card = event.target.closest("[data-radar-candidate-index]");
    if (card) {
      window.IncooomingRadarMap?.select(root, Number(card.dataset.radarCandidateIndex));
      return;
    }
    const chip = event.target.closest("[data-radar-symbol-chip]");
    if (!chip) return;
    symbolInput.value = chip.dataset.radarSymbolChip;
    loadPolicy().then(scan);
  });
  root.addEventListener("keydown", (event) => {
    const card = event.target.closest("[data-radar-candidate-index]");
    if (!card || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    window.IncooomingRadarMap?.select(root, Number(card.dataset.radarCandidateIndex));
  });
  rulesToggle.addEventListener("click", () => {
    const expanded = rulesToggle.getAttribute("aria-expanded") === "true";
    rulesToggle.setAttribute("aria-expanded", String(!expanded));
    rulesToggle.querySelector("span").textContent = expanded ? "+" : "−";
    rules.hidden = expanded;
    if (!expanded) loadPolicy();
  });
  policyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const symbol = canonicalSymbol();
    if (!symbol) { symbolInput.focus(); return; }
    const values = Object.fromEntries(new FormData(policyForm));
    const numeric = ["minimum_dte", "maximum_dte", "minimum_annualized_rate_percent", "minimum_strike_distance_percent", "minimum_open_interest", "minimum_volume", "maximum_quote_age_seconds", "allowed_contracts", "reserved_cash"];
    numeric.forEach((key) => { values[key] = Number(values[key] || 0); });
    values.minimum_strike = values.minimum_strike ? Number(values.minimum_strike) : null;
    values.maximum_effective_entry = values.maximum_effective_entry ? Number(values.maximum_effective_entry) : null;
    values.maximum_spread_percent = values.maximum_spread_percent ? Number(values.maximum_spread_percent) : null;
    values.maximum_five_day_move_percent = values.maximum_five_day_move_percent ? Number(values.maximum_five_day_move_percent) : null;
    values.mode = mode();
    try {
      await request(`/api/v1/radar/policies/${encodeURIComponent(symbol)}`, { method: "PUT", body: JSON.stringify(values) });
      rules.hidden = true;
      rulesToggle.setAttribute("aria-expanded", "false");
      rulesToggle.querySelector("span").textContent = "+";
      scan();
    } catch (error) { renderFailure(error); }
  });
  saveButton.addEventListener("click", async () => {
    if (!currentProjection?.symbol) return;
    const symbol = currentProjection.symbol;
    if (savedSymbols.has(symbol)) {
      await request(`/api/v1/radar/saved-symbols/${encodeURIComponent(symbol)}`, { method: "DELETE" });
      savedSymbols.delete(symbol);
    } else {
      await request("/api/v1/radar/saved-symbols", { method: "POST", body: JSON.stringify({ symbol }) });
      savedSymbols.add(symbol);
    }
    saveButton.textContent = savedSymbols.has(symbol) ? "★ SAVED" : "☆ SAVE TICKER";
  });
  rollClear.addEventListener("click", () => {
    rollHandoff = null;
    rollPanel.hidden = true;
    const cleanUrl = new URL(window.location.href);
    ["review", "source", "targetExpiration", "targetStrike", "from", "returnAnchor"].forEach((key) => cleanUrl.searchParams.delete(key));
    window.history.replaceState({}, "", cleanUrl);
  });
  rollSourceRun?.addEventListener("click", () => {
    const selected = rollSourcePicker?.selectedOptions[0];
    if (!selected) return;
    const symbol = selected.dataset.symbol;
    const selectedMode = selected.dataset.mode;
    const sourceOptionSymbol = selected.value;
    symbolInput.value = symbol;
    form.elements.mode.value = selectedMode;
    rollHandoff = {
      symbol,
      sourceOptionSymbol,
      mode: selectedMode,
      targetExpiration: null,
      targetStrike: null,
      origin: "ROLL REVIEW",
      returnAnchor: "",
      error: null,
    };
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("symbol", symbol);
    nextUrl.searchParams.set("mode", selectedMode);
    nextUrl.searchParams.set("review", "roll");
    nextUrl.searchParams.set("source", sourceOptionSymbol);
    ["targetExpiration", "targetStrike", "from", "returnAnchor"].forEach((key) => nextUrl.searchParams.delete(key));
    window.history.replaceState({}, "", nextUrl);
    renderPendingRoll();
    syncPutRules();
    loadPolicy().then(scan);
  });
  rollHandoff = readRollHandoff();
  if (rollHandoff) {
    symbolInput.value = rollHandoff.symbol;
    form.elements.mode.value = rollHandoff.mode;
    if (rollSourcePicker) {
      const sourceChoice = [...rollSourcePicker.options].find(
        (option) => option.value === rollHandoff.sourceOptionSymbol,
      );
      if (sourceChoice) rollSourcePicker.value = sourceChoice.value;
    }
    renderPendingRoll();
    syncPutRules();
    if (rollHandoff.error) {
      renderRollReview(null, rollHandoff.error);
    } else {
      loadPolicy().then(scan);
    }
  } else {
    syncPutRules();
  }
})();
