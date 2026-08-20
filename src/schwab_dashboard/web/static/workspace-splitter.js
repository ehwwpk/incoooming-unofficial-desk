(() => {
  "use strict";

  const STORAGE_KEY = "incoooming:workspace-chart-percent:v2";
  const DEFAULT_PERCENT = 54;
  const MIN_PERCENT = 42;
  const MAX_PERCENT = 72;
  const MIN_PRICE_WIDTH = 520;
  const MIN_CALL_WIDTH = 480;
  const HANDLE_WIDTH = 9;
  const STACKED_QUERY = window.matchMedia("(max-width: 1100px)");

  const grids = Array.from(document.querySelectorAll("[data-workspace-grid]"));
  const splitters = Array.from(document.querySelectorAll("[data-workspace-splitter]"));
  if (!grids.length || !splitters.length) return;

  const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

  const readPreference = () => {
    try {
      const rawPreference = window.localStorage.getItem(STORAGE_KEY);
      if (rawPreference === null) return DEFAULT_PERCENT;
      const stored = Number(rawPreference);
      return Number.isFinite(stored) ? clamp(stored, MIN_PERCENT, MAX_PERCENT) : DEFAULT_PERCENT;
    } catch {
      return DEFAULT_PERCENT;
    }
  };

  const storePreference = (value) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, value.toFixed(2));
    } catch {
      // Resizing remains available when browser storage is disabled.
    }
  };

  const availableBounds = () => {
    const width = grids[0].getBoundingClientRect().width;
    if (!width) return { minimum: MIN_PERCENT, maximum: MAX_PERCENT };

    const minimum = Math.max(MIN_PERCENT, (MIN_PRICE_WIDTH / width) * 100);
    const maximum = Math.min(
      MAX_PERCENT,
      ((width - HANDLE_WIDTH - MIN_CALL_WIDTH) / width) * 100,
    );
    return maximum >= minimum
      ? { minimum, maximum }
      : { minimum: DEFAULT_PERCENT, maximum: DEFAULT_PERCENT };
  };

  let preferredPercent = readPreference();
  let activePointer = null;
  let resizeFrame = 0;

  const render = () => {
    const { minimum, maximum } = availableBounds();
    const displayedPercent = clamp(preferredPercent, minimum, maximum);
    const roundedPercent = Math.round(displayedPercent);

    grids.forEach((grid) => {
      grid.style.setProperty("--workspace-chart-percent", `${displayedPercent.toFixed(2)}%`);
    });
    splitters.forEach((splitter) => {
      splitter.setAttribute("aria-valuemin", String(Math.ceil(minimum)));
      splitter.setAttribute("aria-valuemax", String(Math.floor(maximum)));
      splitter.setAttribute("aria-valuenow", String(roundedPercent));
      splitter.setAttribute(
        "aria-valuetext",
        `Price chart ${roundedPercent}%, option status ${100 - roundedPercent}%`,
      );
    });
  };

  const finishPointerResize = (splitter, pointerId) => {
    if (splitter.hasPointerCapture(pointerId)) splitter.releasePointerCapture(pointerId);
    activePointer = null;
    document.body.classList.remove("workspace-resizing");
    storePreference(preferredPercent);
  };

  splitters.forEach((splitter) => {
    splitter.addEventListener("pointerdown", (event) => {
      if (STACKED_QUERY.matches || event.button !== 0) return;
      activePointer = { pointerId: event.pointerId, splitter };
      splitter.setPointerCapture(event.pointerId);
      document.body.classList.add("workspace-resizing");
      event.preventDefault();
    });

    splitter.addEventListener("pointermove", (event) => {
      if (!activePointer || activePointer.pointerId !== event.pointerId) return;
      const bounds = grids[0].getBoundingClientRect();
      const available = availableBounds();
      preferredPercent = clamp(
        ((event.clientX - bounds.left) / bounds.width) * 100,
        available.minimum,
        available.maximum,
      );
      render();
    });

    splitter.addEventListener("pointerup", (event) => {
      if (!activePointer || activePointer.pointerId !== event.pointerId) return;
      finishPointerResize(splitter, event.pointerId);
    });

    splitter.addEventListener("pointercancel", (event) => {
      if (!activePointer || activePointer.pointerId !== event.pointerId) return;
      finishPointerResize(splitter, event.pointerId);
    });

    splitter.addEventListener("dblclick", () => {
      preferredPercent = DEFAULT_PERCENT;
      render();
      storePreference(preferredPercent);
    });

    splitter.addEventListener("keydown", (event) => {
      if (STACKED_QUERY.matches) return;
      const { minimum, maximum } = availableBounds();
      const displayedPercent = clamp(preferredPercent, minimum, maximum);
      const step = event.shiftKey ? 5 : 2;
      let nextPercent = null;

      if (event.key === "ArrowLeft") nextPercent = displayedPercent - step;
      if (event.key === "ArrowRight") nextPercent = displayedPercent + step;
      if (event.key === "Home") nextPercent = minimum;
      if (event.key === "End") nextPercent = maximum;
      if (event.key === "Enter") nextPercent = DEFAULT_PERCENT;
      if (nextPercent === null) return;

      event.preventDefault();
      preferredPercent = clamp(nextPercent, MIN_PERCENT, MAX_PERCENT);
      render();
      storePreference(preferredPercent);
    });
  });

  window.addEventListener("resize", () => {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(render);
  });

  render();
})();
