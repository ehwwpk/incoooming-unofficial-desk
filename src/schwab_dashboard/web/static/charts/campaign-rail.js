(() => {
  "use strict";

  const money = (value) => new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
  const day = (value) => String(value || "").slice(0, 10);

  class CampaignRail {
    constructor(root, market, { onSelect, onHover, onLeave }) {
      this.root = root;
      this.market = market;
      this.onSelect = onSelect;
      this.onHover = onHover;
      this.onLeave = onLeave;
      this.open = false;
      this.showAll = false;
      this.selected = null;
      this.hovered = null;
      this.selection = null;
    }

    setState({ selection, selected }) {
      this.selection = selection;
      this.selected = selected;
      this.render();
    }

    setHover(campaignId) {
      this.hovered = campaignId;
      this.root.querySelectorAll("[data-rail-campaign]").forEach((row) => {
        row.classList.toggle("is-hovered", row.dataset.railCampaign === campaignId);
      });
    }

    campaignSet() {
      const campaigns = (this.selection?.campaigns || []).map((item) => item.campaign);
      const open = campaigns.filter((item) => item.status === "OPEN");
      const finished = campaigns
        .filter((item) => item.status !== "OPEN")
        .sort((a, b) => day(b.latest_on).localeCompare(day(a.latest_on)));
      return {
        all: campaigns,
        open,
        finished,
        shown: this.showAll ? [...open, ...finished] : [...open, ...finished.slice(0, 3)],
        hidden: Math.max(0, finished.length - 3),
      };
    }

    render() {
      if (!this.root || !this.selection) return;
      const campaigns = this.campaignSet();
      this.root.replaceChildren();
      this.root.classList.toggle("is-open", this.open);
      this.root.hidden = !campaigns.all.length;
      if (!campaigns.all.length) return;

      const header = document.createElement("header");
      const disclosure = document.createElement("button");
      disclosure.type = "button";
      disclosure.className = "campaign-rail-toggle";
      disclosure.setAttribute("aria-expanded", String(this.open));
      disclosure.setAttribute(
        "aria-label",
        `${this.open ? "Close" : "Open"} campaign rail; ${campaigns.all.length} campaigns, ${campaigns.open.length} open`,
      );

      const title = document.createElement("span");
      title.className = "campaign-rail-title";
      title.textContent = "CAMPAIGNS";
      const count = document.createElement("small");
      count.textContent = `${campaigns.all.length} IN VIEW \u00b7 ${campaigns.open.length} OPEN`;
      const legend = document.createElement("span");
      legend.className = "campaign-rail-legend";
      legend.textContent = "GOLD = TIME OPEN \u00b7 GRAY = FINISHED";
      const cue = document.createElement("span");
      cue.className = "campaign-rail-cue";
      cue.textContent = this.open ? "CLOSE RAIL" : "OPEN RAIL";
      const chevron = document.createElement("span");
      chevron.className = "campaign-rail-chevron";
      chevron.setAttribute("aria-hidden", "true");
      chevron.textContent = "+";
      disclosure.append(title, count, legend, cue, chevron);
      disclosure.addEventListener("click", () => {
        this.open = !this.open;
        this.render();
      });
      header.append(disclosure);
      this.root.append(header);

      if (!this.open) return;

      const rows = document.createElement("div");
      rows.className = "campaign-rail-rows";
      campaigns.shown.forEach((campaign) => rows.append(this.row(campaign)));
      this.root.append(rows);

      if (campaigns.hidden || this.showAll) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "campaign-rail-more";
        more.textContent = this.showAll ? "SHOW RECENT ONLY" : `SHOW ${campaigns.hidden} OLDER`;
        more.setAttribute("aria-expanded", String(this.showAll));
        more.addEventListener("click", () => {
          this.showAll = !this.showAll;
          this.render();
        });
        this.root.append(more);
      }
    }

    row(campaign) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "campaign-rail-row";
      row.dataset.railCampaign = campaign.id;
      row.classList.toggle("is-selected", campaign.id === this.selected);
      row.classList.toggle("is-hovered", campaign.id === this.hovered);

      const identity = document.createElement("span");
      identity.className = "campaign-rail-identity";
      const latest = campaign.legs.at(-1);
      const side = campaign.option_side === "put" ? "P" : "C";
      const strike = Number(latest.strike).toFixed(Number(latest.strike) % 1 ? 1 : 0);
      const code = document.createElement("b");
      code.textContent = campaign.label;
      const contract = document.createElement("span");
      contract.textContent = `${Math.abs(latest.contracts)}\u00d7 $${strike}${side} \u00b7 EXP ${day(latest.expiration).slice(5)}`;
      identity.append(code, contract);

      const track = document.createElement("span");
      track.className = "campaign-rail-track";
      const first = campaign.legs[0];
      const isSettling = Boolean(campaign.settlement)
        && campaign.settlement.can_close_or_roll === false;
      const coverage = this.market.coverage();
      const rangeStart = Date.parse(`${day(this.selection.start || coverage.from)}T00:00:00Z`);
      const rangeEnd = Date.parse(`${day(this.selection.end || coverage.to)}T00:00:00Z`);
      const spanDays = Math.max(1, rangeEnd - rangeStart);
      const startAt = Date.parse(`${day(first.time)}T00:00:00Z`);
      const endAt = campaign.status === "OPEN"
        ? rangeEnd
        : isSettling
          ? Date.parse(`${day(latest.expiration)}T00:00:00Z`)
        : Date.parse(`${day(latest.time)}T00:00:00Z`);
      const left = Math.max(0, Math.min(100, (startAt - rangeStart) / spanDays * 100));
      const right = Math.max(left, Math.min(100, (endAt - rangeStart) / spanDays * 100));
      if ([left, right].every(Number.isFinite)) {
        const span = document.createElement("i");
        span.style.left = `${left}%`;
        span.style.width = `${Math.max(1, right - left)}%`;
        span.classList.toggle("is-open", campaign.status === "OPEN");
        span.classList.toggle("is-settling", isSettling);
        span.title = isSettling
          ? `Trading closed at expiration; ${campaign.settlement.expectation_label.toLowerCase()}; broker confirmation pending`
          : campaign.status === "OPEN"
          ? `Still open from ${day(first.time)} through the latest chart date`
          : `Open from ${day(first.time)} until ${day(latest.time)}`;
        track.append(span);
      }
      track.setAttribute("aria-label", isSettling
        ? `Campaign trading closed at expiration; broker confirmation pending`
        : campaign.status === "OPEN"
        ? `Campaign has remained open since ${day(first.time)}`
        : `Campaign ran from ${day(first.time)} through ${day(latest.time)}`);

      const result = document.createElement("span");
      result.className = "campaign-rail-result";
      const status = document.createElement("b");
      status.textContent = isSettling ? "SETTLING" : campaign.status === "OPEN" ? "OPEN" : campaign.status;
      const cash = document.createElement("span");
      cash.textContent = money(campaign.net_cash);
      result.append(status, cash);
      row.append(identity, track, result);
      row.addEventListener("mouseenter", () => this.onHover?.(campaign.id));
      row.addEventListener("mouseleave", () => this.onLeave?.());
      row.addEventListener("click", () => this.onSelect?.(campaign));
      return row;
    }
  }

  window.IncooomingCampaignRail = CampaignRail;
})();
