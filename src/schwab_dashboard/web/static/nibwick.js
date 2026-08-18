(() => {
  const stage = document.querySelector("[data-nibwick-stage]");
  const aisle = document.querySelector("[data-nibwick-aisle]");
  const glare = document.querySelector("[data-nibwick-glare]");
  const lantern = document.querySelector("[data-nibwick-lantern]");
  const nibwick = document.querySelector("[data-nibwick]");
  const patrolGroup = document.querySelector("[data-nibwick-patrol-group]");
  const art = document.querySelector("[data-nibwick-art]");
  const status = document.querySelector("[data-nibwick-status]");
  const alertPanel = document.querySelector("[data-nibwick-popover]");

  if (!stage || !nibwick || !art || !status) return;

  const STORAGE_KEY = "incoooming:nibwick-paused";
  const BASE_CYCLE = 42000;
  const TOP_HOLD_END = 0.14;
  const FLOOR_HOLD_START = 0.5;
  const FLOOR_HOLD_END = 0.64;
  const CLEAR_START = 0.3;
  const CLEAR_END = 0.338;
  const REACTION_DURATION = 1650;
  const AISLE_GAP = 20;
  const LOOK_SCRIPT = [
    ["along", 2000],
    ["away", 1400],
    ["camera", 1600],
    ["along", 1400],
  ];
  const LOOK_TOTAL = LOOK_SCRIPT.reduce((sum, [, ms]) => sum + ms, 0);
  const SILL_AWAY = 1400;
  const SILL_CAMERA = 1600;
  const SILL_RETURN = 520;
  const SILL_MS = SILL_AWAY + SILL_CAMERA + SILL_RETURN;
  const CYCLE_DURATION = BASE_CYCLE + SILL_MS;
  const TOP_MS = Math.round(BASE_CYCLE * TOP_HOLD_END);
  const DOWN_MS = Math.round(BASE_CYCLE * FLOOR_HOLD_START);
  const FLOOR_MS = Math.round(BASE_CYCLE * FLOOR_HOLD_END);
  const WALK_MS = Math.round(BASE_CYCLE * (FLOOR_HOLD_START - TOP_HOLD_END));
  const UP_HALF_MS = WALK_MS / 2;
  const CLEAR_MS = Math.round(BASE_CYCLE * CLEAR_START);
  const CLEAR_END_MS = Math.round(BASE_CYCLE * CLEAR_END);
  const SILL_START_MS = FLOOR_MS + UP_HALF_MS;
  const SILL_END_MS = SILL_START_MS + SILL_MS;
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
  const STAND_FRAME = makeFrame("o   o", "^", " | | ");
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
  const compactRail = window.matchMedia("(max-width: 700px)");
  let startedAt = performance.now();
  let pausedAt = null;
  let activeReaction = null;
  let reactionStartedAt = null;
  let reactionTimer = 0;
  let aisleTicks = [];
  let aisleFrame = 0;
  let heldTravel = 0;
  let heldLookAt = 0;

  const isPaused = () => nibwick.dataset.paused === "true";
  const isPatrolHeld = () =>
    isPaused() ||
    Boolean(stage.dataset.reaction) ||
    document.body.dataset.nibwickPopoverOpen === "true";

  const cycleMs = (elapsed) =>
    ((elapsed % CYCLE_DURATION) + CYCLE_DURATION) % CYCLE_DURATION;
  const atTopHold = (ms) => ms < TOP_MS;
  const atFloorHold = (ms) => ms >= DOWN_MS && ms < FLOOR_MS;
  const isStudyingAt = (ms) => atTopHold(ms) || atFloorHold(ms);
  const isClearingAt = (ms) => ms >= CLEAR_MS && ms < CLEAR_END_MS;

  const lookClock = (elapsed, studying, clearing) => {
    if (studying || clearing) return 0;
    const ms = cycleMs(elapsed);
    if (ms >= TOP_MS && ms < DOWN_MS) return ms - TOP_MS;
    if (ms >= FLOOR_MS && ms < SILL_START_MS) return ms - FLOOR_MS;
    if (ms >= SILL_END_MS) return ms - FLOOR_MS - SILL_MS;
    return 0;
  };

  const lookFace = (elapsed, studying, clearing) => {
    if (studying || clearing) return "along";
    const sill = sillFace(elapsed);
    if (sill) return sill;
    let remain = lookClock(elapsed, studying, clearing) % LOOK_TOTAL;
    for (const [face, ms] of LOOK_SCRIPT) {
      if (remain < ms) return face;
      remain -= ms;
    }
    return "along";
  };

  const sillFace = (elapsed) => {
    const ms = cycleMs(elapsed);
    if (ms < SILL_START_MS || ms >= SILL_END_MS) return "";
    const local = ms - SILL_START_MS;
    if (local < SILL_AWAY) return "away";
    if (local < SILL_AWAY + SILL_CAMERA) return "camera";
    return "along";
  };

  const patrolTravel = (elapsed) => {
    const ms = cycleMs(elapsed);
    if (ms < TOP_MS) return 0;
    if (ms < DOWN_MS) return (ms - TOP_MS) / WALK_MS;
    if (ms < FLOOR_MS) return 1;
    if (ms < SILL_START_MS) return 1 - 0.5 * (ms - FLOOR_MS) / UP_HALF_MS;
    if (ms < SILL_END_MS) return 0.5;
    return 0.5 * (1 - (ms - SILL_END_MS) / UP_HALF_MS);
  };

  const cycleElapsed = () => {
    if (isPaused() && pausedAt !== null) return (pausedAt - startedAt) % CYCLE_DURATION;
    if (reactionStartedAt !== null) return (reactionStartedAt - startedAt) % CYCLE_DURATION;
    return (performance.now() - startedAt) % CYCLE_DURATION;
  };

  const applyPatrol = () => {
    if (!patrolGroup) return;
    if (motionPreference.matches) {
      patrolGroup.style.transform = "translate3d(0, 3px, 0)";
      return;
    }
    if (compactRail.matches) {
      patrolGroup.style.transform = "none";
      return;
    }
    const distance = Number.parseFloat(stage.style.getPropertyValue("--nibwick-distance")) || 0;
    if (!isPatrolHeld()) heldTravel = patrolTravel(cycleElapsed());
    const y = 3 + heldTravel * Math.max(0, distance - 3);
    patrolGroup.style.transform = `translate3d(0, ${y}px, 0)`;
  };

  const layoutAisle = () => {
    if (!aisle) return;
    if (motionPreference.matches) {
      aisle.hidden = true;
      if (glare) glare.hidden = true;
      if (lantern) lantern.hidden = true;
      aisle.replaceChildren();
      aisleTicks = [];
      return;
    }
    if (glare) glare.hidden = true;
    if (lantern) lantern.hidden = false;
    const height = stage.clientHeight;
    const count = Math.max(3, Math.round(height / AISLE_GAP));
    if (aisleTicks.length === count && aisle.dataset.stageHeight === String(height)) {
      aisle.hidden = false;
      return;
    }
    aisle.hidden = false;
    aisle.dataset.stageHeight = String(height);
    aisle.replaceChildren();
    aisleTicks = [];
    const step = height / count;
    for (let index = 0; index < count; index += 1) {
      const tick = document.createElement("span");
      tick.className = "nibwick-tick";
      tick.dataset.side = index % 2 === 0 ? "left" : "right";
      tick.dataset.y = String(step * index + step * 0.45);
      tick.textContent = "·";
      tick.style.top = `${tick.dataset.y}px`;
      aisle.appendChild(tick);
      aisleTicks.push(tick);
    }
  };

  const applyLantern = () => {
    if (!lantern || motionPreference.matches || compactRail.matches || document.hidden) return;
    const elapsed = isPatrolHeld() ? heldLookAt : cycleElapsed();
    if (!isPatrolHeld()) heldLookAt = elapsed;
    const ms = cycleMs(elapsed);
    const studying = isStudyingAt(ms);
    const clearing = isClearingAt(ms);
    const goingDown = ms < DOWN_MS;
    const face = lookFace(elapsed, studying, clearing);
    lantern.dataset.face = face;
    lantern.dataset.dir = goingDown ? "down" : "up";
    stage.dataset.lanternFace = face;
    const lamp = lantern.getBoundingClientRect();
    const stageBox = stage.getBoundingClientRect();
    const ly = lamp.top + 2 - stageBox.top;
    aisleTicks.forEach((tick) => {
      const tickY = Number(tick.dataset.y);
      const side = tick.dataset.side;
      const near = Math.abs(tickY - ly);
      const ahead = goingDown ? tickY > ly : tickY < ly;
      const lit =
        face === "camera"
          ? side === "right" && near < 44
          : face === "away"
            ? side === "left" && near < 44
            : ahead && near < 110;
      const band = !lit ? "" : near < 28 ? "near" : near < 62 ? "mid" : "far";
      tick.classList.toggle("is-lit", band === "near");
      tick.classList.toggle("is-lit-mid", band === "mid");
      tick.classList.toggle("is-lit-far", band === "far");
      tick.classList.toggle("is-yield", near < 18);
    });
  };

  const measureStage = () => {
    const traveler = nibwick.offsetHeight || 56;
    const distance = Math.max(3, stage.clientHeight - traveler - 6);
    const value = `${distance}px`;
    if (stage.style.getPropertyValue("--nibwick-distance") !== value) {
      stage.style.setProperty("--nibwick-distance", value);
    }
    layoutAisle();
    applyPatrol();
    applyLantern();
  };

  const setControlLabel = () => {
    if (hasAlertNotes) {
      const open = alertPanel && !alertPanel.hidden;
      nibwick.setAttribute("aria-label", `${open ? "Close" : "Open"} Nibwick's notes`);
      nibwick.setAttribute("aria-expanded", String(open));
    }
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

    const elapsed = cycleElapsed();
    const ms = cycleMs(elapsed);
    const studying = isStudyingAt(ms);
    const praying = atFloorHold(ms) && !compactRail.matches;
    const clearing = isClearingAt(ms);
    const atSill = Boolean(sillFace(elapsed)) && !compactRail.matches;
    nibwick.dataset.phase = studying ? "study" : "patrol";
    status.textContent = praying ? "PRAY" : studying ? "STUDY" : clearing ? "CLEAR" : "PATROL";
    if (studying) {
      art.textContent =
        praying || Math.floor(elapsed / 1400) % 4 !== 3 ? STUDY_FRAME : STUDY_BLINK_FRAME;
    } else if (clearing) {
      art.textContent = KICK_FRAME;
    } else if (atSill) {
      art.textContent = STAND_FRAME;
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
    layoutAisle();
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
  const tickAisle = () => {
    aisleFrame = window.requestAnimationFrame(tickAisle);
    if (document.hidden) return;
    applyPatrol();
    applyLantern();
  };
  aisleFrame = window.requestAnimationFrame(tickAisle);
})();
