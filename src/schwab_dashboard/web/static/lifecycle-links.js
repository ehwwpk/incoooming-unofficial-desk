(() => {
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const canvases = [...document.querySelectorAll(".price-path-canvas")];
  if (!canvases.length) return;

  const makePath = (className, pathData, marker) => {
    const path = document.createElementNS(SVG_NAMESPACE, "path");
    path.setAttribute("class", className);
    path.setAttribute("d", pathData);
    path.dataset.campaignId = marker.dataset.campaignId;
    path.dataset.lifecycleId = marker.dataset.lifecycleId;
    path.dataset.lifecycleSlot = marker.dataset.lifecycleSlot;
    path.dataset.linkConfidence = marker.dataset.campaignConfidence || "unknown";
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

  const drawLink = (overlay, previous, current, canvasRect) => {
    const start = markerCenter(previous, canvasRect);
    const end = markerCenter(current, canvasRect);
    const firstControlX = start.x + (end.x - start.x) * 0.38;
    const secondControlX = start.x + (end.x - start.x) * 0.62;
    const pathData = [
      `M ${start.x.toFixed(1)} ${start.y.toFixed(1)}`,
      `C ${firstControlX.toFixed(1)} ${start.y.toFixed(1)}`,
      `${secondControlX.toFixed(1)} ${end.y.toFixed(1)}`,
      `${end.x.toFixed(1)} ${end.y.toFixed(1)}`,
    ].join(" ");
    overlay.append(
      makePath("lifecycle-link-halo", pathData, current),
      makePath(`lifecycle-link ${current.dataset.eventType}`, pathData, current),
    );
  };

  const drawLinks = (canvas) => {
    const overlay = canvas.querySelector("[data-lifecycle-links]");
    if (!overlay) return;
    const canvasRect = canvas.getBoundingClientRect();
    if (!canvasRect.width || !canvasRect.height) return;
    overlay.setAttribute("viewBox", `0 0 ${canvasRect.width} ${canvasRect.height}`);
    overlay.replaceChildren();

    const campaigns = new Map();
    canvas.querySelectorAll("[data-campaign-id]").forEach((marker) => {
      if (marker.hidden) return;
      const key = marker.dataset.campaignId;
      const markers = campaigns.get(key) || [];
      markers.push(marker);
      campaigns.set(key, markers);
    });
    campaigns.forEach((markers) => {
      markers.sort(
        (left, right) => Number(left.dataset.campaignLeg) - Number(right.dataset.campaignLeg),
      );
      for (let index = 1; index < markers.length; index += 1) {
        drawLink(overlay, markers[index - 1], markers[index], canvasRect);
      }
    });
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
