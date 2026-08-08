(() => {
  const stage = document.querySelector("[data-nibwick-stage]");
  const nibwick = document.querySelector("[data-nibwick]");
  const art = document.querySelector("[data-nibwick-art]");
  const status = document.querySelector("[data-nibwick-status]");

  if (!stage || !nibwick || !art || !status) return;

  const STORAGE_KEY = "incoooming:nibwick-paused";
  const CYCLE_DURATION = 42000;
  const STUDY_FRAME = [
    " .-___-.",
    "( -   - )",
    "|   ᴗ   |",
    "(  /_\\  )",
    " `-._.-'",
    "  ᐟ   ᐠ",
  ].join("\n");
  const STUDY_BLINK_FRAME = STUDY_FRAME.replace("( -   - )", "( o   o )");
  const WALK_FRAMES = [
    [" .-___-.", "( o   o )", "|   ᴗ   |", "(  [O]  )", " `-._.-'", "  ᐟ   ╲"].join("\n"),
    [" .-___-.", "( o   o )", "|   ᴗ   |", "(  [O]  )", " `-._.-'", "  ╱   ᐠ"].join("\n"),
  ];
  const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  let startedAt = performance.now();
  let pausedAt = null;

  const isPaused = () => nibwick.dataset.paused === "true";

  const measureStage = () => {
    const distance = Math.max(3, stage.clientHeight - nibwick.offsetHeight - 6);
    stage.style.setProperty("--nibwick-distance", `${distance}px`);
  };

  const renderFrame = () => {
    if (motionPreference.matches) {
      stage.dataset.reducedMotion = "true";
      art.textContent = STUDY_FRAME;
      status.textContent = "STUDY";
      nibwick.dataset.phase = "study";
      nibwick.setAttribute("aria-label", "Nibwick is studying; reduced motion is enabled");
      return;
    }

    delete stage.dataset.reducedMotion;
    if (isPaused()) {
      art.textContent = STUDY_FRAME;
      status.textContent = "PAUSED";
      nibwick.dataset.phase = "study";
      nibwick.setAttribute("aria-label", "Resume Nibwick's desk patrol");
      return;
    }

    const elapsed = (performance.now() - startedAt) % CYCLE_DURATION;
    const studying = elapsed < 5880 || (elapsed >= 21000 && elapsed < 26880);
    nibwick.dataset.phase = studying ? "study" : "patrol";
    status.textContent = studying ? "STUDY" : "PATROL";
    nibwick.setAttribute("aria-label", "Pause Nibwick's desk patrol");
    if (studying) {
      art.textContent = Math.floor(elapsed / 1400) % 4 === 3 ? STUDY_BLINK_FRAME : STUDY_FRAME;
    } else {
      art.textContent = WALK_FRAMES[Math.floor(elapsed / 520) % WALK_FRAMES.length];
    }
  };

  const setPaused = (paused) => {
    const now = performance.now();
    if (paused && pausedAt === null) pausedAt = now;
    if (!paused && pausedAt !== null) {
      startedAt += now - pausedAt;
      pausedAt = null;
    }
    nibwick.dataset.paused = String(paused);
    nibwick.setAttribute("aria-pressed", String(paused));
    localStorage.setItem(STORAGE_KEY, String(paused));
    renderFrame();
  };

  nibwick.addEventListener("click", () => {
    if (!motionPreference.matches) setPaused(!isPaused());
  });
  motionPreference.addEventListener("change", renderFrame);
  new ResizeObserver(measureStage).observe(stage);

  const storedPreference = localStorage.getItem(STORAGE_KEY);
  setPaused(storedPreference === "true");
  measureStage();
  renderFrame();
  window.setInterval(() => {
    if (!document.hidden) renderFrame();
  }, 260);
})();
