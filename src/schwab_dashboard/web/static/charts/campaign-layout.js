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

  function lifecycleLegs(campaign, start) {
    const ordered = campaign.legs.slice().sort((a, b) =>
      a.time.localeCompare(b.time) || a.sequence - b.sequence || a.leg_index - b.leg_index,
    );
    const firstVisible = ordered.findIndex((leg) => leg.time >= start);
    if (firstVisible < 0) return [];
    return ordered.slice(Math.max(0, firstVisible - 1));
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

  function selection(payload, mode, rangeKey, logicalSpan = 112, activeBars = payload.bars) {
    const start = rangeStart(activeBars, rangeKey);
    const level = semanticLevel(logicalSpan);
    const campaigns = payload.campaigns
      .map((campaign, ordinal) => ({ ...campaign, code: campaignCode(campaign, ordinal) }))
      .filter((campaign) => inMode(campaign, mode))
      .map((campaign) => {
        const path = lifecycleLegs(campaign, start);
        return {
          campaign,
          path,
          // Preserve one predecessor for a truthful path entering the viewport,
          // but never pin an off-screen event marker to the left chart edge.
          nodes: displayLegs(path.filter((leg) => leg.time >= start), level),
        };
      })
      .filter((item) => item.path.length);
    return { start, level, campaigns };
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
