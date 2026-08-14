(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";

  document.querySelectorAll("[data-performance-compare]").forEach((panel) => {
    const raw = panel.querySelector("[data-performance-comparison-payload]");
    const svg = panel.querySelector("[data-performance-compare-svg]");
    const empty = panel.querySelector("[data-performance-compare-empty]");
    if (!raw || !svg) return;
    let payload;
    try {
      payload = JSON.parse(raw.textContent);
    } catch {
      return;
    }
    const series = [
      ["actual", payload.actual, "#72cf91"],
      ["shares", payload.shares_without_options, "#e1bd58"],
      ["market", payload.market_reference, "#9ca3a8"],
    ].filter(([, item]) => item?.points?.length > 1);
    if (!series.length) return;
    empty.hidden = true;
    const datedPoints = series.flatMap(([, item]) => item.points)
      .map((point) => ({ ...point, timestamp: Date.parse(`${point.date}T00:00:00Z`) }))
      .filter((point) => Number.isFinite(point.timestamp));
    if (!datedPoints.length) return;
    const startAt = Math.min(...datedPoints.map((point) => point.timestamp));
    const endAt = Math.max(...datedPoints.map((point) => point.timestamp));
    const dateSpan = Math.max(86400000, endAt - startAt);
    const dateLabel = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
    const startLabel = panel.querySelector("[data-performance-start]");
    const endLabel = panel.querySelector("[data-performance-end]");
    if (startLabel) startLabel.textContent = dateLabel.format(new Date(startAt));
    if (endLabel) endLabel.textContent = dateLabel.format(new Date(endAt));
    const values = series.flatMap(([, item]) =>
      item.points
        .map((point) => Number(point.cumulative_return_percent))
        .filter(Number.isFinite),
    );
    const low = Math.min(0, ...values);
    const high = Math.max(0, ...values);
    const spread = Math.max(1, high - low);
    const zeroY = 3 + ((high - 0) / spread) * 30;
    const baseline = document.createElementNS(NS, "line");
    baseline.setAttribute("x1", "0");
    baseline.setAttribute("x2", "100");
    baseline.setAttribute("y1", String(zeroY));
    baseline.setAttribute("y2", String(zeroY));
    baseline.setAttribute("class", "performance-zero-line");
    svg.append(baseline);
    series.forEach(([key, item, color]) => {
      const points = item.points.filter((point) => Number.isFinite(Number(point.cumulative_return_percent)));
      const polyline = document.createElementNS(NS, "polyline");
      polyline.dataset.series = key;
      polyline.setAttribute("stroke", color);
      polyline.setAttribute(
        "points",
        points.map((point) => {
          const timestamp = Date.parse(`${point.date}T00:00:00Z`);
          const x = ((timestamp - startAt) / dateSpan) * 100;
          const y = 3 + ((high - Number(point.cumulative_return_percent)) / spread) * 30;
          return `${x},${y}`;
        }).join(" "),
      );
      svg.append(polyline);
    });
  });
})();
