(() => {
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const BUFFER = 6;
  const EDGE_PADDING = 3;
  const CANDIDATES = [
    [0, 0],
    [0, -20],
    [0, 20],
    [-18, -14],
    [18, -14],
    [-18, 14],
    [18, 14],
    [0, -40],
    [0, 40],
    [-34, 0],
    [34, 0],
  ];
  const canvases = [...document.querySelectorAll(".price-path-canvas")];

  if (!canvases.length) return;

  const moveBox = (box, x, y) => ({
    left: box.left + x,
    right: box.right + x,
    top: box.top + y,
    bottom: box.bottom + y,
  });

  const overlapArea = (a, b) => {
    const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left) + BUFFER);
    const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) + BUFFER);
    return width * height;
  };

  const isInside = (box, width, height) =>
    box.left >= EDGE_PADDING &&
    box.right <= width - EDGE_PADDING &&
    box.top >= EDGE_PADDING &&
    box.bottom <= height - EDGE_PADDING;

  const candidateScore = (box, x, y, placed, width, height) => {
    const moved = moveBox(box, x, y);
    const overlap = placed.reduce((total, other) => total + overlapArea(moved, other), 0);
    const boundaryPenalty = isInside(moved, width, height) ? 0 : 100000;
    const movementPenalty = Math.abs(y) + Math.abs(x) * 2.4;
    return { box: moved, score: boundaryPenalty + overlap * 1000 + movementPenalty };
  };

  const makeLeader = (eventType, x1, y1, x2, y2) => {
    const line = document.createElementNS(SVG_NAMESPACE, "line");
    line.setAttribute("class", `event-leader ${eventType}`);
    line.setAttribute("x1", x1.toFixed(1));
    line.setAttribute("y1", y1.toFixed(1));
    line.setAttribute("x2", x2.toFixed(1));
    line.setAttribute("y2", y2.toFixed(1));
    return line;
  };

  const layoutCanvas = (canvas) => {
    const overlay = canvas.querySelector("[data-event-leaders]");
    if (!overlay) return;

    const allMarkers = [...canvas.querySelectorAll(".price-event, .share-event")];
    for (const marker of allMarkers) {
      marker.style.setProperty("--collision-x", "0px");
      marker.style.setProperty("--collision-y", "0px");
    }
    const markers = allMarkers.filter((marker) => !marker.hidden);

    const canvasRect = canvas.getBoundingClientRect();
    if (!canvasRect.width || !canvasRect.height) return;

    overlay.setAttribute("viewBox", `0 0 ${canvasRect.width} ${canvasRect.height}`);
    overlay.replaceChildren();

    const nodes = markers
      .map((marker) => {
        const badge = marker.querySelector(":scope > b") || marker;
        const rect = badge.getBoundingClientRect();
        const originWidth = marker.dataset.linkedSaleSequence ? 19 : 0;
        return {
          marker,
          priority: marker.classList.contains("share-event") ? 1 : 0,
          anchorX:
            (Number.parseFloat(marker.style.getPropertyValue("--event-x")) / 100) *
            canvasRect.width,
          anchorY:
            (Number.parseFloat(marker.style.getPropertyValue("--event-y")) / 100) *
            canvasRect.height,
          centerX: rect.left + rect.width / 2 - canvasRect.left,
          centerY: rect.top + rect.height / 2 - canvasRect.top,
          box: {
            left: rect.left - canvasRect.left - originWidth,
            right: rect.right - canvasRect.left,
            top: rect.top - canvasRect.top,
            bottom: rect.bottom - canvasRect.top,
          },
        };
      })
      .sort(
        (a, b) =>
          a.priority - b.priority || a.centerX - b.centerX || a.centerY - b.centerY,
      );

    const placed = [];
    for (const node of nodes) {
      let best = null;
      for (const [x, y] of CANDIDATES) {
        const candidate = candidateScore(
          node.box,
          x,
          y,
          placed,
          canvasRect.width,
          canvasRect.height,
        );
        if (!best || candidate.score < best.score) best = { ...candidate, x, y };
        if (candidate.score < 1000) break;
      }

      node.marker.style.setProperty("--collision-x", `${best.x}px`);
      node.marker.style.setProperty("--collision-y", `${best.y}px`);
      placed.push(best.box);

      const resolvedCenterX = node.centerX + best.x;
      const resolvedCenterY = node.centerY + best.y;
      if (Math.hypot(resolvedCenterX - node.anchorX, resolvedCenterY - node.anchorY) > 5) {
        overlay.append(
          makeLeader(
            node.marker.dataset.eventType,
            node.anchorX,
            node.anchorY,
            resolvedCenterX,
            resolvedCenterY,
          ),
        );
      }
    }

    document.dispatchEvent(new CustomEvent("option-event-layout", { detail: { canvas } }));
  };

  let animationFrame = 0;
  const layoutAll = () => {
    animationFrame = 0;
    for (const canvas of canvases) layoutCanvas(canvas);
  };
  const scheduleLayout = () => {
    if (!animationFrame) animationFrame = window.requestAnimationFrame(layoutAll);
  };

  const observer = new ResizeObserver(scheduleLayout);
  for (const canvas of canvases) observer.observe(canvas);
  window.addEventListener("resize", scheduleLayout, { passive: true });
  document.addEventListener("chart-viewport-change", scheduleLayout);
  document.addEventListener("position-detail-toggle", scheduleLayout);
  document.fonts?.ready.then(scheduleLayout);
  scheduleLayout();
})();
