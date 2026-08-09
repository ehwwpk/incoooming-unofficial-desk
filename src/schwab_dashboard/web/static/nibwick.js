(() => {
  const stage = document.querySelector("[data-nibwick-stage]");
  const nibwick = document.querySelector("[data-nibwick]");
  const art = document.querySelector("[data-nibwick-art]");
  const status = document.querySelector("[data-nibwick-status]");
  const alertPanel = document.querySelector("[data-nibwick-popover]");

  if (!stage || !nibwick || !art || !status) return;

  const STORAGE_KEY = "incoooming:nibwick-paused";
  const CYCLE_DURATION = 42000;
  const REACTION_DURATION = 1650;
  const hasAlertNotes = Boolean(alertPanel);
  const makeFrame = (eyes, nose, paws, feet = "  /   \\") =>
    [" ()___()", `( ${eyes} )`, `|   ${nose}   |`, `( ${paws} )`, " `-._.-'", feet].join(
      "\n",
    );
  const STUDY_FRAME = makeFrame("-   -", "^", " /_\\ ");
  const STUDY_BLINK_FRAME = makeFrame("o   o", "^", " /_\\ ");
  const WALK_FRAMES = [
    makeFrame("o   o", "^", " | | ", "  /   _"),
    makeFrame("o   o", "^", " | | ", "  _   \\"),
  ];
  const KICK_FRAME = makeFrame("O   O", "^", " /_> ", "  /__>");
  const WAVE_FRAMES = [
    [" ()___()", "( o   o )", "|   ^   /", "(  | |  )", " `-._.-'", "  /   \\"].join("\n"),
    [" ()___()", "( o   o )", "\\   ^   |", "(  | |  )", " `-._.-'", "  /   \\"].join("\n"),
  ];
  const REACTIONS = {
    audit: { art: makeFrame("O   O", "^", " [T] "), label: "AUDIT" },
    recount: { art: makeFrame("o   o", "^", " [#] "), label: "RECOUNT" },
    shares: { art: makeFrame("o   o", "^", " [+] "), label: "SHARES" },
    notice: { frames: WAVE_FRAMES, label: "NOTE", duration: 2600 },
  };
  const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  let startedAt = performance.now();
  let pausedAt = null;
  let activeReaction = null;
  let reactionStartedAt = null;
  let reactionTimer = 0;

  const isPaused = () => nibwick.dataset.paused === "true";

  const setControlLabel = () => {
    if (hasAlertNotes) {
      const open = alertPanel && !alertPanel.hidden;
      nibwick.setAttribute("aria-label", `${open ? "Close" : "Open"} Nibwick's notes`);
      nibwick.setAttribute("aria-expanded", String(open));
    }
  };

  const measureStage = () => {
    const distance = Math.max(3, stage.clientHeight - nibwick.offsetHeight - 6);
    stage.style.setProperty("--nibwick-distance", `${distance}px`);
  };

  const renderFrame = () => {
    if (motionPreference.matches) {
      stage.dataset.reducedMotion = "true";
      art.textContent = stage.dataset.attention === "true" ? WAVE_FRAMES[0] : STUDY_FRAME;
      status.textContent = stage.dataset.attention === "true" ? "NOTE" : "STUDY";
      nibwick.dataset.phase = "study";
      if (hasAlertNotes) setControlLabel();
      else nibwick.setAttribute("aria-label", "Nibwick is studying; reduced motion is enabled");
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

    if (hasAlertNotes) setControlLabel();
    else nibwick.setAttribute("aria-label", "Pause Nibwick's desk patrol");
    if (activeReaction) {
      const reaction = REACTIONS[activeReaction];
      const reactionElapsed = performance.now() - reactionStartedAt;
      art.textContent = reaction.frames
        ? reaction.frames[Math.floor(reactionElapsed / 260) % reaction.frames.length]
        : reaction.art;
      status.textContent = reaction.label;
      nibwick.dataset.phase = "reaction";
      return;
    }

    const elapsed = (performance.now() - startedAt) % CYCLE_DURATION;
    const studying = elapsed < 5880 || (elapsed >= 21000 && elapsed < 26880);
    const clearing = elapsed >= 12600 && elapsed < 14200;
    nibwick.dataset.phase = studying ? "study" : "patrol";
    status.textContent = studying ? "STUDY" : clearing ? "CLEAR" : "PATROL";
    if (studying) {
      art.textContent = Math.floor(elapsed / 1400) % 4 === 3 ? STUDY_BLINK_FRAME : STUDY_FRAME;
    } else if (clearing) {
      art.textContent = KICK_FRAME;
    } else {
      art.textContent = WALK_FRAMES[Math.floor(elapsed / 520) % WALK_FRAMES.length];
    }
  };

  const finishReaction = (shouldRender = true) => {
    if (reactionTimer) window.clearTimeout(reactionTimer);
    reactionTimer = 0;
    if (reactionStartedAt !== null) startedAt += performance.now() - reactionStartedAt;
    reactionStartedAt = null;
    activeReaction = null;
    delete stage.dataset.reaction;
    if (shouldRender) renderFrame();
  };

  const triggerReaction = (kind) => {
    if (isPaused() || !REACTIONS[kind]) return;
    if (reactionStartedAt === null) reactionStartedAt = performance.now();
    activeReaction = kind;
    stage.dataset.reaction = kind;
    if (reactionTimer) window.clearTimeout(reactionTimer);
    reactionTimer = window.setTimeout(
      finishReaction,
      REACTIONS[kind].duration || REACTION_DURATION,
    );
    renderFrame();
  };

  const setPaused = (paused) => {
    if (paused && activeReaction) finishReaction(false);
    const now = performance.now();
    if (paused && pausedAt === null) pausedAt = now;
    if (!paused && pausedAt !== null) {
      startedAt += now - pausedAt;
      pausedAt = null;
    }
    nibwick.dataset.paused = String(paused);
    stage.dataset.paused = String(paused);
    if (hasAlertNotes) {
      nibwick.removeAttribute("aria-pressed");
      setControlLabel();
    } else {
      nibwick.setAttribute("aria-pressed", String(paused));
      localStorage.setItem(STORAGE_KEY, String(paused));
    }
    renderFrame();
  };

  nibwick.addEventListener("click", () => {
    if (hasAlertNotes) {
      document.dispatchEvent(
        new CustomEvent("nibwick:toggle-notes", { detail: { trigger: nibwick } }),
      );
      triggerReaction("notice");
      return;
    }
    if (!motionPreference.matches) setPaused(!isPaused());
  });
  document.addEventListener("nibwick:react", (event) => {
    triggerReaction(event.detail?.kind);
  });
  document.addEventListener("nibwick:panel-state", renderFrame);
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || event.target.closest("[data-nibwick]")) return;
    const reactiveTarget = event.target.closest("[data-nibwick-react], [data-period]");
    if (!reactiveTarget) return;
    triggerReaction(
      reactiveTarget.matches("[data-period]") ? "recount" : reactiveTarget.dataset.nibwickReact,
    );
  });
  motionPreference.addEventListener("change", () => {
    if (motionPreference.matches && activeReaction) finishReaction(false);
    renderFrame();
  });
  new ResizeObserver(measureStage).observe(stage);

  const storedPreference = localStorage.getItem(STORAGE_KEY);
  setPaused(hasAlertNotes ? false : storedPreference === "true");
  measureStage();
  renderFrame();
  window.setInterval(() => {
    if (!document.hidden) renderFrame();
  }, 260);
})();
