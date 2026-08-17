(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const DAY = 86_400_000;
  const SERIES = [
    { key: "actual", source: "actual", label: "Managed book", color: "#72cf91", shape: "circle" },
    { key: "shares", source: "shares_without_options", label: "Same starting shares", color: "#e1bd58", shape: "square" },
    { key: "market", source: "market_reference", label: "SPY price context", color: "#9ca3a8", shape: "diamond" },
  ];

  const svgNode = (name, attributes = {}) => {
    const node = document.createElementNS(NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };

  const htmlEscape = (value) => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const timestamp = (value) => Date.parse(`${value}T00:00:00Z`);
  const percent = (value) => Number.isFinite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}%` : "—";
  const compactMoney = (value) => {
    const amount = Math.abs(value);
    const compact = amount >= 1_000_000
      ? `$${(amount / 1_000_000).toFixed(amount >= 10_000_000 ? 0 : 1)}M`
      : amount >= 1_000
        ? `$${(amount / 1_000).toFixed(amount >= 10_000 ? 0 : 1)}K`
        : `$${amount.toFixed(0)}`;
    return `${value < 0 ? "−" : "+"}${compact}`;
  };

  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  const fullDateFormatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });

  const parseSeries = (payload, definition) => {
    const source = payload?.[definition.source];
    if (!source?.points?.length) return null;
    const points = source.points
      .map((point, index) => {
        const at = timestamp(point.date);
        let value = point.cumulative_return_percent == null
          ? null
          : Number(point.cumulative_return_percent);
        if (index === 0 && point.cumulative_return_percent == null) value = 0;
        return {
          at,
          date: point.date,
          value: Number.isFinite(value) ? value : null,
          externalFlow: Number(point.external_flow) || 0,
          quality: point.quality || "observed",
        };
      })
      .filter((point) => Number.isFinite(point.at));
    const valued = points.filter((point) => point.value !== null);
    if (valued.length < 2) return null;
    return {
      ...definition,
      label: source.label || definition.label,
      status: source.status || "observed",
      points,
      valued,
    };
  };

  const niceStep = (raw) => {
    const power = 10 ** Math.floor(Math.log10(Math.max(raw, 0.0001)));
    const fraction = raw / power;
    if (fraction <= 1) return power;
    if (fraction <= 2) return 2 * power;
    if (fraction <= 5) return 5 * power;
    return 10 * power;
  };

  const yDomain = (values) => {
    const low = Math.min(0, ...values);
    const high = Math.max(0, ...values);
    const rawSpan = Math.max(0.5, high - low);
    const step = niceStep(rawSpan / 4);
    let min = Math.floor((low - rawSpan * 0.12) / step) * step;
    let max = Math.ceil((high + rawSpan * 0.12) / step) * step;
    if (min === max) max = min + step;
    return { min, max, step };
  };

  const uniqueDateTicks = (dates, target = 5) => {
    if (dates.length <= target) return dates;
    const picked = new Set([dates[0], dates.at(-1)]);
    for (let index = 1; index < target - 1; index += 1) {
      picked.add(dates[Math.round((dates.length - 1) * index / (target - 1))]);
    }
    return [...picked].sort((a, b) => a - b);
  };

  const pathFor = (points, x, y) => {
    let path = "";
    let drawing = false;
    points.forEach((point) => {
      if (point.value === null) {
        drawing = false;
        return;
      }
      path += `${drawing ? " L" : "M"}${x(point.at).toFixed(2)},${y(point.value).toFixed(2)}`;
      drawing = true;
    });
    return path;
  };

  const drawPoint = (group, series, point, x, y) => {
    const cx = x(point.at);
    const cy = y(point.value);
    let marker;
    if (series.shape === "square") {
      marker = svgNode("rect", { x: cx - 3.3, y: cy - 3.3, width: 6.6, height: 6.6, rx: 0.7 });
    } else if (series.shape === "diamond") {
      marker = svgNode("path", { d: `M${cx},${cy - 4} L${cx + 4},${cy} L${cx},${cy + 4} L${cx - 4},${cy} Z` });
    } else {
      marker = svgNode("circle", { cx, cy, r: 3.4 });
    }
    marker.setAttribute("class", `performance-series-point performance-${series.key}-point`);
    marker.dataset.series = series.key;
    marker.dataset.date = point.date;
    group.append(marker);
  };

  const spreadEndLabels = (labels, top, bottom) => {
    const gap = 31;
    const sorted = [...labels].sort((left, right) => left.naturalY - right.naturalY);
    sorted.forEach((item, index) => {
      item.y = Math.max(top, item.naturalY, index ? sorted[index - 1].y + gap : top);
    });
    if (sorted.at(-1)?.y > bottom) {
      const shift = sorted.at(-1).y - bottom;
      sorted.forEach((item) => { item.y -= shift; });
      for (let index = sorted.length - 2; index >= 0; index -= 1) {
        sorted[index].y = Math.min(sorted[index].y, sorted[index + 1].y - gap);
      }
    }
    return labels;
  };

  const renderCoverage = (container, series, startAt, endAt) => {
    if (!container) return;
    const span = Math.max(DAY, endAt - startAt);
    container.innerHTML = series.map((item) => {
      const first = item.valued[0];
      const last = item.valued.at(-1);
      const left = ((first.at - startAt) / span) * 100;
      const width = Math.max(1.5, ((last.at - first.at) / span) * 100);
      const through = last.at < endAt ? `ENDS ${dateFormatter.format(new Date(last.at))}` : `THROUGH ${dateFormatter.format(new Date(last.at))}`;
      return `<div class="performance-coverage-item performance-${item.key}-coverage">
        <span class="performance-series-key"><i aria-hidden="true"></i>${htmlEscape(item.label)}</span>
        <strong>${item.valued.length} VALUES · ${through}</strong>
        <span class="performance-coverage-track" aria-hidden="true"><b style="--coverage-left:${left.toFixed(2)}%;--coverage-width:${width.toFixed(2)}%"></b></span>
      </div>`;
    }).join("");
  };

  const renderChart = (panel, payload) => {
    const chart = panel.querySelector("[data-performance-compare-chart]");
    const svg = panel.querySelector("[data-performance-compare-svg]");
    const empty = panel.querySelector("[data-performance-compare-empty]");
    const coverage = panel.querySelector("[data-performance-coverage]");
    const inspector = panel.querySelector("[data-performance-inspector]");
    const inspectorDate = panel.querySelector("[data-performance-inspector-date]");
    const inspectorFlow = panel.querySelector("[data-performance-inspector-flow]");
    const inspectorSeries = panel.querySelector("[data-performance-inspector-series]");
    const a11y = panel.querySelector("[data-performance-a11y]");
    if (!chart || !svg) return;

    const series = SERIES.map((definition) => parseSeries(payload, definition)).filter(Boolean);
    if (!series.length) {
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    const allDates = [...new Set(series.flatMap((item) => item.points.map((point) => point.at)))].sort((a, b) => a - b);
    const allValues = series.flatMap((item) => item.valued.map((point) => point.value));
    const startAt = allDates[0];
    const endAt = allDates.at(-1);
    const dateSpan = Math.max(DAY, endAt - startAt);
    const state = { cursorIndex: allDates.length - 1, locked: false, cursor: null };

    const describe = () => {
      const summaries = series.map((item) => {
        const last = item.valued.at(-1);
        return `${item.label} ${percent(last.value)} through ${fullDateFormatter.format(new Date(last.at))}`;
      });
      const flows = series[0].points.filter((point) => point.externalFlow).reduce((sum, point) => sum + point.externalFlow, 0);
      if (a11y) a11y.textContent = `${summaries.join(". ")}. ${flows ? `${compactMoney(flows)} of owner cash was excluded from return calculations.` : "No owner cash flows were excluded."}`;
      chart.setAttribute("aria-label", `${summaries.join("; ")}. Use left and right arrow keys to inspect exact observed dates.`);
    };

    const showInspector = (index, clientX = null, clientY = null) => {
      if (!inspector) return;
      state.cursorIndex = Math.max(0, Math.min(allDates.length - 1, index));
      const at = allDates[state.cursorIndex];
      const xPosition = state.x(at);
      if (state.cursor) {
        state.cursor.setAttribute("x1", xPosition);
        state.cursor.setAttribute("x2", xPosition);
        state.cursor.hidden = false;
      }
      inspectorDate.textContent = fullDateFormatter.format(new Date(at));
      const actualPoint = series[0].points.find((point) => point.at === at);
      const flow = actualPoint?.externalFlow || 0;
      inspectorFlow.textContent = flow ? `${compactMoney(flow)} OWNER CASH EXCLUDED` : "OBSERVED CLOSE";
      inspectorFlow.classList.toggle("has-flow", Boolean(flow));
      inspectorSeries.innerHTML = series.map((item) => {
        const point = item.points.find((candidate) => candidate.at === at && candidate.value !== null);
        return `<p class="performance-inspector-row performance-${item.key}-row"><i aria-hidden="true"></i><span>${htmlEscape(item.label)}</span><strong>${point ? percent(point.value) : "NO VALUE"}</strong></p>`;
      }).join("");
      inspector.hidden = false;

      const chartRect = chart.getBoundingClientRect();
      const localX = clientX == null ? xPosition : clientX - chartRect.left;
      const localY = clientY == null ? 42 : clientY - chartRect.top;
      const cardWidth = inspector.offsetWidth || 235;
      const cardHeight = inspector.offsetHeight || 120;
      const left = localX > chartRect.width * 0.66 ? localX - cardWidth - 16 : localX + 16;
      inspector.style.left = `${Math.max(8, Math.min(chartRect.width - cardWidth - 8, left))}px`;
      inspector.style.top = `${Math.max(8, Math.min(chartRect.height - cardHeight - 8, localY - cardHeight / 2))}px`;
    };

    const hideInspector = () => {
      if (state.locked) return;
      if (inspector) inspector.hidden = true;
      if (state.cursor) state.cursor.hidden = true;
    };

    const render = () => {
      const width = Math.max(640, Math.round(chart.clientWidth));
      const height = Math.max(270, Math.round(chart.clientHeight));
      const margin = { top: 28, right: Math.min(168, width * 0.17), bottom: 38, left: 54 };
      const plot = { left: margin.left, right: width - margin.right, top: margin.top, bottom: height - margin.bottom };
      const domain = yDomain(allValues);
      const x = (at) => plot.left + ((at - startAt) / dateSpan) * (plot.right - plot.left);
      const y = (value) => plot.top + ((domain.max - value) / (domain.max - domain.min)) * (plot.bottom - plot.top);
      state.x = x;

      svg.replaceChildren();
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("preserveAspectRatio", "none");

      const definitions = svgNode("defs");
      const gradient = svgNode("linearGradient", { id: "performance-managed-fill", x1: 0, y1: 0, x2: 0, y2: 1 });
      gradient.append(svgNode("stop", { offset: "0%", "stop-color": "#72cf91", "stop-opacity": 0.17 }));
      gradient.append(svgNode("stop", { offset: "100%", "stop-color": "#72cf91", "stop-opacity": 0 }));
      definitions.append(gradient);
      svg.append(definitions);

      const grid = svgNode("g", { class: "performance-grid" });
      for (let tick = domain.min; tick <= domain.max + domain.step / 2; tick += domain.step) {
        const tickY = y(tick);
        grid.append(svgNode("line", { x1: plot.left, x2: plot.right, y1: tickY, y2: tickY, class: tick === 0 ? "performance-zero-line" : "performance-grid-line" }));
        const label = svgNode("text", { x: plot.left - 11, y: tickY + 3, class: "performance-axis-label", "text-anchor": "end" });
        label.textContent = `${tick.toFixed(Math.abs(domain.step) < 1 ? 1 : 0)}%`;
        grid.append(label);
      }
      uniqueDateTicks(allDates, width < 850 ? 4 : 5).forEach((at, index, ticks) => {
        const tickX = x(at);
        grid.append(svgNode("line", { x1: tickX, x2: tickX, y1: plot.top, y2: plot.bottom, class: "performance-date-grid-line" }));
        const label = svgNode("text", { x: tickX, y: plot.bottom + 23, class: "performance-date-label", "text-anchor": index === 0 ? "start" : index === ticks.length - 1 ? "end" : "middle" });
        label.textContent = dateFormatter.format(new Date(at)).toUpperCase();
        grid.append(label);
      });
      const axisTitle = svgNode("text", { x: plot.left, y: 13, class: "performance-axis-title" });
      axisTitle.textContent = "CUMULATIVE RETURN · OWNER CASH FLOWS REMOVED";
      grid.append(axisTitle);
      svg.append(grid);

      const actual = series.find((item) => item.key === "actual");
      if (actual) {
        const actualPath = pathFor(actual.points, x, y);
        const first = actual.valued[0];
        const last = actual.valued.at(-1);
        const area = `${actualPath} L${x(last.at).toFixed(2)},${y(0).toFixed(2)} L${x(first.at).toFixed(2)},${y(0).toFixed(2)} Z`;
        svg.append(svgNode("path", { d: area, class: "performance-managed-area" }));
      }

      const marks = svgNode("g", { class: "performance-series-marks" });
      series.forEach((item) => {
        marks.append(svgNode("path", { d: pathFor(item.points, x, y), class: `performance-series-line performance-${item.key}-line` }));
        item.valued.forEach((point) => drawPoint(marks, item, point, x, y));
      });
      svg.append(marks);

      const cashFlows = actual?.points.filter((point) => point.externalFlow) || [];
      cashFlows.forEach((point, index) => {
        const flowX = x(point.at);
        svg.append(svgNode("line", { x1: flowX, x2: flowX, y1: plot.top, y2: plot.bottom, class: "performance-flow-line" }));
        const tag = svgNode("g", { class: "performance-flow-tag", transform: `translate(${flowX},${plot.top + 11 + index * 18})` });
        tag.append(svgNode("path", { d: "M-4,-6 L4,-6 L0,0 Z" }));
        const text = svgNode("text", { x: 8, y: -3 });
        text.textContent = `${compactMoney(point.externalFlow)} CASH EXCLUDED`;
        tag.append(text);
        svg.append(tag);
      });

      const endLabels = spreadEndLabels(series.map((item) => {
        const last = item.valued.at(-1);
        return { item, last, naturalY: y(last.value) };
      }), plot.top + 10, plot.bottom - 10);
      endLabels.forEach(({ item, last, y: labelY }) => {
        const lastX = x(last.at);
        const lastY = y(last.value);
        const labelX = plot.right + 16;
        const group = svgNode("g", { class: `performance-end-label performance-${item.key}-end` });
        group.append(svgNode("path", { d: `M${lastX + 5},${lastY} L${labelX - 6},${labelY}` }));
        const name = svgNode("text", { x: labelX, y: labelY - 4 });
        name.textContent = item.label.toUpperCase();
        const value = svgNode("text", { x: labelX, y: labelY + 10, class: "performance-end-value" });
        value.textContent = percent(last.value);
        const through = svgNode("text", { x: labelX, y: labelY + 22, class: "performance-end-through" });
        through.textContent = `${last.at < endAt ? "ENDS" : "THROUGH"} ${dateFormatter.format(new Date(last.at)).toUpperCase()}`;
        group.append(name, value, through);
        svg.append(group);
      });

      const cursor = svgNode("line", { x1: 0, x2: 0, y1: plot.top, y2: plot.bottom, class: "performance-scrub-line" });
      cursor.hidden = true;
      svg.append(cursor);
      state.cursor = cursor;

      const hit = svgNode("rect", { x: plot.left, y: plot.top, width: plot.right - plot.left, height: plot.bottom - plot.top, class: "performance-hit-area" });
      hit.addEventListener("pointermove", (event) => {
        if (state.locked) return;
        const rect = svg.getBoundingClientRect();
        const svgX = ((event.clientX - rect.left) / rect.width) * width;
        const ratio = Math.max(0, Math.min(1, (svgX - plot.left) / (plot.right - plot.left)));
        const requested = startAt + ratio * dateSpan;
        const index = allDates.reduce((best, candidate, candidateIndex) => Math.abs(candidate - requested) < Math.abs(allDates[best] - requested) ? candidateIndex : best, 0);
        showInspector(index, event.clientX, event.clientY);
      });
      hit.addEventListener("pointerleave", hideInspector);
      hit.addEventListener("click", (event) => {
        state.locked = !state.locked;
        if (!state.locked) hideInspector();
        else showInspector(state.cursorIndex, event.clientX, event.clientY);
      });
      svg.append(hit);

      if (!inspector?.hidden) showInspector(state.cursorIndex);
    };

    chart.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) return;
      event.preventDefault();
      if (event.key === "Escape") {
        state.locked = false;
        hideInspector();
        return;
      }
      state.locked = true;
      if (event.key === "Home") state.cursorIndex = 0;
      else if (event.key === "End") state.cursorIndex = allDates.length - 1;
      else state.cursorIndex += event.key === "ArrowRight" ? 1 : -1;
      showInspector(state.cursorIndex);
    });
    chart.addEventListener("blur", () => {
      state.locked = false;
      hideInspector();
    });

    renderCoverage(coverage, series, startAt, endAt);
    describe();
    render();
    if (window.ResizeObserver) new ResizeObserver(render).observe(chart);
    else window.addEventListener("resize", render, { passive: true });
  };

  document.querySelectorAll("[data-performance-compare]").forEach((panel) => {
    const raw = panel.querySelector("[data-performance-comparison-payload]");
    if (!raw) return;
    try {
      renderChart(panel, JSON.parse(raw.textContent));
    } catch (error) {
      console.error("Performance comparison chart could not be rendered.", error);
    }
  });
})();
