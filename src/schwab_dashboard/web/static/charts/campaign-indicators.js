(() => {
  "use strict";

  const charts = window.LightweightCharts;
  if (!charts) return;

  const chartTime = (value) => {
    const text = String(value || "");
    return text.includes("T") ? Math.floor(Date.parse(text) / 1000) : text;
  };
  const close = (bar) => Number(bar.close ?? bar.value ?? 0);

  function ema(values, period) {
    const multiplier = 2 / (period + 1);
    const output = [];
    let current = values[0] ?? 0;
    values.forEach((value, index) => {
      current = index ? value * multiplier + current * (1 - multiplier) : value;
      output.push(current);
    });
    return output;
  }

  function rsi(bars, period = 14) {
    if (bars.length <= period) return [];
    let gain = 0;
    let loss = 0;
    for (let index = 1; index <= period; index += 1) {
      const change = close(bars[index]) - close(bars[index - 1]);
      gain += Math.max(change, 0);
      loss += Math.max(-change, 0);
    }
    gain /= period;
    loss /= period;
    const points = [];
    for (let index = period; index < bars.length; index += 1) {
      if (index > period) {
        const change = close(bars[index]) - close(bars[index - 1]);
        gain = (gain * (period - 1) + Math.max(change, 0)) / period;
        loss = (loss * (period - 1) + Math.max(-change, 0)) / period;
      }
      const value = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
      points.push({ time: chartTime(bars[index].time), value });
    }
    return points;
  }

  function macd(bars) {
    if (bars.length < 26) return { macd: [], signal: [], histogram: [] };
    const values = bars.map(close);
    const fast = ema(values, 12);
    const slow = ema(values, 26);
    const macdValues = values.map((_, index) => fast[index] - slow[index]);
    const signalValues = ema(macdValues, 9);
    const start = 25;
    return {
      macd: bars.slice(start).map((bar, index) => ({
        time: chartTime(bar.time),
        value: macdValues[start + index],
      })),
      signal: bars.slice(start).map((bar, index) => ({
        time: chartTime(bar.time),
        value: signalValues[start + index],
      })),
      histogram: bars.slice(start).map((bar, index) => {
        const value = macdValues[start + index] - signalValues[start + index];
        return {
          time: chartTime(bar.time),
          value,
          color: value >= 0 ? "rgba(114, 207, 145, .62)" : "rgba(223, 112, 105, .62)",
        };
      }),
    };
  }

  class CampaignIndicators {
    constructor(market, stage) {
      this.market = market;
      this.stage = stage;
      this.enabled = new Set();
      this.series = [];
    }

    toggle(name) {
      if (this.enabled.has(name)) this.enabled.delete(name);
      else this.enabled.add(name);
      this.refresh();
      return this.enabled.has(name);
    }

    refresh() {
      this.series.forEach((series) => {
        try { this.market.chart.removeSeries(series); } catch (_) { /* already removed */ }
      });
      this.series = [];
      let paneIndex = 1;
      if (this.enabled.has("rsi")) this.addRsi(paneIndex++);
      if (this.enabled.has("macd")) this.addMacd(paneIndex++);
      this.stage.dataset.indicatorCount = String(this.enabled.size);
      requestAnimationFrame(() => {
        const panes = this.market.chart.panes?.() || [];
        panes.slice(1).forEach((pane) => pane.setHeight?.(104));
      });
    }

    addRsi(paneIndex) {
      const series = this.market.chart.addSeries(charts.LineSeries, {
        title: "RSI 14",
        color: "#d7bd68",
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: true,
        priceFormat: { type: "custom", formatter: (value) => value.toFixed(1) },
      }, paneIndex);
      series.setData(rsi(this.market.bars()));
      [30, 70].forEach((price) => series.createPriceLine({
        price,
        color: "rgba(137, 143, 147, .38)",
        lineWidth: 1,
        lineStyle: charts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: price === 70 ? "OVERBOUGHT" : "OVERSOLD",
      }));
      this.series.push(series);
    }

    addMacd(paneIndex) {
      const data = macd(this.market.bars());
      const histogram = this.market.chart.addSeries(charts.HistogramSeries, {
        title: "MACD HIST",
        priceLineVisible: false,
        lastValueVisible: false,
        base: 0,
      }, paneIndex);
      const macdLine = this.market.chart.addSeries(charts.LineSeries, {
        title: "MACD",
        color: "#d8dad7",
        lineWidth: 1.5,
        priceLineVisible: false,
      }, paneIndex);
      const signal = this.market.chart.addSeries(charts.LineSeries, {
        title: "SIGNAL",
        color: "#d7bd68",
        lineWidth: 1.25,
        priceLineVisible: false,
      }, paneIndex);
      histogram.setData(data.histogram);
      macdLine.setData(data.macd);
      signal.setData(data.signal);
      this.series.push(histogram, macdLine, signal);
    }
  }

  window.IncooomingCampaignIndicators = CampaignIndicators;
})();
