(() => {
  "use strict";

  const layout = window.IncooomingCampaignLayout;
  const story = window.IncooomingCampaignStory;
  const MarketLayer = window.IncooomingCampaignMarketLayer;
  const LifecycleLayer = window.IncooomingCampaignLifecycleLayer;
  const Indicators = window.IncooomingCampaignIndicators;
  const FocusController = window.IncooomingCampaignFocusController;
  if (!layout || !story || !MarketLayer || !LifecycleLayer || !Indicators || !FocusController) return;

  const number = (value) => Number(value || 0);
  const dayKey = (value) => String(value || "").slice(0, 10);
  const money = (value) => new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(number(value));
  const shortDate = (value) => new Date(`${dayKey(value)}T12:00:00Z`)
    .toLocaleDateString("en-US", { month: "short", day: "2-digit" }).toUpperCase();
  const strike = (value) => number(value).toFixed(number(value) % 1 ? 1 : 0);

  function legAction(leg) {
    const outcome = String(leg.outcome || "").toUpperCase();
    const event = String(leg.event_type || "").toUpperCase();
    if (event.includes("ROLL") || outcome === "ROLLED") return "ROLLED";
    if (["ASSIGNED", "EXPIRED", "CLOSED"].includes(outcome)) return outcome;
    return "SOLD";
  }

  class CampaignChartController {
    constructor(shell) {
      this.shell = shell;
      this.shell.dataset.runtime = "campaign-chart-v6";
      this.card = shell.closest("details");
      this.fallback = shell.parentElement.querySelector("[data-campaign-chart-fallback]");
      this.stage = shell.querySelector("[data-campaign-chart-stage]");
      this.canvas = shell.querySelector("[data-campaign-chart-canvas]");
      this.lifecycleCanvas = shell.querySelector("[data-campaign-chart-lifecycle]");
      this.popover = shell.querySelector("[data-campaign-chart-popover]");
      this.story = shell.querySelector("[data-campaign-story]");
      this.readout = shell.querySelector("[data-campaign-chart-readout]");
      this.mode = "all";
      this.range = "16w";
      this.style = "candles";
      this.intervalMode = "auto";
      this.shares = false;
      this.selected = null;
      this.ready = false;
      this.booting = false;
      this.bind();
      if (this.card?.open) this.boot();
    }

    bind() {
      this.shell.dataset.controlsBound = "true";
      this.card?.addEventListener("toggle", () => {
        if (this.card.open) this.boot();
      });
      this.shell.querySelectorAll("[data-campaign-mode]").forEach((button) => {
        button.addEventListener("click", () => {
          this.mode = button.dataset.campaignMode;
          this.press("[data-campaign-mode]", button);
          this.render();
        });
      });
      this.shell.querySelectorAll("[data-campaign-range]").forEach((button) => {
        button.addEventListener("click", () => {
          this.range = button.dataset.campaignRange;
          this.press("[data-campaign-range]", button);
          this.applyResolution();
          this.applyRange();
        });
      });
      this.shell.querySelectorAll("[data-campaign-interval]").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.disabled) return;
          this.intervalMode = button.dataset.campaignInterval;
          this.press("[data-campaign-interval]", button);
          this.applyResolution();
          this.applyRange();
        });
      });
      this.shell.querySelectorAll("[data-campaign-style]").forEach((button) => {
        button.addEventListener("click", () => {
          this.style = button.dataset.campaignStyle;
          this.press("[data-campaign-style]", button);
          this.market?.setStyle(this.style);
          this.lifecycle?.schedule();
        });
      });
      this.shell.querySelectorAll("[data-campaign-indicator]").forEach((button) => {
        button.addEventListener("click", () => {
          const enabled = this.indicators?.toggle(button.dataset.campaignIndicator);
          button.setAttribute("aria-pressed", String(Boolean(enabled)));
          requestAnimationFrame(() => this.lifecycle?.schedule());
        });
      });
      this.shell.querySelector("[data-campaign-shares]")?.addEventListener("click", (event) => {
        this.shares = !this.shares;
        event.currentTarget.setAttribute("aria-pressed", String(this.shares));
        event.currentTarget.textContent = this.shares ? "SHARES ON" : "SHARES OFF";
        this.render();
      });
      this.shell.querySelector("[data-campaign-fit]")?.addEventListener("click", () => {
        this.market?.fit();
        this.lifecycle?.schedule();
      });
    }

    press(selector, active) {
      this.shell.querySelectorAll(selector).forEach((button) =>
        button.setAttribute("aria-pressed", String(button === active)),
      );
    }

    async boot() {
      if (this.ready || this.booting) return;
      this.booting = true;
      try {
        const response = await fetch(this.shell.dataset.endpoint, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error(`chart payload ${response.status}`);
        this.shell.hidden = false;
        this.payload = await response.json();
        this.createChart();
        if (this.fallback) this.fallback.hidden = true;
        this.ready = true;
        this.audit();
        this.applyResolution();
        this.applyRange();
      } catch (error) {
        console.error("Campaign chart unavailable.", error);
        this.shell.hidden = true;
        if (this.fallback) this.fallback.hidden = false;
      } finally {
        this.booting = false;
      }
    }

    createChart() {
      this.market = new MarketLayer(this.canvas, this.payload, this.readout);
      this.market.setStyle(this.style);
      this.indicators = new Indicators(this.market, this.stage);
      this.lifecycle = new LifecycleLayer({
        stage: this.stage,
        canvas: this.lifecycleCanvas,
        chart: this.market.chart,
        priceSeries: this.market.candles,
        timeForDate: (value) => this.market.timeForDate(value),
        onSelect: (campaign) => this.selectCampaign(campaign),
        onHover: (hit, point) => this.showPopover(hit, point),
        onLeave: () => { this.popover.hidden = true; },
      });
      const available = new Set(this.market.availableIntervals());
      this.shell.querySelectorAll("[data-campaign-interval]").forEach((button) => {
        const key = button.dataset.campaignInterval;
        button.disabled = key !== "auto" && !available.has(key);
        if (button.disabled) button.title = `${button.textContent} bars are not stored yet`;
      });
      this.focus = new FocusController(
        this.shell,
        this.shell.querySelector("[data-campaign-focus]"),
        () => this.applyRange(),
      );
      this.market.onViewport(() => this.render());
      story.renderOverview(this.story, this.payload.campaigns);
      this.resize = new ResizeObserver(() => this.lifecycle.schedule());
      this.resize.observe(this.stage);
    }

    audit() {
      const audit = this.payload.audit;
      const target = this.shell.querySelector("[data-campaign-chart-audit]");
      const review = audit.unknown_campaigns + audit.needs_review_campaigns;
      target.textContent = `${audit.campaigns} CAMPAIGNS · ${audit.exact_campaigns} EXACT · ${audit.inferred_campaigns} INFERRED${review ? ` · ${review} NEED REVIEW` : ""}`;
      target.classList.toggle("attention", review > 0);
    }

    applyResolution() {
      if (!this.market) return;
      const key = this.intervalMode === "auto"
        ? this.market.bestInterval(this.range)
        : this.intervalMode;
      this.market.setInterval(key);
      this.market.setStyle(this.style);
      this.indicators?.refresh();
      this.shell.dataset.activeInterval = key;
      this.lifecycle?.schedule();
    }

    applyRange() {
      if (!this.ready) return;
      const bars = this.market.bars();
      const start = layout.rangeStart(bars, this.range);
      const end = bars.at(-1)?.time;
      this.visibleStart = start;
      this.market.setRange(start, end);
      const visibleBars = bars.filter((bar) => !start || dayKey(bar.time) >= start).length;
      const interval = this.market.intervals.get(this.market.interval);
      const coverage = interval?.extended_hours ? " · EXTENDED HOURS" : "";
      this.shell.querySelector("[data-campaign-chart-meta]").textContent = `${visibleBars} ${interval?.label || "1D"} BARS${coverage} · ${this.payload.audit.events} OPTION EVENTS`;
      this.shell.querySelector("[data-campaign-series-label]").textContent = `${interval?.label || "1D"} SCHWAB OHLC${coverage}`;
      requestAnimationFrame(() => this.render());
    }

    render() {
      if (!this.ready) return;
      const selection = layout.selection(
        this.payload,
        this.mode,
        this.range,
        this.market.logicalSpan(),
        this.market.bars(),
      );
      const shares = this.shares
        ? this.payload.share_events.filter((item) => dayKey(item.time) >= selection.start)
        : [];
      if (!selection.campaigns.length) {
        this.story.innerHTML = "<span>NO CAMPAIGNS HERE</span><p>Show all campaigns or widen the time range.</p>";
      }
      this.lifecycle.setState({ selection, selected: this.selected, shares });
    }

    selectCampaign(campaign) {
      this.selected = this.selected === campaign.id ? null : campaign.id;
      if (this.selected) story.renderCampaign(this.story, campaign);
      else story.renderOverview(this.story, this.payload.campaigns);
      this.render();
    }

    showPopover(hit, point) {
      this.popover.replaceChildren();
      if (hit.kind === "share") {
        const title = document.createElement("b");
        title.textContent = `${String(hit.item.action || "shares").toUpperCase()} · ${hit.item.shares} SHARES`;
        const detail = document.createElement("span");
        detail.textContent = `${shortDate(hit.item.time)} · $${number(hit.item.price).toFixed(2)} · ${hit.item.detail}`;
        this.popover.append(title, detail);
      } else {
        const { campaign, leg } = hit;
        const title = document.createElement("b");
        title.textContent = `${legAction(leg)} ${Math.abs(leg.contracts)}× $${strike(leg.strike)} ${leg.option_side.toUpperCase()}`;
        const contract = document.createElement("span");
        contract.textContent = `${shortDate(leg.time)} · EXP ${shortDate(leg.expiration)} · ${Math.max(0, Math.round((Date.parse(leg.expiration) - Date.parse(leg.time)) / 86_400_000))} DTE`;
        const detail = document.createElement("small");
        detail.textContent = `STOCK $${number(leg.underlying_price).toFixed(2)} · ${money(leg.net_cash)} THIS LEG · ${money(campaign.net_cash)} CAMPAIGN`;
        this.popover.append(title, contract, detail);
      }
      this.popover.hidden = false;
      const half = Math.min(150, this.stage.clientWidth / 2 - 10);
      this.popover.style.left = `${Math.min(Math.max(point.x, half), this.stage.clientWidth - half)}px`;
      this.popover.classList.toggle("below", point.y < 118);
      this.popover.style.top = `${point.y < 118 ? point.y + 18 : point.y - 16}px`;
    }
  }

  document.querySelectorAll("[data-campaign-chart]").forEach((shell) => {
    new CampaignChartController(shell);
  });
})();
