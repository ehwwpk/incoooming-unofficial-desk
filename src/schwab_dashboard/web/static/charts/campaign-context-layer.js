(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const number = (value) => Number(value || 0);
  const money = (value) => {
    const amount = number(value);
    return amount.toFixed(Number.isInteger(amount) ? 0 : 2);
  };
  const monthDay = (value) => {
    const day = String(value || "").slice(0, 10);
    if (!day) return "DATE UNKNOWN";
    const date = new Date(`${day}T12:00:00Z`);
    if (Number.isNaN(date.getTime())) return day;
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).toUpperCase();
  };
  const svg = (name, attrs = {}) => {
    const node = document.createElementNS(NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };

  class CampaignContextLayer {
    constructor({ stage, canvas, market }) {
      this.stage = stage;
      this.canvas = canvas;
      this.market = market;
      this.selection = null;
      this.selected = null;
      this.focused = false;
    }

    setState({ selection, selected, focused }) {
      this.selection = selection;
      this.selected = selected;
      this.focused = focused;
      this.render();
    }

    render() {
      const width = Math.max(1, this.stage.clientWidth);
      const height = Math.max(1, this.stage.clientHeight);
      this.canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
      this.canvas.replaceChildren();
      const fragment = document.createDocumentFragment();
      const campaigns = this.selection?.campaigns || [];
      const open = campaigns.filter(({ campaign }) => campaign.status === "OPEN");
      const chosen = campaigns.find(({ campaign }) => campaign.id === this.selected);

      open
        .filter(({ campaign }) => campaign.id !== this.selected)
        .forEach((item, index) => this.drawTail(fragment, item, width, height, index));
      if (chosen?.campaign?.status === "OPEN") {
        this.drawObligationVector(fragment, chosen, width, height);
      }
      if (this.focused && chosen?.campaign?.status === "OPEN") {
        this.drawCorridor(fragment, chosen.campaign, width, height);
      }
      this.canvas.append(fragment);
    }

    drawTail(fragment, item, width, height, index) {
      const last = this.openLeg(item.campaign);
      if (!last) return;
      const startX = this.market.xForEvent(last);
      const startY = this.market.activeSeries().priceToCoordinate(number(last.underlying_price));
      const nowX = this.market.xForEvent({ time: this.market.coverage().to, time_precision: "date_only" });
      if (![startX, startY, nowX].every(Number.isFinite)) return;
      const lane = height - 27 - (index % 3) * 7;
      fragment.append(svg("path", {
        d: `M ${startX.toFixed(1)} ${startY.toFixed(1)} L ${startX.toFixed(1)} ${lane} L ${Math.min(width - 72, nowX).toFixed(1)} ${lane}`,
        fill: "none",
        stroke: "#8d947c",
        "stroke-width": 1,
        "stroke-dasharray": "3 4",
        opacity: .18,
        "vector-effect": "non-scaling-stroke",
      }));
    }

    drawObligationVector(fragment, item, width, height) {
      const campaign = item.campaign;
      const leg = this.openLeg(campaign);
      if (!leg) return;
      const series = this.market.activeSeries();
      const sourcePrice = number(leg.underlying_price || campaign.risk_reference?.spot);
      const sourceY = series.priceToCoordinate(sourcePrice);
      const target = this.referenceY(series, number(leg.strike), height);
      const rawSourceX = this.market.xForEvent(leg);
      if (![rawSourceX, sourceY].every(Number.isFinite) || !target) return;

      const targetX = Math.max(66, width - 82);
      const sourceX = Math.min(Math.max(8, rawSourceX), targetX - 34);
      const targetY = target.y;
      const distance = Math.max(34, targetX - sourceX);
      const firstControlX = sourceX + Math.max(16, distance * .38);
      const secondControlX = targetX - Math.max(13, Math.min(38, distance * .24));
      const color = "#ddb657";
      const side = String(leg.option_side || campaign.option_side || "call").toLowerCase();
      const contract = `$${money(leg.strike)}${side === "put" ? "P" : "C"}`;
      const boundary = side === "put" ? "ITM BELOW" : "ITM ABOVE";

      fragment.append(svg("circle", {
        cx: sourceX,
        cy: sourceY,
        r: 3,
        fill: "#0f1112",
        stroke: color,
        "stroke-width": 1.25,
        opacity: .88,
        "data-obligation-anchor": campaign.id,
      }));
      fragment.append(svg("path", {
        d: `M ${sourceX.toFixed(1)} ${sourceY.toFixed(1)} C ${firstControlX.toFixed(1)} ${sourceY.toFixed(1)}, ${secondControlX.toFixed(1)} ${targetY.toFixed(1)}, ${targetX.toFixed(1)} ${targetY.toFixed(1)}`,
        fill: "none",
        stroke: color,
        "stroke-width": 1.35,
        "stroke-dasharray": "2 5",
        "stroke-linecap": "round",
        opacity: .9,
        "vector-effect": "non-scaling-stroke",
        "data-obligation-vector": campaign.id,
      }));
      fragment.append(svg("line", {
        x1: targetX - 22,
        x2: targetX,
        y1: targetY,
        y2: targetY,
        stroke: color,
        "stroke-width": 1.5,
        opacity: .92,
        "vector-effect": "non-scaling-stroke",
      }));
      fragment.append(svg("path", {
        d: `M ${targetX - 7} ${targetY - 4} L ${targetX} ${targetY} L ${targetX - 7} ${targetY + 4}`,
        fill: "none",
        stroke: color,
        "stroke-width": 1.5,
        "stroke-linecap": "square",
        "stroke-linejoin": "miter",
        opacity: .96,
        "vector-effect": "non-scaling-stroke",
        "data-obligation-target": campaign.id,
      }));

      const labelY = targetY < 32 ? targetY + 18 : targetY - 11;
      const label = svg("text", {
        x: targetX - 3,
        y: labelY,
        fill: color,
        "text-anchor": "end",
        "font-family": '"IBM Plex Mono", Consolas, monospace',
        "font-size": 8.5,
        "font-weight": 800,
        "letter-spacing": ".02em",
        "data-obligation-label": campaign.id,
      });
      label.textContent = `EXP ${monthDay(leg.expiration)} \u00b7 ${contract}${target.suffix}`;
      fragment.append(label);

      const meaning = svg("text", {
        x: targetX - 3,
        y: labelY + 11,
        fill: "#a39a7c",
        "text-anchor": "end",
        "font-family": '"IBM Plex Mono", Consolas, monospace',
        "font-size": 6.75,
        "font-weight": 700,
        "letter-spacing": ".04em",
        "data-obligation-boundary": campaign.id,
      });
      meaning.textContent = `${boundary} $${money(leg.strike)} AT EXPIRY`;
      fragment.append(meaning);
    }

    openLeg(campaign) {
      const ordered = campaign.legs.slice().sort((a, b) =>
        String(a.time).localeCompare(String(b.time)) ||
        number(a.sequence) - number(b.sequence) ||
        number(a.leg_index) - number(b.leg_index),
      );
      return ordered.filter((leg) => Boolean(leg.is_open)).at(-1) || ordered.at(-1) || null;
    }

    drawCorridor(fragment, campaign, width, height) {
      const ref = campaign.risk_reference;
      if (!ref) return;
      const series = this.market.activeSeries();
      const strike = this.referenceY(series, number(ref.strike), height);
      const spot = this.referenceY(series, number(ref.spot), height);
      if (!strike || !spot) return;
      const strikeY = strike.y;
      const spotY = spot.y;
      const right = width - 70;
      const startX = Math.max(0, this.market.xForEvent(campaign.legs[0]) || 0);
      const itmTop = campaign.option_side === "put" ? strikeY : 0;
      const itmHeight = campaign.option_side === "put" ? height - strikeY : strikeY;
      fragment.append(svg("rect", {
        x: startX,
        y: itmTop,
        width: Math.max(0, right - startX),
        height: Math.max(0, itmHeight),
        fill: "rgba(198, 97, 91, .045)",
      }));
      if (ref.expected_move_low !== null && ref.expected_move_high !== null) {
        const high = this.referenceY(series, number(ref.expected_move_high), height);
        const low = this.referenceY(series, number(ref.expected_move_low), height);
        if (high && low) {
          fragment.append(svg("rect", {
            x: startX,
            y: Math.min(high.y, low.y),
            width: Math.max(0, right - startX),
            height: Math.abs(low.y - high.y),
            fill: "rgba(225, 189, 88, .045)",
            stroke: "rgba(225, 189, 88, .18)",
            "stroke-dasharray": "2 5",
          }));
        }
      }
      this.line(fragment, startX, right, strikeY, `STRIKE $${number(ref.strike).toFixed(2)}${strike.suffix}`, "#d97770");
      this.line(fragment, startX, right, spotY, `SPOT $${number(ref.spot).toFixed(2)}${spot.suffix}`, "#8fd1a4");
      const note = svg("text", {
        x: startX + 7,
        y: height - 9,
        fill: "#8c9295",
        "font-family": '"IBM Plex Mono", Consolas, monospace',
        "font-size": 7,
        "font-weight": 700,
      });
      note.textContent = ref.expected_move !== null
        ? `${ref.source} \u00b7 \u00b1$${number(ref.expected_move).toFixed(2)} TO EXP \u00b7 NOT A FORECAST`
        : "STRIKE / SPOT REFERENCE \u00b7 NO VERIFIED IV BAND";
      fragment.append(note);
    }

    referenceY(series, value, height) {
      const raw = series.priceToCoordinate(value);
      if (!Number.isFinite(raw)) return null;
      const upper = 14;
      const lower = Math.max(upper, height - 34);
      if (raw < upper) return { y: upper, suffix: " \u00b7 ABOVE VIEW" };
      if (raw > lower) return { y: lower, suffix: " \u00b7 BELOW VIEW" };
      return { y: raw, suffix: "" };
    }

    line(fragment, left, right, y, label, color) {
      fragment.append(svg("line", {
        x1: left,
        x2: right,
        y1: y,
        y2: y,
        stroke: color,
        "stroke-width": 1,
        "stroke-dasharray": "5 5",
        opacity: .58,
      }));
      const text = svg("text", {
        x: right - 4,
        y: y - 4,
        fill: color,
        "text-anchor": "end",
        "font-family": '"IBM Plex Mono", Consolas, monospace',
        "font-size": 8,
        "font-weight": 800,
      });
      text.textContent = label;
      fragment.append(text);
    }
  }

  window.IncooomingCampaignContextLayer = CampaignContextLayer;
})();
