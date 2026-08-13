(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  const number = (value, digits = 2) => Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const svgNode = (tag, attributes = {}, text) => {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const latestValue = (points, key) => {
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const value = points[index][key];
      if (value !== null && value !== undefined) return Number(value);
    }
    return null;
  };
  const linePoints = (points, key, x, y) => points
    .filter((point) => point[key] !== null && point[key] !== undefined)
    .map((point) => `${x(point.x_percent)},${y(Number(point[key]))}`)
    .join(" ");
  const timeGrid = (svg, points, x, top, bottom) => {
    if (!points.length) return;
    const first = Number(points[0].x_percent);
    const last = Number(points[points.length - 1].x_percent);
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((fraction) => {
      const position = first + ((last - first) * fraction);
      svg.append(svgNode("line", {
        class: "indicator-time-grid",
        x1: x(position),
        y1: top,
        x2: x(position),
        y2: bottom,
      }));
    });
  };

  const pane = (kind, title, value, note) => {
    const section = document.createElement("section");
    section.className = `radar-indicator-pane ${kind}-pane`;
    section.dataset.radarIndicatorPane = kind;
    const header = document.createElement("header");
    const label = document.createElement("span");
    label.textContent = title;
    const current = document.createElement("b");
    current.textContent = value;
    const context = document.createElement("small");
    context.textContent = note;
    header.append(label, current, context);
    const stage = document.createElement("div");
    stage.className = "radar-indicator-stage";
    section.append(header, stage);
    return { section, stage };
  };

  const renderRsi = (stack, points, width) => {
    const current = latestValue(points, "rsi_14");
    const { section, stage } = pane(
      "rsi",
      "RSI 14 / DAILY CLOSE",
      current === null ? "UNAVAILABLE" : number(current, 1),
      "70 / 30 REFERENCE - CONTEXT, NOT A TRADE SIGNAL",
    );
    const height = 92;
    const top = 8;
    const bottom = 84;
    const x = (value) => (Number(value) / 100) * width;
    const y = (value) => top + ((100 - value) / 100) * (bottom - top);
    const svg = svgNode("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": current === null
        ? "RSI 14 is unavailable because there are not enough daily closes."
        : `RSI 14 pane. Latest value ${number(current, 1)}.`,
    });
    const todayX = x(points.at(-1)?.x_percent ?? 90);
    svg.append(svgNode("rect", {
      class: "indicator-forward-zone",
      x: todayX,
      y: top,
      width: Math.max(x(90) - todayX, 1),
      height: bottom - top,
    }));
    timeGrid(svg, points, x, top, bottom);
    [70, 50, 30].forEach((level) => {
      svg.append(svgNode("line", {
        class: `indicator-reference rsi-${level}`,
        x1: x(5), y1: y(level), x2: x(90), y2: y(level),
      }));
      svg.append(svgNode("text", {
        class: "indicator-axis-label",
        x: x(91.4), y: y(level) + 3,
      }, String(level)));
    });
    const pointsValue = linePoints(points, "rsi_14", x, y);
    if (pointsValue) svg.append(svgNode("polyline", { class: "indicator-rsi-line", points: pointsValue }));
    if (!pointsValue) {
      svg.append(svgNode("text", {
        class: "indicator-unavailable",
        x: width / 2, y: height / 2,
        "text-anchor": "middle",
      }, "RSI NEEDS AT LEAST 15 DAILY CLOSES"));
    }
    stage.append(svg);
    stack.append(section);
  };

  const renderMacd = (stack, points, width) => {
    const currentMacd = latestValue(points, "macd");
    const currentSignal = latestValue(points, "macd_signal");
    const currentHistogram = latestValue(points, "macd_histogram");
    const valueLabel = currentMacd === null || currentSignal === null
      ? "UNAVAILABLE"
      : `${number(currentMacd)} / ${number(currentSignal)}`;
    const { section, stage } = pane(
      "macd",
      "MACD / SIGNAL",
      valueLabel,
      currentHistogram === null
        ? "12 / 26 / 9 EMA"
        : `HIST ${number(currentHistogram)} - 12 / 26 / 9 EMA`,
    );
    const height = 112;
    const top = 8;
    const bottom = 104;
    const x = (value) => (Number(value) / 100) * width;
    const values = points.flatMap((point) => [point.macd, point.macd_signal, point.macd_histogram])
      .filter((value) => value !== null && value !== undefined)
      .map(Number);
    const bound = Math.max(...values.map(Math.abs), 0.01) * 1.12;
    const y = (value) => top + ((bound - value) / (bound * 2)) * (bottom - top);
    const zeroY = y(0);
    const svg = svgNode("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": currentMacd === null || currentSignal === null
        ? "MACD is unavailable because there are not enough daily closes."
        : `MACD pane. Latest MACD ${number(currentMacd)} and signal ${number(currentSignal)}.`,
    });
    const todayX = x(points.at(-1)?.x_percent ?? 90);
    svg.append(svgNode("rect", {
      class: "indicator-forward-zone",
      x: todayX,
      y: top,
      width: Math.max(x(90) - todayX, 1),
      height: bottom - top,
    }));
    timeGrid(svg, points, x, top, bottom);
    svg.append(svgNode("line", {
      class: "indicator-reference macd-zero",
      x1: x(5), y1: zeroY, x2: x(90), y2: zeroY,
    }));
    const historical = points.filter(
      (point) => point.macd_histogram !== null && point.macd_histogram !== undefined,
    );
    const barWidth = historical.length > 1
      ? Math.max(
          1.25,
          Math.min(5, (x(historical[1].x_percent) - x(historical[0].x_percent)) * 0.58),
        )
      : 2;
    historical.forEach((point) => {
      const value = Number(point.macd_histogram);
      const valueY = y(value);
      svg.append(svgNode("rect", {
        class: value >= 0 ? "indicator-histogram positive" : "indicator-histogram negative",
        x: x(point.x_percent) - (barWidth / 2),
        y: Math.min(valueY, zeroY),
        width: barWidth,
        height: Math.max(Math.abs(zeroY - valueY), 0.75),
      }));
    });
    const macdPoints = linePoints(points, "macd", x, y);
    const signalPoints = linePoints(points, "macd_signal", x, y);
    if (macdPoints) svg.append(svgNode("polyline", { class: "indicator-macd-line", points: macdPoints }));
    if (signalPoints) svg.append(svgNode("polyline", { class: "indicator-signal-line", points: signalPoints }));
    if (!signalPoints) {
      svg.append(svgNode("text", {
        class: "indicator-unavailable",
        x: width / 2, y: height / 2,
        "text-anchor": "middle",
      }, "MACD 12/26/9 NEEDS AT LEAST 34 DAILY CLOSES"));
    }
    stage.append(svg);
    stack.append(section);
  };

  const render = (root, projection, active, expanded) => {
    const stack = root.querySelector("[data-radar-indicator-stack]");
    stack.replaceChildren();
    const points = projection.expiration_map?.indicator_points || [];
    const enabled = expanded && (active.rsi || active.macd);
    stack.hidden = !enabled;
    if (!enabled) return;
    const priceStage = root.querySelector("[data-radar-map-stage]");
    const width = Math.max(Math.round(priceStage.getBoundingClientRect().width), 620);
    if (active.rsi) renderRsi(stack, points, width);
    if (active.macd) renderMacd(stack, points, width);
  };

  window.IncooomingRadarIndicators = { render };
})();
