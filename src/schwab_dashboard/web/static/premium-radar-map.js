(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const state = new WeakMap();
  const boundRoots = new WeakSet();

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
  const signedMoney = (value, digits = 2) => {
    const numeric = Number(value);
    return `${numeric >= 0 ? "+" : "−"}${money(Math.abs(numeric), digits)}`;
  };
  const shortDate = (value) =>
    new Intl.DateTimeFormat(undefined, { month: "short", day: "2-digit" })
      .format(new Date(`${value}T12:00:00`))
      .toUpperCase();
  const svgNode = (tag, attributes = {}, text) => {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const addText = (parent, className, xValue, yValue, text, anchor = "start") => {
    parent.append(svgNode("text", {
      class: className,
      x: xValue,
      y: yValue,
      "text-anchor": anchor,
    }, text));
  };
  const setText = (root, selector, value) => {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  };
  const nullableMetric = (value, formatter) =>
    value === null || value === undefined ? "—" : formatter(value);

  const dateAtFraction = (start, end, fraction) => {
    const startMs = new Date(`${start}T12:00:00`).getTime();
    const endMs = new Date(`${end}T12:00:00`).getTime();
    return new Date(startMs + ((endMs - startMs) * fraction));
  };

  const geometryFor = (stage) => {
    const bounds = stage.getBoundingClientRect();
    const width = Math.max(Math.round(bounds.width), 620);
    const height = Math.max(Math.round(bounds.height), 300);
    const x = (value) => (Number(value) / 100) * width;
    const y = (value) => (Number(value) / 100) * height;
    return {
      width,
      height,
      x,
      y,
      plotLeft: x(5),
      plotRight: x(90),
      plotTop: y(7),
      plotBottom: y(84),
      dateBaseline: y(94.5),
    };
  };

  const renderTimeGrid = (svg, map, geometry, expanded) => {
    const { x, y, plotTop, plotBottom } = geometry;
    const fractions = expanded ? [0, 0.2, 0.4, 0.6, 0.8, 1] : [0, 0.5, 1];
    fractions.forEach((fraction) => {
      const xPercent = 5 + (85 * fraction);
      const tickX = x(xPercent);
      svg.append(svgNode("line", {
        class: "map-time-grid",
        x1: tickX,
        y1: plotTop,
        x2: tickX,
        y2: plotBottom,
      }));
      const label = new Intl.DateTimeFormat(undefined, { month: "short", day: "2-digit" })
        .format(dateAtFraction(map.history_start, map.future_end, fraction))
        .toUpperCase();
      const anchor = fraction === 0 ? "start" : (fraction === 1 ? "end" : "middle");
      addText(svg, "map-date-label", tickX, y(94.5), label, anchor);
    });
  };

  const syncIndicatorControls = (root, current) => {
    root.querySelectorAll("[data-radar-indicator]").forEach((button) => {
      const key = button.dataset.radarIndicator;
      const active = Boolean(current.indicators[key]);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  };

  const renderIndicators = (root, current) => {
    window.IncooomingRadarIndicators?.render(
      root,
      current.projection,
      current.indicators,
      current.expanded,
    );
  };

  const renderSvg = (root, projection, selectedIndex) => {
    const map = projection.expiration_map;
    const selected = map.candidates[selectedIndex];
    const stage = root.querySelector("[data-radar-map-stage]");
    const panel = root.querySelector("[data-radar-map-panel]");
    const expanded = panel.classList.contains("is-expanded");
    const geometry = geometryFor(stage);
    const { width, height, x, y, plotLeft, plotRight, plotTop, plotBottom } = geometry;
    const svg = svgNode("svg", {
      class: `radar-expiry-svg ${projection.mode === "covered_call" ? "call-map" : "put-map"}`,
      viewBox: `0 0 ${width} ${height}`,
      role: "group",
      "aria-label": `${projection.symbol} option expiration map. Select a numbered contract for details.`,
      preserveAspectRatio: "xMidYMid meet",
    });

    const todayX = x(map.spot_x_percent);
    svg.append(svgNode("rect", {
      class: "map-history-zone",
      x: plotLeft,
      y: plotTop,
      width: Math.max(todayX - plotLeft, 1),
      height: plotBottom - plotTop,
    }));
    svg.append(svgNode("rect", {
      class: "map-forward-zone",
      x: todayX,
      y: plotTop,
      width: Math.max(plotRight - todayX, 1),
      height: plotBottom - plotTop,
    }));
    addText(svg, "map-zone-label", plotLeft + 5, plotTop + 12, "OBSERVED DAILY CLOSES");
    addText(svg, "map-zone-label", todayX + 5, plotTop + 12, "OPTION HORIZON");

    renderTimeGrid(svg, map, geometry, expanded);
    map.axis_labels.forEach((tick) => {
      const tickY = y(tick.y_percent);
      svg.append(svgNode("line", { class: "map-grid", x1: plotLeft, y1: tickY, x2: plotRight, y2: tickY }));
      addText(svg, "map-axis-label", x(91.4), tickY + 4, money(tick.price, 0));
    });

    const strikeY = y(selected.y_percent);
    const expiryX = x(selected.x_percent);
    const zoneY = projection.mode === "covered_call" ? plotTop : strikeY;
    const zoneHeight = projection.mode === "covered_call" ? strikeY - plotTop : plotBottom - strikeY;
    svg.append(svgNode("rect", {
      class: "map-itm-zone",
      x: todayX,
      y: zoneY,
      width: Math.max(expiryX - todayX, 1),
      height: Math.max(zoneHeight, 1),
    }));

    if (
      selected.expected_move_low_y_percent !== null
      && selected.expected_move_high_y_percent !== null
    ) {
      svg.append(svgNode("polygon", {
        class: "map-move-cone",
        points: `${todayX},${y(map.spot_y_percent)} ${expiryX},${y(selected.expected_move_high_y_percent)} ${expiryX},${y(selected.expected_move_low_y_percent)}`,
      }));
      svg.append(svgNode("line", {
        class: "map-move-edge",
        x1: todayX,
        y1: y(map.spot_y_percent),
        x2: expiryX,
        y2: y(selected.expected_move_high_y_percent),
      }));
      svg.append(svgNode("line", {
        class: "map-move-edge",
        x1: todayX,
        y1: y(map.spot_y_percent),
        x2: expiryX,
        y2: y(selected.expected_move_low_y_percent),
      }));
    }

    svg.append(svgNode("line", {
      class: "map-today",
      x1: todayX,
      y1: plotTop,
      x2: todayX,
      y2: plotBottom,
    }));
    const compressedHorizon = expiryX - todayX < 105;
    addText(
      svg,
      "map-today-label",
      todayX + (compressedHorizon ? -5 : 0),
      y(89),
      `TODAY ${shortDate(map.as_of)}`,
      compressedHorizon ? "end" : "middle",
    );

    if (map.price_points.length > 1) {
      svg.append(svgNode("polyline", {
        class: "map-price-path",
        points: map.price_points.map((point) => `${x(point.x_percent)},${y(point.y_percent)}`).join(" "),
      }));
    }

    svg.append(svgNode("line", {
      class: "map-expiry-guide",
      x1: expiryX,
      y1: Math.min(strikeY, plotBottom),
      x2: expiryX,
      y2: plotBottom,
    }));
    addText(
      svg,
      "map-expiry-label",
      expiryX + (compressedHorizon ? 5 : 0),
      y(89),
      `EXP ${shortDate(selected.expiration_date)} · ${selected.days_to_expiration} DTE`,
      compressedHorizon ? "start" : "middle",
    );

    map.candidates.forEach((candidate, index) => {
      const candidateY = y(candidate.y_percent);
      const candidateX = x(candidate.x_percent);
      const labelY = y(candidate.label_y_percent);
      const selectedClass = index === selectedIndex ? " selected" : "";
      const researchClass = candidate.clears_all_rules ? "" : " research";
      svg.append(svgNode("line", {
        class: `map-strike-line${selectedClass}${researchClass}`,
        x1: todayX,
        y1: candidateY,
        x2: candidateX,
        y2: candidateY,
      }));
      if (Math.abs(labelY - candidateY) > 1) {
        svg.append(svgNode("line", {
          class: `map-label-connector${selectedClass}`,
          x1: candidateX,
          y1: candidateY,
          x2: candidateX,
          y2: labelY,
        }));
      }

      const putCall = projection.mode === "covered_call" ? "C" : "P";
      const placeLeft = candidateX > width * 0.76;
      const target = svgNode("g", {
        class: "map-contract-target",
        role: "button",
        tabindex: "0",
        "aria-pressed": String(index === selectedIndex),
        "aria-label": `Comparison ${candidate.sequence}: ${strikeMoney(candidate.strike)} ${putCall === "C" ? "call" : "put"}, ${candidate.days_to_expiration} days to expiration`,
        "data-radar-map-index": index,
      });
      target.append(svgNode("rect", {
        x: candidateX - 15,
        y: labelY - 15,
        width: 30,
        height: 30,
        fill: "transparent",
      }));
      target.append(svgNode("rect", {
        class: `map-contract-marker${selectedClass}${researchClass}`,
        x: candidateX - 10,
        y: labelY - 10,
        width: 20,
        height: 20,
      }));
      addText(target, `map-contract-number${selectedClass}`, candidateX, labelY + 4, String(candidate.sequence), "middle");
      addText(
        target,
        `map-contract-label${selectedClass}`,
        candidateX + (placeLeft ? -16 : 16),
        labelY + 4,
        `${strikeMoney(candidate.strike)}${putCall} · ${candidate.days_to_expiration}D`,
        placeLeft ? "end" : "start",
      );
      addText(
        target,
        `map-contract-date${selectedClass}`,
        candidateX + (placeLeft ? -16 : 16),
        labelY + 15,
        `EXP ${shortDate(candidate.expiration_date)}`,
        placeLeft ? "end" : "start",
      );
      svg.append(target);
    });

    if (projection.mode === "cash_secured_put" && selected.effective_entry_y_percent !== null) {
      const entryY = y(selected.effective_entry_y_percent);
      svg.append(svgNode("line", {
        class: "map-effective-entry",
        x1: todayX,
        y1: entryY,
        x2: expiryX,
        y2: entryY,
      }));
      addText(svg, "map-entry-label", expiryX - 5, entryY - 5, `ENTRY AFTER CREDIT ${money(selected.effective_entry, 2)}`, "end");
    }

    svg.append(svgNode("circle", {
      class: "map-spot-dot",
      cx: todayX,
      cy: y(map.spot_y_percent),
      r: 5,
    }));
    addText(svg, "map-spot-label", todayX - 9, y(map.spot_y_percent) - 9, `NOW ${money(map.spot, 2)}`, "end");
    addText(svg, "map-session-label", plotLeft, y(89), `${map.price_points.length} SESSIONS`);
    addText(
      svg,
      "map-itm-label",
      (todayX + expiryX) / 2,
      projection.mode === "covered_call" ? plotTop + 17 : plotBottom - 10,
      projection.mode === "covered_call" ? "CALL ITM ABOVE STRIKE" : "PUT ITM BELOW STRIKE",
      "middle",
    );
    stage.replaceChildren(svg);
  };

  const updateReadout = (root, projection, selectedIndex) => {
    const candidate = projection.candidates[selectedIndex];
    const mapCandidate = projection.expiration_map.candidates[selectedIndex];
    const isCall = projection.mode === "covered_call";
    const rollComparison = projection.roll_review?.comparisons?.find(
      (comparison) => comparison.option_symbol === candidate.option_symbol,
    );
    setText(root, "[data-radar-map-position]", `${selectedIndex + 1} / ${projection.candidates.length}`);
    setText(root, "[data-radar-map-selection]", `#${selectedIndex + 1} · ${strikeMoney(candidate.strike)}${isCall ? "C" : "P"} · ${candidate.days_to_expiration} DTE`);
    setText(root, "[data-radar-map-premium]", `${money(candidate.premium_per_contract, 0)} BID · ${money(candidate.bid_credit_per_calendar_day, 2)}/DAY`);
    setText(root, "[data-radar-map-premium-note]", `${number(candidate.simple_annualized_rate_percent, 1)}% simple APR · expires ${shortDate(candidate.expiration_date)}`);
    const rollRow = root.querySelector("[data-radar-map-roll-row]");
    rollRow.hidden = !rollComparison;
    if (rollComparison) {
      const sourceSide = projection.roll_review.source_option_side === "put" ? "P" : "C";
      const net = Number(rollComparison.net_roll_per_share);
      setText(root, "[data-radar-map-roll-label]", `ROLL NET · ${projection.roll_review.source_contracts}X`);
      setText(
        root,
        "[data-radar-map-roll-net]",
        `${net > 0 ? "CREDIT" : net < 0 ? "DEBIT" : "FLAT"} ${signedMoney(net)}/SH · ${signedMoney(rollComparison.net_roll_cash, 0)} TOTAL`,
      );
      setText(
        root,
        "[data-radar-map-roll-detail]",
        `From ${strikeMoney(projection.roll_review.source_strike)}${sourceSide} · ${signedMoney(rollComparison.strike_change_per_share)} strike · ${rollComparison.added_days >= 0 ? "+" : "−"}${Math.abs(rollComparison.added_days)} days`,
      );
      rollRow.dataset.rollTone = net > 0 ? "credit" : net < 0 ? "debit" : "flat";
    } else {
      delete rollRow.dataset.rollTone;
    }
    setText(root, "[data-radar-map-boundary]", `${money(candidate.strike, 2)} · ${isCall ? "ITM ABOVE" : "ITM BELOW"}`);
    setText(root, "[data-radar-map-outcome]", isCall
      ? "Above this strike at expiration, 100 shares per contract may be called away."
      : "Below this strike at expiration, 100 shares per contract may be assigned to you.");
    setText(root, "[data-radar-map-room]", `${money(candidate.room_dollars, 2)} · ${number(candidate.room_percent, 1)}%`);
    setText(root, "[data-radar-map-room-note]", isCall
      ? "Current stock price to the call strike."
      : mapCandidate.effective_entry === null
        ? "Current stock price to the put strike."
        : `Effective stock entry after bid credit: ${money(mapCandidate.effective_entry, 2)}.`);
    setText(root, "[data-radar-map-move]", candidate.expected_move === null
      ? "UNAVAILABLE"
      : `±${money(candidate.expected_move, 2)} · ${number(candidate.strike_distance_in_moves, 2)}× TO STRIKE`);
    setText(root, "[data-radar-map-move-note]", "One expected-move reference from current IV; not a forecast or probability.");
    setText(root, "[data-radar-map-economic-label]", isCall ? "IF CALLED / SHARE" : "ENTRY AFTER CREDIT");
    setText(root, "[data-radar-map-economic]", isCall
      ? money(Number(candidate.strike) + Number(candidate.bid), 2)
      : money(candidate.effective_entry, 2));
    setText(root, "[data-radar-map-volatility]", `|Δ| ${nullableMetric(candidate.delta, (value) => number(Math.abs(value), 2))} · IV ${nullableMetric(candidate.implied_volatility, (value) => `${number(value, 1)}%`)}`);
    setText(root, "[data-radar-map-market]", `${money(candidate.bid)} / ${money(candidate.ask)} · ${number(candidate.spread_percent, 1)}%`);
    setText(root, "[data-radar-map-liquidity]", `${nullableMetric(candidate.open_interest, (value) => number(value, 0))} / ${nullableMetric(candidate.volume, (value) => number(value, 0))}`);
    setText(root, "[data-radar-map-summary]", isCall
      ? `The selected call becomes in the money above ${money(candidate.strike, 2)} at expiration. The map shows the boundary and volatility reference—not a future stock path.`
      : `The selected put becomes in the money below ${money(candidate.strike, 2)} at expiration. Premium changes the economic entry, not the assignment strike.`);

    const previous = root.querySelector("[data-radar-map-previous]");
    const next = root.querySelector("[data-radar-map-next]");
    previous.disabled = selectedIndex === 0;
    next.disabled = selectedIndex === projection.candidates.length - 1;
  };

  const select = (root, selectedIndex) => {
    const current = state.get(root);
    if (!current?.projection.expiration_map) return;
    const maximum = current.projection.candidates.length - 1;
    const nextIndex = Math.min(Math.max(Number(selectedIndex) || 0, 0), maximum);
    current.selectedIndex = nextIndex;
    root.querySelectorAll("[data-radar-candidate-index]").forEach((card) => {
      const isSelected = Number(card.dataset.radarCandidateIndex) === nextIndex;
      card.classList.toggle("selected", isSelected);
      card.setAttribute("aria-selected", String(isSelected));
    });
    renderSvg(root, current.projection, nextIndex);
    updateReadout(root, current.projection, nextIndex);
  };

  const setExpanded = (root, expanded) => {
    const current = state.get(root);
    if (!current?.projection.expiration_map) return;
    current.expanded = Boolean(expanded);
    const panel = root.querySelector("[data-radar-map-panel]");
    const button = root.querySelector("[data-radar-map-expand]");
    panel.classList.toggle("is-expanded", current.expanded);
    button.setAttribute("aria-expanded", String(current.expanded));
    button.textContent = current.expanded ? "COMPACT MAP ↙" : "EXPAND MAP ↗";
    syncIndicatorControls(root, current);
    requestAnimationFrame(() => {
      renderSvg(root, current.projection, current.selectedIndex);
      renderIndicators(root, current);
      if (current.expanded) panel.scrollIntoView({ block: "start" });
    });
  };

  const bindInteractions = (root) => {
    if (boundRoots.has(root)) return;
    boundRoots.add(root);
    const stage = root.querySelector("[data-radar-map-stage]");
    root.querySelector("[data-radar-map-expand]").addEventListener("click", () => {
      const current = state.get(root);
      setExpanded(root, !current?.expanded);
    });
    root.querySelector("[data-radar-map-previous]").addEventListener("click", () => {
      const current = state.get(root);
      if (current) select(root, current.selectedIndex - 1);
    });
    root.querySelector("[data-radar-map-next]").addEventListener("click", () => {
      const current = state.get(root);
      if (current) select(root, current.selectedIndex + 1);
    });
    root.querySelectorAll("[data-radar-indicator]").forEach((button) => {
      button.addEventListener("click", () => {
        const current = state.get(root);
        if (!current?.expanded) return;
        const key = button.dataset.radarIndicator;
        current.indicators[key] = !current.indicators[key];
        syncIndicatorControls(root, current);
        renderIndicators(root, current);
      });
    });
    stage.addEventListener("click", (event) => {
      const target = event.target.closest("[data-radar-map-index]");
      if (target) select(root, Number(target.dataset.radarMapIndex));
    });
    stage.addEventListener("keydown", (event) => {
      const target = event.target.closest("[data-radar-map-index]");
      if (!target || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      const nextIndex = Number(target.dataset.radarMapIndex);
      select(root, nextIndex);
      requestAnimationFrame(() => {
        root.querySelector(`[data-radar-map-index="${nextIndex}"]`)?.focus();
      });
    });
    document.addEventListener("keydown", (event) => {
      const current = state.get(root);
      if (event.key !== "Escape" || !current?.expanded) return;
      setExpanded(root, false);
      root.querySelector("[data-radar-map-expand]").focus();
    });
    if ("ResizeObserver" in window) {
      let lastSize = "";
      const observer = new ResizeObserver((entries) => {
        const size = entries[0]?.contentRect;
        const signature = size ? `${Math.round(size.width)}x${Math.round(size.height)}` : "";
        if (!signature || signature === lastSize) return;
        lastSize = signature;
        const current = state.get(root);
        if (current?.projection.expiration_map) {
          requestAnimationFrame(() => {
            renderSvg(root, current.projection, current.selectedIndex);
            renderIndicators(root, current);
          });
        }
      });
      observer.observe(stage);
    }
  };

  const render = (root, projection) => {
    const panel = root.querySelector("[data-radar-map-panel]");
    if (!projection.expiration_map || !projection.candidates.length) {
      panel.hidden = true;
      root.querySelector("[data-radar-map-stage]").replaceChildren();
      root.querySelector("[data-radar-indicator-stack]").replaceChildren();
      state.delete(root);
      return;
    }
    panel.hidden = false;
    const previous = state.get(root);
    const preferred = projection.candidates.findIndex((candidate) => candidate.label === "balanced");
    const cleared = projection.candidates.findIndex((candidate) => candidate.clears_all_rules);
    const selectedIndex = preferred >= 0 ? preferred : (cleared >= 0 ? cleared : 0);
    const expanded = previous?.expanded || false;
    const indicators = previous?.indicators || { rsi: false, macd: false };
    const current = { projection, selectedIndex, expanded, indicators };
    state.set(root, current);
    panel.classList.toggle("is-expanded", expanded);
    const expandButton = root.querySelector("[data-radar-map-expand]");
    expandButton.setAttribute("aria-expanded", String(expanded));
    expandButton.textContent = expanded ? "COMPACT MAP ↙" : "EXPAND MAP ↗";
    syncIndicatorControls(root, current);
    bindInteractions(root);
    select(root, selectedIndex);
    requestAnimationFrame(() => renderIndicators(root, current));
  };

  window.IncooomingRadarMap = { render, select, setExpanded };
})();
