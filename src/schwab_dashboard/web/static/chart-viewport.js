(() => {
  const DAY = 86_400_000;
  const RANGES = {
    full: { label: "FULL", days: null },
    "8w": { label: "8W", days: 56 },
    "4w": { label: "4W", days: 28 },
  };
  const money = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const shortDate = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  });

  const readDate = (value) => new Date(`${value}T00:00:00Z`);
  const timestamp = (element) => readDate(element.dataset.date).getTime();
  const number = (element, key) => Number.parseFloat(element.dataset[key]);
  const setCoordinate = (element, x, y = null) => {
    element.style.setProperty("--event-x", `${x.toFixed(2)}%`);
    if (y !== null) element.style.setProperty("--event-y", `${y.toFixed(2)}%`);
  };
  const show = (element, visible) => {
    element.hidden = !visible;
  };
  const percent = (value) => `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;

  const initializeChart = (workspace) => {
    const points = [...workspace.querySelectorAll("[data-chart-point]")].map((element) => ({
      element,
      date: timestamp(element),
      price: number(element, "price"),
    }));
    if (points.length < 2) return;

    const card = workspace.closest("[data-underlying-card]");
    const buttons = [...workspace.querySelectorAll("[data-chart-range]")];
    const line = workspace.querySelector("[data-chart-line]");
    const area = workspace.querySelector("[data-chart-area]");
    const heading = workspace.querySelector("[data-chart-heading]");
    const metadata = workspace.querySelector("[data-chart-metadata]");
    const moveLabel = workspace.querySelector("[data-chart-move]");
    const sessionCount = workspace.querySelector("[data-chart-session-count]");
    const eventCount = workspace.querySelector("[data-chart-event-count]");
    const rangePosition = workspace.querySelector("[data-chart-range-position]");
    const fromHigh = workspace.querySelector("[data-chart-from-high]");
    const highLabel = workspace.querySelector("[data-chart-high-label]");
    const axis = Object.fromEntries(
      [...workspace.querySelectorAll("[data-chart-axis]")].map((item) => [
        item.dataset.chartAxis,
        item,
      ]),
    );
    const dateAxis = Object.fromEntries(
      [...workspace.querySelectorAll("[data-chart-date]")].map((item) => [
        item.dataset.chartDate,
        item,
      ]),
    );
    const latestDate = points.at(-1).date;

    const applyRange = (key) => {
      const range = RANGES[key] || RANGES.full;
      const cutoff = range.days === null ? points[0].date : latestDate - range.days * DAY;
      const visible = points.filter((point) => point.date >= cutoff);
      const startDate = visible[0].date;
      const endDate = visible.at(-1).date;
      const dateSpan = Math.max(1, endDate - startDate);
      const prices = visible.map((point) => point.price);
      const low = Math.min(...prices);
      const high = Math.max(...prices);
      const priceSpan = Math.max(0.01, high - low);
      const xFor = (date) => ((date - startDate) / dateSpan) * 100;
      const yFor = (price) => 88 - ((price - low) / priceSpan) * 76;
      const mapped = visible.map((point) => ({
        ...point,
        x: xFor(point.date),
        y: yFor(point.price),
      }));

      for (const point of points) {
        const isVisible = point.date >= startDate && point.date <= endDate;
        show(point.element, isVisible);
        if (isVisible) setCoordinate(point.element, xFor(point.date), yFor(point.price));
      }

      for (const guide of workspace.querySelectorAll("[data-chart-guide]")) {
        const date = timestamp(guide);
        const isVisible = date >= startDate && date <= endDate;
        show(guide, isVisible);
        if (isVisible) setCoordinate(guide, xFor(date));
      }

      let visibleEvents = 0;
      for (const event of workspace.querySelectorAll("[data-chart-event]")) {
        const date = timestamp(event);
        const isVisible = date >= startDate && date <= endDate;
        show(event, isVisible);
        if (isVisible) {
          setCoordinate(event, xFor(date), yFor(number(event, "price")));
          visibleEvents += 1;
        }
      }

      for (const ledgerEvent of workspace.querySelectorAll("[data-chart-ledger-event]")) {
        const date = timestamp(ledgerEvent);
        show(ledgerEvent, date >= startDate && date <= endDate);
      }

      const now = workspace.querySelector("[data-chart-now]");
      if (now) setCoordinate(now, 100, yFor(number(now, "price")));
      const polylinePoints = mapped.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`);
      line?.setAttribute("points", polylinePoints.join(" "));
      area?.setAttribute("points", `0,96 ${polylinePoints.join(" ")} 100,96`);

      const first = visible[0];
      const last = visible.at(-1);
      const midpoint = (startDate + endDate) / 2;
      const middle = visible.reduce((nearest, point) =>
        Math.abs(point.date - midpoint) < Math.abs(nearest.date - midpoint) ? point : nearest,
      );
      const move = (last.price / first.price - 1) * 100;
      const position = ((last.price - low) / priceSpan) * 100;
      const distanceFromHigh = (last.price / high - 1) * 100;

      if (heading) heading.textContent = `${range.label} DAILY CLOSES`;
      if (metadata) {
        metadata.childNodes[0].textContent = `${shortDate.format(startDate)}–${shortDate.format(endDate)} · ${visible.length} MARKET SESSIONS `;
      }
      if (moveLabel) {
        moveLabel.textContent = `${percent(move)} MOVE`;
        moveLabel.classList.toggle("positive", move >= 0);
        moveLabel.classList.toggle("negative", move < 0);
      }
      if (sessionCount) sessionCount.textContent = String(visible.length);
      if (eventCount) eventCount.textContent = String(visibleEvents);
      if (rangePosition) rangePosition.textContent = `${position.toFixed(1)}%`;
      if (fromHigh) fromHigh.textContent = percent(distanceFromHigh);
      if (highLabel) highLabel.textContent = `FROM ${range.label} HIGH`;
      if (axis.high) axis.high.textContent = money.format(high);
      if (axis.mid) axis.mid.textContent = money.format((high + low) / 2);
      if (axis.low) axis.low.textContent = money.format(low);
      if (dateAxis.start) dateAxis.start.textContent = shortDate.format(first.date);
      if (dateAxis.mid) dateAxis.mid.textContent = shortDate.format(middle.date);
      if (dateAxis.end) dateAxis.end.textContent = shortDate.format(last.date);
      for (const button of buttons) {
        button.setAttribute("aria-pressed", String(button.dataset.chartRange === key));
      }
      if (card) card.dataset.chartRange = key;

      document.dispatchEvent(
        new CustomEvent("chart-viewport-change", {
          detail: { workspace, range: key, sessions: visible.length },
        }),
      );
    };

    for (const button of buttons) {
      button.addEventListener("click", () => applyRange(button.dataset.chartRange));
    }
    applyRange("full");
  };

  for (const workspace of document.querySelectorAll("[data-chart-workspace]")) {
    initializeChart(workspace);
  }
})();
