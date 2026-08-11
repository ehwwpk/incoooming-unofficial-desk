(() => {
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const canvases = [...document.querySelectorAll(".price-path-canvas")];

  if (!canvases.length) return;

  const makePath = (className, pathData, lifecycleId, lifecycleSlot) => {
    const path = document.createElementNS(SVG_NAMESPACE, "path");
    path.setAttribute("class", className);
    path.setAttribute("d", pathData);
    path.dataset.lifecycleId = lifecycleId;
    path.dataset.lifecycleSlot = lifecycleSlot;
    return path;
  };

  const markerCenter = (marker, canvasRect) => {
    const badge = marker.querySelector(":scope > b") || marker;
    const rect = badge.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - canvasRect.left,
      y: rect.top + rect.height / 2 - canvasRect.top,
    };
  };

  const drawLinks = (canvas) => {
    const overlay = canvas.querySelector("[data-lifecycle-links]");
    if (!overlay) return;

    const canvasRect = canvas.getBoundingClientRect();
    if (!canvasRect.width || !canvasRect.height) return;

    overlay.setAttribute("viewBox", `0 0 ${canvasRect.width} ${canvasRect.height}`);
    overlay.replaceChildren();

    const sales = new Map();
    const outcomes = [];
    for (const marker of canvas.querySelectorAll("[data-lifecycle-id]")) {
      if (marker.hidden) continue;
      if (marker.dataset.eventType === "sale") {
        sales.set(marker.dataset.lifecycleId, marker);
      } else if (marker.dataset.linkedSaleSequence) {
        outcomes.push(marker);
      }
    }

    for (const outcome of outcomes) {
      const sale = sales.get(outcome.dataset.lifecycleId);
      if (!sale) continue;

      const start = markerCenter(sale, canvasRect);
      const end = markerCenter(outcome, canvasRect);
      const firstControlX = start.x + (end.x - start.x) * 0.38;
      const secondControlX = start.x + (end.x - start.x) * 0.62;
      const pathData = [
        `M ${start.x.toFixed(1)} ${start.y.toFixed(1)}`,
        `C ${firstControlX.toFixed(1)} ${start.y.toFixed(1)}`,
        `${secondControlX.toFixed(1)} ${end.y.toFixed(1)}`,
        `${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
      ].join(" ");

      overlay.append(
        makePath(
          "lifecycle-link-halo",
          pathData,
          outcome.dataset.lifecycleId,
          outcome.dataset.lifecycleSlot,
        ),
        makePath(
          `lifecycle-link ${outcome.dataset.eventType}`,
          pathData,
          outcome.dataset.lifecycleId,
          outcome.dataset.lifecycleSlot,
        ),
      );
    }
  };

  let animationFrame = 0;
  const drawAll = () => {
    animationFrame = 0;
    for (const canvas of canvases) drawLinks(canvas);
  };
  const scheduleDraw = () => {
    if (!animationFrame) animationFrame = window.requestAnimationFrame(drawAll);
  };

  const observer = new ResizeObserver(scheduleDraw);
  for (const canvas of canvases) observer.observe(canvas);
  document.addEventListener("option-event-layout", scheduleDraw);
  document.addEventListener("position-detail-toggle", scheduleDraw);
  window.addEventListener("resize", scheduleDraw, { passive: true });
  document.fonts?.ready.then(scheduleDraw);
  scheduleDraw();
})();
