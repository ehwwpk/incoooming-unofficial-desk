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
    constructor({ stage, canvas, chart, priceSeries, resolveTime, timeForDate, onSelect, onIsolate, onHover, onLeave }) {
      this.stage = stage;
      this.surface = canvas;
      this.chart = chart;
      this.priceSeries = priceSeries;
      this.resolveTime = resolveTime || ((value) => ({
        time: timeForDate ? timeForDate(value) : value,
        exact: true,
        dateAnchored: false,
        edge: null,
      }));
      this.onSelect = onSelect;
      this.onIsolate = onIsolate;
      this.onHover = onHover;
      this.onLeave = onLeave;
      this.selection = { campaigns: [], level: "medium" };
      this.selected = null;
      this.hovered = null;
      this.shares = [];
      this.hits = [];
      this.frame = 0;
      this.trackingFrame = 0;
      this.clickTimer = 0;
      this.pointerStart = null;
      this.suppressClick = false;
      this.bind();
    }

    bind() {
      this.stage.addEventListener("pointerdown", (event) => {
        this.pointerStart = { x: event.clientX, y: event.clientY };
        this.suppressClick = false;
        this.trackTransform();
      });
      this.stage.addEventListener("pointerup", (event) => {
        if (!this.pointerStart) return;
        const moved = Math.hypot(event.clientX - this.pointerStart.x, event.clientY - this.pointerStart.y);
        this.pointerStart = null;
        this.suppressClick = moved > 5;
        this.stopTracking();
        this.redrawBurst();
      });
      this.stage.addEventListener("pointercancel", () => {
        this.pointerStart = null;
        this.suppressClick = true;
        this.stopTracking();
        this.redrawBurst();
      });
      this.stage.addEventListener("click", (event) => {
        if (this.suppressClick) {
          this.suppressClick = false;
          return;
        }
        const hit = this.hit(event);
        if (hit?.kind !== "campaign") return;
        clearTimeout(this.clickTimer);
        this.clickTimer = window.setTimeout(() => {
          this.onSelect?.(hit.campaign, hit.leg);
          this.clickTimer = 0;
        }, 220);
      });
      this.stage.addEventListener("dblclick", (event) => {
        const hit = this.hit(event);
        if (hit?.kind !== "campaign") return;
        clearTimeout(this.clickTimer);
        this.clickTimer = 0;
        this.onIsolate?.(hit.campaign, hit.leg);
      });
      this.stage.addEventListener("pointermove", (event) => {
        const hit = this.hit(event);
        const hovered = hit?.kind === "campaign" ? hit.campaign.id : null;
        if (hovered !== this.hovered) {
          this.hovered = hovered;
          this.schedule();
        }
        this.stage.classList.toggle("has-lifecycle-hit", Boolean(hit));
        if (hit) this.onHover?.(hit, this.localPoint(event));
        else this.onLeave?.();
      });
      this.stage.addEventListener("pointerleave", () => {
        if (this.hovered) {
          this.hovered = null;
          this.schedule();
        }
        this.stage.classList.remove("has-lifecycle-hit");
        this.onLeave?.();
      });
      this.stage.addEventListener("wheel", () => this.redrawBurst(), { passive: true });
    }

    setState({ selection, selected, shares }) {
      this.selection = selection;
      this.selected = selected;
      this.shares = shares || [];
      this.schedule();
    }

    setHover(campaignId) {
      if (this.hovered === campaignId) return;
      this.hovered = campaignId;
      this.schedule();
    }

    schedule() {
      cancelAnimationFrame(this.frame);
      this.frame = requestAnimationFrame(() => this.render());
    }

    trackTransform() {
      cancelAnimationFrame(this.trackingFrame);
      const tick = () => {
        if (!this.pointerStart) return;
        this.render();
        this.trackingFrame = requestAnimationFrame(tick);
      };
      this.trackingFrame = requestAnimationFrame(tick);
    }

    stopTracking() {
      cancelAnimationFrame(this.trackingFrame);
      this.trackingFrame = 0;
    }

    redrawBurst(frames = 4) {
      let remaining = frames;
      const tick = () => {
        this.render();
        remaining -= 1;
        if (remaining > 0) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
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
      const resolved = this.resolveTime(leg);
      let rawX = resolved.time === null ? null : this.chart.timeScale().timeToCoordinate(resolved.time);
      const rawY = this.priceSeries.priceToCoordinate(number(leg.underlying_price ?? leg.price));
      if (!Number.isFinite(rawY)) return null;
      let edge = resolved.edge;
      if (Number.isFinite(rawX)) {
        if (rawX < 10) edge = "before";
        else if (rawX > width - 10) edge = "after";
      } else if (edge === "before") rawX = 10;
      else if (edge === "after") rawX = width - 10;
      else return null;
      return {
        rawX,
        rawY,
        x: edge === "before" ? 10 : (edge === "after" ? width - 10 : rawX),
        y: Math.min(Math.max(rawY, 14), height - 14),
        edge,
        exact: Boolean(resolved.exact),
        dateAnchored: Boolean(resolved.dateAnchored),
        executionExact: Boolean(resolved.executionExact),
        intervalAnchored: Boolean(resolved.intervalAnchored),
        executionTime: resolved.executionTime ?? null,
      };
    }

    visiblePath(points) {
      const visible = points.filter((item) => !item.point.edge);
      if (!visible.length) return [];
      const firstVisible = points.findIndex((item) => !item.point.edge);
      let lastVisible = points.length - 1;
      while (lastVisible >= 0 && points[lastVisible].point.edge) lastVisible -= 1;
      const result = points.slice(firstVisible, lastVisible + 1);
      const before = points.slice(0, firstVisible).filter((item) => item.point.edge === "before").at(-1);
      const after = points.slice(lastVisible + 1).find((item) => item.point.edge === "after");
      if (before) result.unshift(before);
      if (after) result.push(after);
      return result;
    }

    render() {
      const { fragment, width, height } = this.setupSurface();
      this.hits = [];
      const paths = this.selection.campaigns.map((item, ordinal) => ({
        ...item,
        ordinal,
        points: this.visiblePath(item.path
          .map((leg) => ({ leg, point: this.point(leg, width, height) }))
          .filter((row) => row.point)),
      })).filter((item) => item.points.length);

      paths.forEach((item) => this.drawPath(fragment, item));
      const nodes = [];
      paths.forEach((item) => item.nodes.forEach((leg) => {
        const point = this.point(leg, width, height);
        if (point && !point.edge && point.exact) nodes.push({ ...item, leg, ...point, displayX: point.x, displayY: point.y });
      }));
      layout.cluster(nodes).forEach((group) => {
        group.items.forEach((item) => this.drawNode(fragment, item));
      });
      this.shares.forEach((item) => this.drawShare(fragment, item, width, height));
      this.surface.append(fragment);
      this.surface.dataset.pathCount = String(paths.length);
      this.surface.dataset.nodeCount = String(this.hits.filter((item) => item.kind === "campaign").length);
      this.surface.dataset.edgePathCount = String(paths.filter((item) => item.points.some(({ point }) => point.edge)).length);
    }

    drawPath(fragment, item) {
      if (item.points.length < 2) return;
      const active = item.campaign.id === (this.selected || this.hovered);
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
        "stroke-width": active ? 2.55 : 1.55,
        "stroke-dasharray": active ? "none" : "5 4",
        "stroke-linecap": "round",
        "vector-effect": "non-scaling-stroke",
        opacity: active ? .98 : ((this.selected || this.hovered) ? .045 : .72),
      }));
      if (item.points[0].point.edge === "before") this.drawHistoryEntry(fragment, item, active);
      if (active) this.drawDirection(fragment, item);
    }

    drawHistoryEntry(fragment, item, active) {
      const point = item.points[0].point;
      const identity = COLORS[item.ordinal % COLORS.length];
      fragment.append(element("path", {
        d: `M 10 ${(point.y - 7).toFixed(1)} L 10 ${(point.y + 7).toFixed(1)} M 10 ${point.y.toFixed(1)} L 16 ${point.y.toFixed(1)}`,
        fill: "none",
        stroke: identity,
        "stroke-width": active ? 2 : 1.25,
        "vector-effect": "non-scaling-stroke",
        opacity: active ? .92 : ((this.selected || this.hovered) ? .045 : .52),
      }));
    }

    drawDirection(fragment, item) {
      const points = item.points.map((row) => row.point);
      const end = points.at(-1);
      const start = points.slice(0, -1).reverse().find((point) => Math.hypot(end.x - point.x, end.y - point.y) > 8);
      if (!start || end.edge) return;
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.hypot(dx, dy);
      const ux = dx / length;
      const uy = dy / length;
      const cx = start.x + dx * .72;
      const cy = start.y + dy * .72;
      const size = 5;
      const tipX = cx + ux * size;
      const tipY = cy + uy * size;
      const baseX = cx - ux * size;
      const baseY = cy - uy * size;
      fragment.append(element("polygon", {
        points: `${tipX.toFixed(1)},${tipY.toFixed(1)} ${(baseX - uy * size * .72).toFixed(1)},${(baseY + ux * size * .72).toFixed(1)} ${(baseX + uy * size * .72).toFixed(1)},${(baseY - ux * size * .72).toFixed(1)}`,
        fill: COLORS[item.ordinal % COLORS.length],
        opacity: .95,
      }));
    }

    drawNode(fragment, item) {
      const x = item.displayX ?? item.x;
      const y = item.displayY ?? item.y;
      const moved = Math.abs(x - item.x) > 1 || Math.abs(y - item.y) > 1;
      const active = item.campaign.id === (this.selected || this.hovered);
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
          opacity: active ? .58 : ((this.selected || this.hovered) ? .04 : .48),
          "vector-effect": "non-scaling-stroke",
        }));
      }

      const group = element("g", {
        transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})`,
        opacity: active ? 1 : ((this.selected || this.hovered) ? .075 : .96),
      });
      const shape = item.campaign.option_side === "put"
        ? element("polygon", {
          points: `0,-${size} ${size},0 0,${size} -${size},0`,
          fill: semantic.fill,
          stroke: identity,
          "stroke-width": active ? 2.4 : 1.5,
        })
        : element("rect", {
          x: -size,
          y: -size,
          width: size * 2,
          height: size * 2,
          fill: semantic.fill,
          stroke: identity,
          "stroke-width": active ? 2.4 : 1.5,
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
        dateAnchored: item.dateAnchored,
        executionExact: item.executionExact,
        intervalAnchored: item.intervalAnchored,
        executionTime: item.executionTime,
      });
    }

    drawShare(fragment, item, width, height) {
      const point = this.point(item, width, height);
      if (!point || point.edge || !point.exact) return;
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
