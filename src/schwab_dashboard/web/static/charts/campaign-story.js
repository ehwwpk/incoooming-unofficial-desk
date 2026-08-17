(() => {
  "use strict";

  const money = (value) => new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
  const strike = (value) => Number(value || 0).toFixed(Number(value || 0) % 1 ? 1 : 0);
  const plural = (value, word) => `${value} ${word}${value === 1 ? "" : "s"}`;

  function timestamp(value) {
    const raw = String(value || "");
    const exact = raw.includes("T");
    const parsed = new Date(exact ? raw : `${raw.slice(0, 10)}T12:00:00Z`);
    if (!Number.isFinite(parsed.getTime())) return { label: raw, exact: raw };
    const label = parsed.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "America/New_York",
    });
    return { label, exact: raw };
  }

  function sameMoment(left, right) {
    if (!left || !right) return false;
    const a = String(left.time || "");
    const b = String(right.time || "");
    return a === b || (a.slice(0, 10) === b.slice(0, 10) && (!a.includes("T") || !b.includes("T")));
  }

  function isRoll(leg) {
    const event = String(leg?.event_type || "").toUpperCase();
    const outcome = String(leg?.outcome || "").toUpperCase();
    return event.includes("ROLL") || outcome === "ROLLED";
  }

  function isClose(leg) {
    const event = String(leg?.event_type || "").toUpperCase();
    const outcome = String(leg?.outcome || "").toUpperCase();
    return outcome === "CLOSED" || event.includes("CLOSE");
  }

  function instrument(leg) {
    return String(leg.option_side || "call").toLowerCase() === "put" ? "put" : "call";
  }

  function quantity(leg) {
    return Math.abs(Number(leg.contracts || 0));
  }

  function expiry(leg) {
    return timestamp(leg.expiration).label;
  }

  function contractPhrase(leg) {
    const count = quantity(leg);
    const contract = `$${strike(leg.strike)} ${instrument(leg)}`;
    return `${count}\u00d7 ${contract}${count === 1 ? "" : "s"}`;
  }

  function stepText(leg) {
    const outcome = String(leg.outcome || "").toUpperCase();
    const event = String(leg.event_type || "").toUpperCase();
    const side = instrument(leg);
    const qty = quantity(leg);
    if (event.includes("SALE") || event.includes("SELL")) {
      return `Sold ${contractPhrase(leg)} expiring ${expiry(leg)}.`;
    }
    if (outcome === "EXPIRED") return `The $${strike(leg.strike)} ${side} expired. Premium stayed home.`;
    if (outcome === "ASSIGNED") {
      return side === "call"
        ? `${plural(qty * 100, "share")} got called away at $${strike(leg.strike)}.`
        : `${plural(qty * 100, "share")} were assigned at $${strike(leg.strike)}.`;
    }
    if (isClose(leg)) return `Bought back ${contractPhrase(leg)} early.`;
    if (isRoll(leg)) return `Rolled into ${contractPhrase(leg)} expiring ${expiry(leg)}.`;
    if (outcome === "OPEN") {
      return `Sold ${contractPhrase(leg)} expiring ${expiry(leg)}.`;
    }
    return `${contractPhrase(leg)} \u00b7 ${outcome || event || "updated"}.`;
  }

  function storySteps(campaign) {
    const legs = campaign.legs || [];
    const steps = [];
    for (let index = 0; index < legs.length; index += 1) {
      const leg = legs[index];
      const next = legs[index + 1];
      if (isClose(leg) && isRoll(next) && sameMoment(leg, next)) {
        const oldSide = instrument(leg);
        const newSide = instrument(next);
        const direction = Number(next.strike) > Number(leg.strike)
          ? "up"
          : Number(next.strike) < Number(leg.strike) ? "down" : "out";
        const status = String(next.outcome).toUpperCase() === "OPEN" ? "still working" : "now finished";
        const text = direction === "out"
          ? `Rolled the $${strike(leg.strike)} ${oldSide} out to ${expiry(next)}; the new ${newSide} is ${status}.`
          : `Rolled the $${strike(leg.strike)} ${oldSide} ${direction} to $${strike(next.strike)} for ${expiry(next)}; the new ${newSide} is ${status}.`;
        steps.push({ time: leg.time, text, exact: `${leg.time} / ${next.time}` });
        index += 1;
      } else {
        steps.push({ time: leg.time, text: stepText(leg), exact: String(leg.time || "") });
      }
    }
    return steps;
  }

  function appendTimeline(target, steps) {
    const timeline = document.createElement("ol");
    steps.forEach((step) => {
      const item = document.createElement("li");
      const when = timestamp(step.time);
      const time = document.createElement("time");
      time.dateTime = String(step.time || "");
      time.title = step.exact || when.exact;
      time.textContent = when.label.toUpperCase();
      const text = document.createElement("span");
      text.textContent = step.text;
      item.append(time, text);
      timeline.append(item);
    });
    target.append(timeline);
  }

  function renderCampaign(target, campaign) {
    if (!target || !campaign) return;
    target.innerHTML = "";
    const identity = document.createElement("span");
    const side = String(campaign.option_side || "call").toUpperCase();
    const current = [...(campaign.legs || [])].reverse().find((leg) => Boolean(leg.is_open));
    identity.textContent = campaign.status === "OPEN" && current
      ? `${campaign.label} \u00b7 NOW OPEN ${contractPhrase(current).toUpperCase()} \u00b7 EXP ${expiry(current).toUpperCase()}`
      : `${campaign.label} \u00b7 ${side} FINISHED`;
    const story = document.createElement("p");
    const moves = storySteps(campaign);
    const ending = campaign.status === "OPEN" ? "Still working." : "Campaign finished.";
    story.textContent = `${ending} ${money(campaign.net_cash)} net cash across ${plural(moves.length, "move")}.`;
    target.append(identity, story);
    appendTimeline(target, moves);
  }

  function renderCluster(target, items) {
    if (!target || !items.length) return;
    const campaigns = [...new Map(items.map(({ campaign }) => [campaign.id, campaign])).values()];
    target.innerHTML = "";
    const identity = document.createElement("span");
    identity.textContent = `${plural(campaigns.length, "CAMPAIGN")} HERE`;
    const story = document.createElement("p");
    story.textContent = "Pick one. Nibwick will trace only that path.";
    target.append(identity, story);
    appendTimeline(target, campaigns.map((campaign) => ({
      time: campaign.latest_on,
      exact: campaign.latest_on,
      text: `${campaign.label} \u00b7 ${campaign.status === "OPEN" ? "still working" : "finished"} \u00b7 ${money(campaign.net_cash)} net cash`,
    })));
  }

  function renderOverview(target, campaigns) {
    if (!target) return;
    const open = campaigns.filter((campaign) => campaign.status === "OPEN").length;
    const finished = campaigns.length - open;
    target.innerHTML = "";
    const identity = document.createElement("span");
    identity.textContent = "CAMPAIGN MAP";
    const summary = document.createElement("p");
    summary.textContent = `${open} still working \u00b7 ${finished} finished. Hover to peek; click to hold one story.`;
    target.append(identity, summary);
  }

  window.IncooomingCampaignStory = { renderCampaign, renderCluster, renderOverview };
})();
