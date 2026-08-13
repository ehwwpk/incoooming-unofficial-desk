(() => {
  const statusRoot = document.querySelector("[data-sync-status-root]");
  if (!statusRoot || document.body.dataset.demoMode === "true") return;

  const stateLabel = statusRoot.querySelector("[data-sync-state]");
  const detail = statusRoot.querySelector("[data-sync-detail]");
  const syncButton = statusRoot.querySelector("[data-sync-now]");
  const serverHealth = statusRoot.querySelector("[data-server-health]");
  const pageObservedAt = Date.parse(document.body.dataset.snapshotAsOf || "");
  let reloadQueued = false;

  const setState = (label, tone) => {
    if (!stateLabel) return;
    stateLabel.textContent = label;
    stateLabel.classList.remove("positive", "negative", "muted");
    stateLabel.classList.add(tone);
  };

  const localTime = (value) => {
    const parsed = Date.parse(value || "");
    if (!Number.isFinite(parsed)) return "NO SUCCESSFUL SNAPSHOT";
    return `SYNCED ${new Date(parsed).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    })}`;
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

      const latestObservedAt = Date.parse(status.latest_successful_at || "");
      if (
        !reloadQueued &&
        !status.running &&
        Number.isFinite(pageObservedAt) &&
        Number.isFinite(latestObservedAt) &&
        latestObservedAt > pageObservedAt + 1000 &&
        document.visibilityState === "visible"
      ) {
        reloadQueued = true;
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
