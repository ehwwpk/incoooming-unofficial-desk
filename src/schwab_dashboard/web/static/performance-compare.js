(() => {
  "use strict";

  const SERIES = [
    { key: "actual", source: "actual", label: "Managed book", short: "MANAGED", color: "#72cf91" },
    { key: "shares", source: "shares_without_options", label: "Starting shares", short: "STARTING SHARES", color: "#e1bd58", lineStyle: 2 },
    { key: "market", source: "market_reference", label: "SPY price", short: "SPY", color: "#9ca3a8", lineStyle: 3 },
    { key: "levered", source: "levered_market_reference", label: "SPY at exposure", short: "SPY × EXPOSURE", color: "#a98cd8", lineStyle: 2 },
  ];

  const htmlEscape = (value) => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const percent = (value) => Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
    : "—";

  const compactMoney = (value) => {
    const amount = Math.abs(Number(value) || 0);
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

  const toDate = (value) => new Date(`${value}T00:00:00Z`);
  const timeKey = (value) => {
    if (typeof value === "string") return value;
    if (value && Number.isInteger(value.year) && Number.isInteger(value.month) && Number.isInteger(value.day)) {
      return `${value.year}-${String(value.month).padStart(2, "0")}-${String(value.day).padStart(2, "0")}`;
    }
    return null;
  };
  const formatDate = (value, full = false) => {
    if (!value) return "—";
    return (full ? fullDateFormatter : dateFormatter).format(toDate(value)).toUpperCase();
  };

  const parseSeries = (payload, definition) => {
    const source = payload?.[definition.source];
    if (!source?.points?.length) return null;
    const seen = new Map();
    source.points.forEach((point, index) => {
      let value = point.cumulative_return_percent == null
        ? null
        : Number(point.cumulative_return_percent);
      if (index === 0 && value === null) value = 0;
      if (!point.date || !Number.isFinite(value)) return;
      seen.set(point.date, {
        date: point.date,
        value,
        externalFlow: Number(point.external_flow) || 0,
        quality: point.quality || "observed",
      });
    });
    const points = [...seen.values()].sort((left, right) => left.date.localeCompare(right.date));
    if (points.length < 2) return null;
    return {
      ...definition,
      label: source.label || definition.label,
      status: source.status || "observed",
      points,
    };
  };

  const renderChart = (panel, payload) => {
    const charts = window.LightweightCharts;
    const frame = panel.querySelector("[data-performance-compare-chart]");
    const canvas = panel.querySelector("[data-performance-compare-canvas]");
    const empty = panel.querySelector("[data-performance-compare-empty]");
    const inspector = panel.querySelector("[data-performance-inspector]");
    const inspectorDate = panel.querySelector("[data-performance-inspector-date]");
    const inspectorFlow = panel.querySelector("[data-performance-inspector-flow]");
    const inspectorSeries = panel.querySelector("[data-performance-inspector-series]");
    const a11y = panel.querySelector("[data-performance-a11y]");
    if (!frame || !canvas) return;

    const series = SERIES.map((definition) => parseSeries(payload, definition)).filter(Boolean);
    if (!charts?.createChart || !series.length) {
      if (empty) {
        empty.hidden = false;
        empty.textContent = series.length
          ? "The chart runtime did not load. Reload Results to try again."
          : "Two valued market days are needed before a return path can be drawn.";
      }
      return;
    }
    if (empty) empty.hidden = true;

    const chart = charts.createChart(canvas, {
      autoSize: true,
      layout: {
        background: { type: charts.ColorType.Solid, color: "#090a0c" },
        textColor: "#858b8f",
        fontFamily: '"IBM Plex Mono", Consolas, monospace',
        fontSize: 11,
      },
      localization: {
        priceFormatter: (value) => percent(value),
      },
      grid: {
        vertLines: { color: "#131517", style: charts.LineStyle.Solid },
        horzLines: { color: "#17191b", style: charts.LineStyle.Solid },
      },
      crosshair: {
        mode: charts.CrosshairMode.Normal,
        vertLine: { color: "#8b9195", width: 1, style: charts.LineStyle.Dashed, labelBackgroundColor: "#34383b" },
        horzLine: { color: "#666c70", width: 1, style: charts.LineStyle.Dashed, labelBackgroundColor: "#34383b" },
      },
      rightPriceScale: {
        visible: true,
        borderVisible: true,
        borderColor: "#34383b",
        minimumWidth: 64,
        scaleMargins: { top: 0.08, bottom: 0.08 },
        entireTextOnly: true,
      },
      leftPriceScale: { visible: false },
      timeScale: {
        visible: true,
        borderVisible: true,
        borderColor: "#34383b",
        rightOffset: 1.4,
        barSpacing: 54,
        minBarSpacing: 18,
        fixLeftEdge: true,
        fixRightEdge: true,
        lockVisibleTimeRangeOnResize: true,
        rightBarStaysOnScroll: true,
        timeVisible: false,
        secondsVisible: false,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: { time: true, price: true }, mouseWheel: true, pinch: true },
    });

    const chartSeries = new Map();
    series.forEach((item) => {
      const common = {
        title: "",
        color: item.color,
        lineColor: item.color,
        lineWidth: item.key === "actual" ? 2 : 1,
        lineStyle: item.lineStyle ?? charts.LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
        priceFormat: { type: "custom", formatter: (value) => percent(value), minMove: 0.01 },
      };
      const api = chart.addSeries(charts.LineSeries, common);
      api.setData(item.points.map((point) => ({ time: point.date, value: point.value })));
      chartSeries.set(item.key, api);
    });

    const actualApi = chartSeries.get("actual");
    actualApi?.createPriceLine?.({
      price: 0,
      color: "#363b3e",
      lineWidth: 1,
      lineStyle: charts.LineStyle.Dotted,
      axisLabelVisible: false,
      title: "",
    });
    const dates = [...new Set(series.flatMap((item) => item.points.map((point) => point.date)))].sort();
    const pointsBySeries = new Map(series.map((item) => [item.key, new Map(item.points.map((point) => [point.date, point]))]));
    let locked = false;
    let cursorIndex = dates.length - 1;

    const showInspector = (date, point = null) => {
      if (!inspector || !date) return;
      cursorIndex = Math.max(0, dates.indexOf(date));
      inspectorDate.textContent = formatDate(date, true);
      const flow = pointsBySeries.get("actual")?.get(date)?.externalFlow || 0;
      inspectorFlow.textContent = flow ? `${compactMoney(flow)} OWNER CASH EXCLUDED` : "OBSERVED CLOSE";
      inspectorFlow.classList.toggle("has-flow", Boolean(flow));
      inspectorSeries.innerHTML = series.map((item) => {
        const value = pointsBySeries.get(item.key)?.get(date)?.value;
        return `<p class="performance-inspector-row performance-${item.key}-row"><i aria-hidden="true"></i><span>${htmlEscape(item.label)}</span><strong>${Number.isFinite(value) ? percent(value) : "NO VALUE"}</strong></p>`;
      }).join("");
      inspector.hidden = false;

      const width = inspector.offsetWidth || 250;
      const height = inspector.offsetHeight || 150;
      const x = point?.x ?? frame.clientWidth * 0.55;
      const y = point?.y ?? 96;
      const left = x > frame.clientWidth * 0.64 ? x - width - 18 : x + 18;
      inspector.style.left = `${Math.max(8, Math.min(frame.clientWidth - width - 8, left))}px`;
      inspector.style.top = `${Math.max(8, Math.min(frame.clientHeight - height - 8, y - height / 2))}px`;
    };

    const hideInspector = () => {
      if (!locked && inspector) inspector.hidden = true;
    };

    chart.subscribeCrosshairMove((parameter) => {
      if (!parameter?.time || parameter.point?.x < 0 || parameter.point?.y < 0 || parameter.point?.x > frame.clientWidth || parameter.point?.y > frame.clientHeight) {
        hideInspector();
        return;
      }
      if (!locked) showInspector(timeKey(parameter.time), parameter.point);
    });

    canvas.addEventListener("click", () => {
      locked = !locked;
      if (!locked) hideInspector();
    });
    canvas.addEventListener("mouseleave", hideInspector);
    frame.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) return;
      event.preventDefault();
      if (event.key === "Escape") {
        locked = false;
        hideInspector();
        chart.clearCrosshairPosition?.();
        return;
      }
      locked = true;
      if (event.key === "Home") cursorIndex = 0;
      else if (event.key === "End") cursorIndex = dates.length - 1;
      else cursorIndex = Math.max(0, Math.min(dates.length - 1, cursorIndex + (event.key === "ArrowRight" ? 1 : -1)));
      const date = dates[cursorIndex];
      showInspector(date);
      const point = pointsBySeries.get("actual")?.get(date);
      if (point && actualApi && chart.setCrosshairPosition) chart.setCrosshairPosition(point.value, date, actualApi);
    });
    frame.addEventListener("blur", () => {
      locked = false;
      hideInspector();
    });

    chart.timeScale().fitContent();
    const summary = series.map((item) => {
      const last = item.points.at(-1);
      return `${item.label} ${percent(last.value)} through ${formatDate(last.date, true)}`;
    }).join(". ");
    if (a11y) a11y.textContent = summary;
    frame.setAttribute("aria-label", `${summary}. Drag or use the mouse wheel to inspect the period; use arrow keys for observed dates.`);
  };

  document.querySelectorAll("[data-performance-compare]").forEach((panel) => {
    const raw = panel.querySelector("[data-performance-comparison-payload]");
    if (!raw) return;
    try {
      renderChart(panel, JSON.parse(raw.textContent));
    } catch (error) {
      console.error("Performance comparison chart could not be rendered.", error);
      const empty = panel.querySelector("[data-performance-compare-empty]");
      if (empty) {
        empty.hidden = false;
        empty.textContent = "The performance chart hit a rendering error. The figures above are unchanged.";
      }
    }
  });
})();
