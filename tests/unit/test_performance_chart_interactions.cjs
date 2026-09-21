const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.resolve(__dirname,
  "../../src/schwab_dashboard/web/static/performance-compare.js"), "utf8");

// Fictional returns deliberately include different Friday and Sunday endpoints.
const day = (date, value, extra = {}) => ({
  date, cumulative_return_percent: value, external_flow: 0,
  value_quality: "observed", return_quality: "observed", valuation_phase: "close", ...extra,
});
const first = "2026-09-16";
const friday = "2026-09-18";
const sunday = "2026-09-20";
const fixture = () => ({
  actual: { points: [day(first, 0), day(friday, -6), day(sunday, -6.25,
    { return_quality: "provisional", valuation_phase: "off_session" })] },
  shares_without_options: { points: [day(first, 0), day(friday, -8)] },
  market_reference: { points: [day(first, 0), day(friday, -2)] },
  levered_market_reference: { points: [day(first, 0), day(friday, -4)] },
});

function setup(payload = fixture()) {
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      hidden: selector === "[data-performance-inspector]", textContent: "", innerHTML: "",
      clientWidth: 1000, clientHeight: 600, offsetWidth: 280, offsetHeight: 180,
      style: {}, events: {}, classList: { toggle() {} },
      addEventListener(event, callback) { this.events[event] = callback; },
      setAttribute() {},
    });
    return nodes.get(selector);
  }
  const panel = { dataset: { performanceDemo: "false" }, querySelector: node };
  node("[data-performance-comparison-payload]").textContent = JSON.stringify(payload);
  const plotted = [];
  let move;
  let crosshair = null;
  let options;
  const chart = {
    addSeries(_type, settings) {
      const api = {
        settings, points: [], setData(points) { this.points = points; }, createPriceLine() {},
      };
      plotted.push(api);
      return api;
    },
    subscribeCrosshairMove(callback) { move = callback; },
    setCrosshairPosition(value, time, api) {
      assert.ok(api.points.some(p => p.time === time && p.value === value));
      crosshair = { time, value };
      // Exercise re-entrant delivery too, so restoring a pin cannot loop.
      move({ time, point: { x: 100, y: 100 } });
    },
    clearCrosshairPosition() { crosshair = null; },
    timeScale() { return { fitContent() {} }; },
  };
  vm.runInNewContext(source, {
    document: { querySelectorAll: () => [panel] },
    window: { LightweightCharts: {
      createChart(_canvas, value) { options = value; return chart; },
      ColorType: { Solid: 0 }, LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
      CrosshairMode: { Normal: 0 }, LineSeries: {},
    } },
    console: { error(message, error) { throw error || new Error(message); } },
  });
  return {
    node, plotted, options,
    get crosshair() { return crosshair; },
    hover(time, y = 70) {
      crosshair = { time, value: 4.22 }; // Free mouse height, not a return.
      move({ time, point: { x: 700, y } });
    },
    key(key) { node("[data-performance-compare-chart]").events.keydown({ key, preventDefault() {} }); },
    click() { node("[data-performance-compare-canvas]").events.click(); },
    blur() { node("[data-performance-compare-chart]").events.blur(); },
    get tooltip() { return node("[data-performance-inspector-series]").innerHTML; },
    get date() { return node("[data-performance-inspector-date]").textContent; },
  };
}

test("the free pointer height never appears as a return; tooltip equals plotted values", () => {
  const ui = setup();
  assert.equal(ui.options.crosshair.horzLine.visible, false);
  assert.equal(ui.options.crosshair.horzLine.labelVisible, false);
  ui.hover(friday);
  for (const [color, value] of [["#72cf91", -6], ["#e1bd58", -8], ["#9ca3a8", -2], ["#a98cd8", -4]]) {
    assert.ok(ui.plotted.some(s => s.settings.color === color &&
      s.points.some(p => p.time === friday && p.value === value)));
    assert.ok(ui.tooltip.includes(`>${value.toFixed(2)}%</strong>`));
  }
  assert.ok(!ui.tooltip.includes("4.22%"));
  const text = ui.tooltip;
  ui.hover(friday, 550);
  assert.equal(ui.tooltip, text);
});

test("click pin keeps date, markers and values together until unpinned", () => {
  const ui = setup();
  ui.hover(friday);
  ui.click();
  const text = ui.tooltip;
  const date = ui.date;
  ui.hover(first);
  assert.equal(ui.crosshair.time, friday);
  assert.equal(ui.crosshair.value, -6);
  assert.equal(ui.tooltip, text);
  assert.equal(ui.date, date);
  ui.click();
  ui.hover(first);
  assert.notEqual(ui.date, date);
  assert.ok(ui.tooltip.includes("+0.00%"));
});

test("keyboard selection and market-closed endpoint use actual date values", () => {
  const ui = setup();
  ui.key("End");
  assert.equal(ui.crosshair.time, sunday);
  assert.ok(ui.tooltip.includes("-6.25%"));
  assert.equal((ui.tooltip.match(/MARKET CLOSED/g) || []).length, 3);
  ui.hover(first);
  assert.equal(ui.crosshair.time, sunday);
  ui.key("ArrowLeft");
  assert.equal(ui.crosshair.time, friday);
  assert.ok(ui.tooltip.includes("-6.00%"));
  ui.key("Escape");
  assert.equal(ui.crosshair, null);
  assert.equal(ui.node("[data-performance-inspector]").hidden, true);
  ui.key("Home");
  ui.blur();
  assert.equal(ui.crosshair, null);
  assert.equal(ui.node("[data-performance-inspector]").hidden, true);
});

test("benchmark-only dates remain selectable without fabricating managed values", () => {
  const payload = fixture();
  const referenceDate = "2026-09-17";
  payload.market_reference.points.splice(1, 0, day(referenceDate, -1));
  const ui = setup(payload);
  ui.key("Home");
  ui.key("ArrowRight");
  assert.equal(ui.crosshair.time, referenceDate);
  assert.equal(ui.crosshair.value, -1);
  assert.ok(ui.tooltip.includes("UNRESOLVED / OUTSIDE COVERAGE"));
  assert.ok(ui.tooltip.includes("-1.00%"));
});
