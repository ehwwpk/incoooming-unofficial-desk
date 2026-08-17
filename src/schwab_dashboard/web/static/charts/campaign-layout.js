(() => {
  "use strict";

  const DAY = 86_400_000;
  const MAJOR_OUTCOMES = new Set(["ASSIGNED", "CLOSED", "EXPIRED", "ROLLED"]);

  function rangeStart(bars, key) {
    if (!bars.length) return null;
    if (key === "max") return String(bars[0].time).slice(0, 10);
    const days = { "4w": 28, "8w": 56, "16w": 112, "1y": 365 }[key] ?? 112;
    const end = Date.parse(`${String(bars.at(-1).time).slice(0, 10)}T00:00:00Z`);
    return new Date(end - days * DAY).toISOString().slice(0, 10);
  }

  function semanticLevel(logicalSpan) {
    if (logicalSpan <= 48) return "close";
    if (logicalSpan <= 126) return "medium";
    return "wide";
  }

  function campaignCode(campaign, ordinal) {
    const prefix = campaign.option_side === "put" ? "P" : "C";
    return `${prefix}${ordinal + 1}`;
  }

  function inMode(campaign, mode) {
    return mode !== "active" || campaign.status === "OPEN";
  }

  function lifecycleLegs(campaign, start, end) {
    const ordered = campaign.legs.slice().sort((a, b) =>
      a.time.localeCompare(b.time) || a.sequence - b.sequence || a.leg_index - b.leg_index,
    );
    const firstVisible = ordered.findIndex((leg) => (!start || leg.time >= start) && (!end || leg.time <= end));
    if (firstVisible < 0) return [];
    let lastVisible = firstVisible;
    while (lastVisible + 1 < ordered.length && (!end || ordered[lastVisible + 1].time <= end)) {
      lastVisible += 1;
    }
    return ordered.slice(Math.max(0, firstVisible - 1), lastVisible + 1);
  }

  function displayLegs(legs, level) {
    if (level !== "wide" || legs.length <= 3) return legs;
    return legs.filter((leg, index) =>
      index === 0 ||
      index === legs.length - 1 ||
      MAJOR_OUTCOMES.has(String(leg.outcome || "").toUpperCase()) ||
      String(leg.event_type || "").toLowerCase().includes("roll"),
    );
  }

  function selection(payload, mode, rangeKey, logicalSpan = 112, activeBars = payload.bars, visibleRange = null) {
    const requestedStart = rangeStart(activeBars, rangeKey);
    const coverageStart = activeBars.length ? String(activeBars[0].time).slice(0, 10) : null;
    const coverageEnd = activeBars.length ? String(activeBars.at(-1).time).slice(0, 10) : null;
    const starts = [requestedStart, coverageStart, visibleRange?.from].filter(Boolean).sort();
    const start = starts.at(-1) || null;
    const ends = [coverageEnd, visibleRange?.to].filter(Boolean).sort();
    const end = ends[0] || null;
    const level = semanticLevel(logicalSpan);
    const campaigns = payload.campaigns
      .map((campaign, ordinal) => ({ ...campaign, code: campaignCode(campaign, ordinal) }))
      .filter((campaign) => inMode(campaign, mode))
      .map((campaign) => {
        let path = lifecycleLegs(campaign, start, end);
        // A live obligation remains relevant even when its latest transaction
        // sits outside the visible price window. Keep its final reconciled leg
        // available to the context layer without inventing an on-screen event.
        if (!path.length && campaign.status === "OPEN" && campaign.legs.length) {
          path = campaign.legs
            .slice()
            .sort((a, b) =>
              a.time.localeCompare(b.time) || a.sequence - b.sequence || a.leg_index - b.leg_index,
            )
            .slice(-1);
        }
        const visible = path.filter((leg) => (!start || leg.time >= start) && (!end || leg.time <= end));
        return {
          campaign,
          path,
          // Preserve one predecessor for a truthful path entering the viewport,
          // but never pin an off-screen event marker to the left chart edge.
          nodes: displayLegs(visible, level),
          entersFromHistory: Boolean(path.length && start && path[0].time < start),
          visibleEvents: visible.length,
        };
      })
      .filter((item) => item.path.length);
    return {
      start,
      end,
      level,
      campaigns,
      visibleEvents: campaigns.reduce((total, item) => total + item.visibleEvents, 0),
      enteringCampaigns: campaigns.filter((item) => item.entersFromHistory).length,
    };
  }

  function cluster(positioned, minDistance = 30) {
    const groups = [];
    positioned
      .slice()
      .sort((a, b) => a.x - b.x || a.y - b.y)
      .forEach((item) => {
        const group = groups.find((candidate) =>
          Math.abs(candidate.x - item.x) < minDistance &&
          Math.abs(candidate.y - item.y) < minDistance,
        );
        if (!group) {
          groups.push({ x: item.x, y: item.y, items: [item] });
          return;
        }
        const lane = group.items.length;
        item.displayX = item.x + (lane % 2 ? 1 : -1) * (12 + Math.floor(lane / 2) * 9);
        item.displayY = item.y + (lane % 3 - 1) * 13;
        group.items.push(item);
      });
    return groups;
  }

  window.IncooomingCampaignLayout = {
    rangeStart,
    semanticLevel,
    selection,
    cluster,
  };
})();
