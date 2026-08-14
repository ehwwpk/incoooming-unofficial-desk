(() => {
  "use strict";

  const money = (value) => {
    const number = Number(value || 0);
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(number);
  };

  function renderCampaign(target, campaign) {
    if (!target || !campaign) return;
    const latest = campaign.legs.at(-1);
    target.innerHTML = "";
    const identity = document.createElement("span");
    identity.textContent = `${campaign.label} · ${campaign.option_side.toUpperCase()} · ${campaign.status}`;
    const story = document.createElement("p");
    story.textContent = `${campaign.legs.length} leg${campaign.legs.length === 1 ? "" : "s"} · ${money(campaign.net_cash)} net cash · latest ${latest.time} at $${Number(latest.underlying_price).toFixed(2)}`;
    const timeline = document.createElement("ol");
    campaign.legs.forEach((leg) => {
      const item = document.createElement("li");
      item.textContent = `${leg.time}  ${leg.event_type.toUpperCase()}  ${Math.abs(leg.contracts)}× $${Number(leg.strike).toFixed(0)} ${leg.option_side.toUpperCase()}  ${leg.outcome}`;
      timeline.append(item);
    });
    target.append(identity, story, timeline);
  }

  function renderCluster(target, items) {
    if (!target || !items.length) return;
    const campaigns = [...new Map(items.map(({ campaign }) => [campaign.id, campaign])).values()];
    target.innerHTML = "";
    const identity = document.createElement("span");
    identity.textContent = `${campaigns.length} CAMPAIGN${campaigns.length === 1 ? "" : "S"} · SAME CHART NEIGHBORHOOD`;
    const story = document.createElement("p");
    story.textContent = "Pick one below; the chart draws only that campaign's path.";
    const timeline = document.createElement("ol");
    campaigns.forEach((campaign) => {
      const item = document.createElement("li");
      item.textContent = `${campaign.label}  ${campaign.status}  ${money(campaign.net_cash)}`;
      timeline.append(item);
    });
    target.append(identity, story, timeline);
  }

  function renderOverview(target, campaigns) {
    if (!target) return;
    const open = campaigns.filter((campaign) => campaign.status === "OPEN").length;
    target.innerHTML = "";
    const identity = document.createElement("span");
    identity.textContent = "CAMPAIGN MAP";
    const summary = document.createElement("p");
    summary.textContent = `${open} open · ${campaigns.length} total. Squares are calls; diamonds are puts. Click one to isolate its path.`;
    target.append(identity, summary);
  }

  window.IncooomingCampaignStory = { renderCampaign, renderCluster, renderOverview };
})();
