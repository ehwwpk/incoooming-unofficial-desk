(() => {
  const statusRoot = document.querySelector("[data-sync-status-root]");
  if (!statusRoot || document.body.dataset.demoMode === "true") return;

  const stateLabel = statusRoot.querySelector("[data-sync-state]");
  const detail = statusRoot.querySelector("[data-sync-detail]");
  const syncButton = statusRoot.querySelector("[data-sync-now]");
  const serverHealth = statusRoot.querySelector("[data-server-health]");
  // Market observations can be older than the sync run that fetched them on
  // weekends, holidays, and after hours. Comparing those two different clocks
  // makes every fresh page look stale and creates an endless reload loop.
  const pageBuiltAt = Date.parse(document.body.dataset.pageBuiltAt || "");
  const VIEW_STATE_KEY = "incoooming:auto-refresh-view";
  let reloadQueued = false;

  const setState = (label, tone) => {
    if (!stateLabel) return;
    stateLabel.textContent = label;
    stateLabel.classList.remove("positive", "negative", "muted");
    stateLabel.classList.add(tone);
  };

  const localTime = (value) => {
    const parsed = parseServerTime(value);
    if (!Number.isFinite(parsed)) return "NO SUCCESSFUL SNAPSHOT";
    return `SYNCED ${new Date(parsed).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    })}`;
  };

  const parseServerTime = (value) => {
    if (!value) return Number.NaN;
    const normalized = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`;
    return Date.parse(normalized);
  };

  const poll = async () => {
    try {
      const [healthResponse, response] = await Promise.all([
        fetch("/api/v1/health/ready", {
          cache: "no-store",
          headers: { Accept: "application/json" },
        }),
        fetch("/api/v1/sync/status", {
        cache: "no-store",
        headers: { Accept: "application/json" },
        }),
      ]);
      if (!healthResponse.ok) throw new Error(`Server health ${healthResponse.status}`);
      if (!response.ok) throw new Error(`Sync status ${response.status}`);
      if (serverHealth) {
        serverHealth.dataset.state = "ready";
        serverHealth.title = "Local server and ledger database are ready";
        serverHealth.setAttribute("aria-label", serverHealth.title);
      }
      const status = await response.json();
      if (syncButton) syncButton.disabled = status.running;

      if (status.state === "syncing") setState("SYNCING", "muted");
      else if (status.state === "authorization_required") {
        setState("RECONNECT SCHWAB", "negative");
      } else if (status.state === "attention") setState("SYNC ATTENTION", "negative");
      else if (status.state === "waiting") setState("WAITING TO SYNC", "muted");
      else setState("SYNCED", "positive");

      if (detail) {
        const intervalMinutes = Math.max(1, Math.round(status.interval_seconds / 60));
        const error = status.last_error || status.latest_attempt_error;
        detail.textContent = error
          ? `${error} / AUTO PAUSED`
          : `${localTime(status.latest_successful_at)} / AUTO ${intervalMinutes}M`;
        detail.title = error || "";
      }

      const latestObservedAt = parseServerTime(status.latest_successful_at);
      if (
        !reloadQueued &&
        !status.running &&
        Number.isFinite(pageBuiltAt) &&
        Number.isFinite(latestObservedAt) &&
        latestObservedAt > pageBuiltAt + 1000 &&
        document.visibilityState === "visible"
      ) {
        reloadQueued = true;
        const openDetails = [...document.querySelectorAll("details[open][id]")]
          .map((node) => node.id)
          .filter(Boolean);
        try {
          sessionStorage.setItem(
            VIEW_STATE_KEY,
            JSON.stringify({
              path: `${window.location.pathname}${window.location.search}`,
              openDetails,
              scrollY: window.scrollY,
            }),
          );
        } catch (_) {
          // Refresh still proceeds when browser storage is disabled.
        }
        window.location.reload();
      }
    } catch (_) {
      if (serverHealth) {
        serverHealth.dataset.state = "offline";
        serverHealth.title = "Local server health check failed";
        serverHealth.setAttribute("aria-label", serverHealth.title);
      }
      setState("SYNC STATUS OFFLINE", "negative");
      if (detail) detail.textContent = "Dashboard is open / freshness check unavailable";
    }
  };

  window.setTimeout(poll, 1500);
  window.setInterval(poll, 30000);
  window.addEventListener("focus", poll);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });
})();
