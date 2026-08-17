(() => {
  "use strict";

  const charts = window.LightweightCharts;
  if (!charts) return;

  const palette = {
    background: "#0d0f10",
    grid: "rgba(85, 90, 94, .19)",
    line: "#c9cbcb",
    muted: "#747a7f",
  };
  const number = (value) => Number(value || 0);
  const dayKey = (value) => {
    if (typeof value === "number") return new Date(value * 1000).toISOString().slice(0, 10);
    if (value && typeof value === "object" && "year" in value) {
      return `${value.year}-${String(value.month).padStart(2, "0")}-${String(value.day).padStart(2, "0")}`;
    }
    return String(value || "").slice(0, 10);
  };
  const chartTime = (value) => {
    const text = String(value || "");
    if (!text.includes("T")) return text;
    return Math.floor(Date.parse(text) / 1000);
  };
  const epochDay = (value) => Date.parse(`${dayKey(value)}T00:00:00Z`);
  const easternClock = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const easternMinute = (value) => {
    const instant = typeof value === "number" ? new Date(value * 1000) : new Date(value);
    const parts = Object.fromEntries(easternClock.formatToParts(instant).map((part) => [part.type, part.value]));
    return Number(parts.hour) * 60 + Number(parts.minute);
  };

  class CampaignMarketLayer {
    constructor(container, payload, readout) {
      this.container = container;
      this.payload = payload;
      this.readout = readout;
      this.style = "candles";
      this.interval = payload.default_interval || "1d";
      this.viewportListeners = new Set();
      this.intervals = new Map(
        (payload.intervals?.length
          ? payload.intervals
          : [{ key: "1d", label: "1D", minutes: 1440, bars: payload.bars, extended_hours: false }]
        ).map((item) => [item.key, item]),
      );
      if (!this.intervals.has(this.interval)) this.interval = "1d";
      this.create();
    }

    create() {
      this.chart = charts.createChart(this.container, {
        autoSize: true,
        layout: {
          background: { type: charts.ColorType.Solid, color: palette.background },
          textColor: palette.muted,
          fontFamily: '"IBM Plex Mono", Consolas, monospace',
          fontSize: 10,
          attributionLogo: true,
          panes: { separatorColor: "#34383b", separatorHoverColor: "#e1bd58" },
        },
        grid: {
          vertLines: { color: palette.grid },
          horzLines: { color: palette.grid },
        },
        rightPriceScale: {
          borderColor: "#303438",
          minimumWidth: 68,
          scaleMargins: { top: .10, bottom: .10 },
        },
        timeScale: {
          borderColor: "#303438",
          rightOffset: 4,
          barSpacing: 8,
          minBarSpacing: 2,
          timeVisible: false,
          secondsVisible: false,
          fixLeftEdge: false,
          fixRightEdge: false,
        },
        crosshair: {
          mode: charts.CrosshairMode.Normal,
          vertLine: { color: "rgba(225, 189, 88, .38)", labelBackgroundColor: "#332d1a" },
          horzLine: { color: "rgba(225, 189, 88, .26)", labelBackgroundColor: "#332d1a" },
        },
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: false,
        },
        handleScale: {
          mouseWheel: true,
          pinch: true,
          axisPressedMouseMove: { time: true, price: true },
          axisDoubleClickReset: { time: true, price: true },
        },
      });

      this.candles = this.chart.addSeries(charts.CandlestickSeries, {
        upColor: "#8fcea3",
        downColor: "#d56d67",
        borderUpColor: "#8fcea3",
        borderDownColor: "#d56d67",
        wickUpColor: "#779f84",
        wickDownColor: "#a55d59",
        priceLineVisible: false,
        lastValueVisible: true,
        priceFormat: { type: "custom", formatter: (price) => `$${price.toFixed(2)}` },
      });
      this.line = this.chart.addSeries(charts.LineSeries, {
        color: palette.line,
        lineWidth: 2,
        crosshairMarkerVisible: true,
        priceLineVisible: false,
        lastValueVisible: true,
        priceFormat: { type: "custom", formatter: (price) => `$${price.toFixed(2)}` },
        visible: false,
      });

      this.setInterval(this.interval);
      this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        const span = range ? Math.max(1, range.to - range.from) : this.bars().length;
        this.viewportListeners.forEach((listener) => listener(span));
      });
      this.chart.subscribeCrosshairMove((param) => this.updateReadout(param));
    }

    availableIntervals() {
      return [...this.intervals.keys()];
    }

    bars() {
      return this.intervals.get(this.interval)?.bars || this.payload.bars || [];
    }

    bestInterval(rangeKey) {
      const preferred = { "4w": "1h", "8w": "4h" }[rangeKey] || "1d";
      const candidate = this.intervals.get(preferred);
      if (!candidate?.bars?.length) return "1d";
      const days = { "4w": 28, "8w": 56 }[rangeKey];
      const end = epochDay(candidate.bars.at(-1).time);
      const requiredStart = end - days * 86_400_000;
      const actualStart = epochDay(candidate.bars[0].time);
      return actualStart <= requiredStart + 3 * 86_400_000 ? preferred : "1d";
    }

    setInterval(key) {
      this.interval = this.intervals.has(key) ? key : "1d";
      const bars = this.bars();
      const normalized = bars.map((bar) => ({
        time: chartTime(bar.time),
        open: number(bar.open ?? bar.value),
        high: number(bar.high ?? bar.value),
        low: number(bar.low ?? bar.value),
        close: number(bar.close ?? bar.value),
      }));
      this.candles.setData(normalized);
      this.line.setData(normalized.map((bar) => ({ time: bar.time, value: bar.close })));
      this.chart.applyOptions({
        timeScale: {
          timeVisible: this.interval !== "1d",
          secondsVisible: false,
        },
      });
      this.rebuildDateMap();
      return this.interval;
    }

    rebuildDateMap() {
      this.dateTimes = new Map();
      this.timesByDate = new Map();
      this.bars().forEach((bar) => {
        const key = dayKey(bar.time);
        const time = chartTime(bar.time);
        const rows = this.timesByDate.get(key) || [];
        rows.push(time);
        this.timesByDate.set(key, rows);
      });
      this.timesByDate.forEach((times, key) => {
        const regularSession = this.interval === "1d"
          ? times
          : times.filter((time) => {
            const minute = easternMinute(time);
            // A bar stamped 16:00 ET begins after-hours. Date-only records
            // belong on the final bar that ends at the regular-session close.
            return minute >= 570 && minute < 960;
          });
        this.dateTimes.set(key, (regularSession.length ? regularSession : times).at(-1));
      });
      this.coverageDates = [...this.dateTimes.keys()].sort();
    }

    timeForDate(value) {
      return this.resolveEventTime(value).time;
    }

    resolveEventTime(value) {
      const event = value && typeof value === "object" && "time" in value ? value : null;
      const raw = event?.time ?? value;
      const precision = event?.time_precision || "date_only";
      const key = dayKey(raw);
      if (precision === "exact" && String(raw).includes("T") && this.interval !== "1d") {
        const execution = chartTime(raw);
        const candidates = (this.timesByDate.get(key) || []).slice().sort((a, b) => a - b);
        if (candidates.length) {
          const containing = candidates.filter((time) => time <= execution).at(-1) ?? candidates[0];
          return {
            time: containing,
            exact: true,
            executionExact: true,
            executionTime: execution,
            intervalAnchored: containing !== execution,
            dateAnchored: false,
            edge: null,
          };
        }
      }
      const exact = this.dateTimes.get(key);
      if (exact !== undefined) {
        return {
          time: exact,
          exact: true,
          executionExact: precision === "exact",
          executionTime: precision === "exact" && String(raw).includes("T") ? chartTime(raw) : null,
          intervalAnchored: precision === "exact",
          dateAnchored: precision !== "exact" && this.interval !== "1d",
          edge: null,
        };
      }
      const first = this.coverageDates?.[0];
      const last = this.coverageDates?.at(-1);
      if (!first || !last) return { time: null, exact: false, dateAnchored: false, edge: null };
      if (key < first) return { time: this.dateTimes.get(first), exact: false, dateAnchored: false, edge: "before" };
      if (key > last) return { time: this.dateTimes.get(last), exact: false, dateAnchored: false, edge: "after" };
      const nearest = this.coverageDates.reduce((best, candidate) => (
        Math.abs(epochDay(candidate) - epochDay(key)) < Math.abs(epochDay(best) - epochDay(key))
          ? candidate
          : best
      ), first);
      return {
        time: this.dateTimes.get(nearest),
        exact: false,
        dateAnchored: false,
        edge: null,
      };
    }

    xForEvent(value) {
      const resolved = this.resolveEventTime(value);
      if (resolved.time === null) return null;
      return this.chart.timeScale().timeToCoordinate(resolved.time);
    }

    visibleDateRange() {
      const visible = this.chart.timeScale().getVisibleRange();
      if (!visible) return null;
      return { from: dayKey(visible.from), to: dayKey(visible.to) };
    }

    coverage() {
      return {
        from: this.coverageDates?.[0] || null,
        to: this.coverageDates?.at(-1) || null,
      };
    }

    activeSeries() {
      return this.style === "candles" ? this.candles : this.line;
    }

    setStyle(style) {
      this.style = style === "line" ? "line" : "candles";
      this.candles.applyOptions({ visible: this.style === "candles" });
      this.line.applyOptions({ visible: this.style === "line" });
    }

    setRange(from, to) {
      if (!from || !to) return;
      const intraday = this.interval !== "1d";
      const start = intraday ? Math.floor(Date.parse(`${dayKey(from)}T00:00:00Z`) / 1000) : dayKey(from);
      const last = this.bars().at(-1)?.time || to;
      const end = intraday ? chartTime(last) : dayKey(to);
      this.chart.timeScale().setVisibleRange({ from: start, to: end });
    }

    fit() {
      this.chart.timeScale().fitContent();
      this.chart.priceScale("right").applyOptions({ autoScale: true });
    }

    logicalSpan() {
      const range = this.chart.timeScale().getVisibleLogicalRange();
      return range ? Math.max(1, range.to - range.from) : this.bars().length;
    }

    onViewport(listener) {
      this.viewportListeners.add(listener);
    }

    updateReadout(param) {
      if (!this.readout) return;
      const bar = param?.seriesData?.get(this.activeSeries());
      if (!bar || !param.time) {
        this.readout.textContent = "DRAG TO PAN · WHEEL TO ZOOM · DRAG PRICE AXIS TO SCALE";
        return;
      }
      const open = number(bar.open ?? bar.value);
      const high = number(bar.high ?? bar.value);
      const low = number(bar.low ?? bar.value);
      const close = number(bar.close ?? bar.value);
      const stamp = typeof param.time === "number"
        ? new Date(param.time * 1000).toLocaleString([], { month: "short", day: "2-digit", hour: "numeric", minute: "2-digit" })
        : param.time;
      this.readout.textContent = `${stamp} · O ${open.toFixed(2)} · H ${high.toFixed(2)} · L ${low.toFixed(2)} · C ${close.toFixed(2)}`;
    }
  }

  window.IncooomingCampaignMarketLayer = CampaignMarketLayer;
})();
