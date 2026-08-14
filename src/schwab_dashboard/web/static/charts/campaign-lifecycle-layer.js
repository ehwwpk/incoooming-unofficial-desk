(() => {
  "use strict";

  const layout = window.IncooomingCampaignLayout;
  if (!layout) return;

  const NS = "http://www.w3.org/2000/svg";
  const COLORS = ["#e1bd58", "#8fbf9e", "#c98b63", "#d2d0c8", "#9ba66c", "#d47770"];
  const STATUS = {
    OPEN: { fill: "#282313", text: "#f0cf72" },
    EXPIRED: { fill: "#101c14", text: "#86d79f" },
    CLOSED: { fill: "#151819", text: "#bec2c4" },
    ROLLED: { fill: "#221d10", text: "#e1bd58" },
    ASSIGNED: { fill: "#241313", text: "#ec8179" },
  };
  const number = (value) => Number(value || 0);

  function element(name, attributes = {}) {
    const node = document.createElementNS(NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  class CampaignLifecycleLayer {
    constructor({ stage, canvas, chart, priceSeries, timeForDate, onSelect, onHover, onLeave }) {
      this.stage = stage;
      this.surface = canvas;
      this.chart = chart;
      this.priceSeries = priceSeries;
      this.timeForDate = timeForDate || ((value) => value);
      this.onSelect = onSelect;
      this.onHover = onHover;
      this.onLeave = onLeave;
      this.selection = { campaigns: [], level: "medium" };
      this.selected = null;
      this.shares = [];
      this.hits = [];
      this.frame = 0;
      this.pointerStart = null;
      this.bind();
    }

    bind() {
      this.stage.addEventListener("pointerdown", (event) => {
        this.pointerStart = { x: event.clientX, y: event.clientY };
      });
      this.stage.addEventListener("pointerup", (event) => {
        if (!this.pointerStart) return;
        const moved = Math.hypot(event.clientX - this.pointerStart.x, event.clientY - this.pointerStart.y);
        this.pointerStart = null;
        if (moved > 5) return;
        const hit = this.hit(event);
        if (hit?.kind === "campaign") this.onSelect?.(hit.campaign, hit.leg);
      });
      this.stage.addEventListener("pointermove", (event) => {
        const hit = this.hit(event);
        this.stage.classList.toggle("has-lifecycle-hit", Boolean(hit));
        if (hit) this.onHover?.(hit, this.localPoint(event));
        else this.onLeave?.();
      });
      this.stage.addEventListener("pointerleave", () => {
        this.stage.classList.remove("has-lifecycle-hit");
        this.onLeave?.();
      });
    }

    setState({ selection, selected, shares }) {
      this.selection = selection;
      this.selected = selected;
      this.shares = shares || [];
      this.schedule();
    }

    schedule() {
      cancelAnimationFrame(this.frame);
      this.frame = requestAnimationFrame(() => this.render());
    }

    localPoint(event) {
      const bounds = this.stage.getBoundingClientRect();
      return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
    }

    hit(event) {
      const point = this.localPoint(event);
      return this.hits
        .slice()
        .reverse()
        .find((item) => Math.hypot(point.x - item.x, point.y - item.y) <= item.radius);
    }

    setupSurface() {
      const width = Math.max(1, this.stage.clientWidth);
      const height = Math.max(1, this.stage.clientHeight);
      this.surface.setAttribute("viewBox", `0 0 ${width} ${height}`);
      this.surface.setAttribute("preserveAspectRatio", "none");
      this.surface.replaceChildren();
      return { fragment: document.createDocumentFragment(), width, height };
    }

    point(leg, width, height) {
      const rawX = this.chart.timeScale().timeToCoordinate(this.timeForDate(leg.time));
      const rawY = this.priceSeries.priceToCoordinate(number(leg.underlying_price ?? leg.price));
      if (!Number.isFinite(rawX) || !Number.isFinite(rawY)) return null;
      return {
        rawX,
        rawY,
        x: Math.min(Math.max(rawX, 10), width - 10),
        y: Math.min(Math.max(rawY, 14), height - 14),
      };
    }

    render() {
      const { fragment, width, height } = this.setupSurface();
      this.hits = [];
      const paths = this.selection.campaigns.map((item, ordinal) => ({
        ...item,
        ordinal,
        points: item.path
          .map((leg) => ({ leg, point: this.point(leg, width, height) }))
          .filter((row) => row.point),
      })).filter((item) => item.points.length);

      paths.forEach((item) => this.drawPath(fragment, item));
      const nodes = [];
      paths.forEach((item) => item.nodes.forEach((leg) => {
        const point = this.point(leg, width, height);
        if (point) nodes.push({ ...item, leg, ...point, displayX: point.x, displayY: point.y });
      }));
      layout.cluster(nodes).forEach((group) => {
        group.items.forEach((item) => this.drawNode(fragment, item));
      });
      this.shares.forEach((item) => this.drawShare(fragment, item, width, height));
      this.surface.append(fragment);
      this.surface.dataset.pathCount = String(paths.length);
      this.surface.dataset.nodeCount = String(this.hits.filter((item) => item.kind === "campaign").length);
    }

    drawPath(fragment, item) {
      if (item.points.length < 2) return;
      const selected = item.campaign.id === this.selected;
      let data = "";
      item.points.forEach(({ point }, index) => {
        if (!index) {
          data = `M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
          return;
        }
        const previous = item.points[index - 1].point;
        const controlX = previous.x + (point.x - previous.x) * .52;
        data += ` C ${controlX.toFixed(1)} ${previous.y.toFixed(1)}, ${controlX.toFixed(1)} ${point.y.toFixed(1)}, ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
      });
      fragment.append(element("path", {
        d: data,
        fill: "none",
        stroke: COLORS[item.ordinal % COLORS.length],
        "stroke-width": selected ? 2.4 : 1.65,
        "stroke-dasharray": selected ? "none" : "4 4",
        "stroke-linecap": "round",
        "vector-effect": "non-scaling-stroke",
        opacity: selected ? .98 : (this.selected ? .22 : .82),
      }));
    }

    drawNode(fragment, item) {
      const x = item.displayX ?? item.x;
      const y = item.displayY ?? item.y;
      const moved = Math.abs(x - item.x) > 1 || Math.abs(y - item.y) > 1;
      const selected = item.campaign.id === this.selected;
      const status = String(item.leg.outcome || item.campaign.status || "OPEN").toUpperCase();
      const identity = COLORS[item.ordinal % COLORS.length];
      const semantic = STATUS[status] || STATUS.OPEN;
      const size = this.selection.level === "close" ? 14 : 13;
      if (moved) {
        fragment.append(element("line", {
          x1: item.x,
          y1: item.y,
          x2: x,
          y2: y,
          stroke: identity,
          "stroke-width": 1,
          opacity: .54,
          "vector-effect": "non-scaling-stroke",
        }));
      }

      const group = element("g", {
        transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`,
        opacity: selected ? 1 : (this.selected ? .48 : .98),
      });
      const shape = item.campaign.option_side === "put"
        ? element("polygon", {
          points: `0,-${size} ${size},0 0,${size} -${size},0`,
          fill: semantic.fill,
          stroke: identity,
          "stroke-width": selected ? 2.4 : 1.5,
        })
        : element("rect", {
          x: -size,
          y: -size,
          width: size * 2,
          height: size * 2,
          fill: semantic.fill,
          stroke: identity,
          "stroke-width": selected ? 2.4 : 1.5,
        });
      group.append(shape);
      if (status === "ROLLED") {
        const inset = item.campaign.option_side === "put"
          ? element("polygon", {
            points: `0,-${size * .72} ${size * .72},0 0,${size * .72} -${size * .72},0`,
            fill: "none",
            stroke: semantic.text,
            "stroke-width": 1,
          })
          : element("rect", {
            x: -size * .72,
            y: -size * .72,
            width: size * 1.44,
            height: size * 1.44,
            fill: "none",
            stroke: semantic.text,
            "stroke-width": 1,
          });
        group.append(inset);
      }
      const text = element("text", {
        x: 0,
        y: 3.2,
        fill: semantic.text,
        "text-anchor": "middle",
        "font-family": '"IBM Plex Mono", Consolas, monospace',
        "font-size": 9,
        "font-weight": 800,
      });
      text.textContent = item.campaign.code;
      group.append(text);
      fragment.append(group);

      this.hits.push({
        kind: "campaign",
        x,
        y,
        radius: size + 6,
        campaign: item.campaign,
        leg: item.leg,
      });
    }

    drawShare(fragment, item, width, height) {
      const point = this.point(item, width, height);
      if (!point) return;
      const sold = String(item.action || "").toLowerCase() === "sold";
      const group = element("g", { transform: `translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})` });
      group.append(element("circle", {
        cx: 0,
        cy: 0,
        r: 7,
        fill: sold ? "#211414" : "#101a14",
        stroke: sold ? "#c56f69" : "#72cf91",
        "stroke-width": 1.25,
      }));
      const text = element("text", {
        x: 0,
        y: 3.2,
        fill: sold ? "#df8078" : "#8fd6a6",
        "text-anchor": "middle",
        "font-family": '"IBM Plex Mono", Consolas, monospace',
        "font-size": 9,
        "font-weight": 800,
      });
      text.textContent = sold ? "−" : "+";
      group.append(text);
      fragment.append(group);
      this.hits.push({ kind: "share", x: point.x, y: point.y, radius: 11, item });
    }
  }

  window.IncooomingCampaignLifecycleLayer = CampaignLifecycleLayer;
})();
