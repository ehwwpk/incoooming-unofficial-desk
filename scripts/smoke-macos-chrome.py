"""Native Chrome acceptance checks using fictional files on disposable macOS CI runners."""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import suppress
from decimal import Decimal
from pathlib import Path

from macos_smoke_support import (
    evidence_dir,
    free_port,
    record,
    require,
    require_macos,
    stop_owned,
    wait_ready,
)
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait

POSITIONS = (
    "Account,Symbol,Description,Quantity,Last Price,Market Value,Average Price\n"
    "Demo account,CVX,Chevron Corp,100,195.00,19500.00,150.00\n"
    "Demo account,CVX  260821C00205000,CVX 08/21/2026 205 Call,-1,1.25,-125,2\n"
)
ACTIVITY = (
    "Account,Date,Action,Symbol,Description,Quantity,Price,Fees,Amount\n"
    "Demo account,08/01/2026,Sell to Open,CVX  260821C00205000,"
    "CVX 08/21/2026 205 Call,1,1.25,0.03,124.97\n"
    "Demo account,08/02/2026,Dividend,CVX,Chevron dividend,,,,171.00\n"
)


def run_browser(port: int, isolated: Path) -> None:
    base = f"http://127.0.0.1:{port}"
    binary = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    require(binary.is_file(), "The native Google Chrome application is not installed.")
    options = webdriver.ChromeOptions()
    options.binary_location = str(binary)
    options.add_argument(f"--user-data-dir={isolated / 'Chrome profile'}")
    # Headed Chrome with its normal sandbox. Selenium Manager resolves the matching driver.
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)
    checks: list[str] = []
    captures: dict[str, object] = {}
    browser_version = driver.capabilities.get("browserVersion")
    driver_version = driver.capabilities.get("chrome", {}).get("chromedriverVersion")

    def visible(selector: str):
        return wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, selector)))

    def scroll_to(element) -> None:
        # The runner's usable screen can be shorter than the requested window. ChromeDriver's
        # native focus/typing can queue smooth scrolling after our first reposition. Reposition
        # each attempt and confirm stable geometry over two frames before the real click.
        wait.until(
            lambda current: current.execute_async_script(
                """
                const element = arguments[0], done = arguments[arguments.length - 1];
                element.scrollIntoView({block:'center', inline:'center', behavior:'instant'});
                const first = element.getBoundingClientRect();
                requestAnimationFrame(() => requestAnimationFrame(() => {
                  const rect = element.getBoundingClientRect();
                  const x = (rect.left + rect.right) / 2, y = (rect.top + rect.bottom) / 2;
                  const hit = document.elementFromPoint(x, y);
                  const settled = Math.abs(first.left - rect.left) < 1
                    && Math.abs(first.top - rect.top) < 1;
                  const unblocked = x >= 0 && x < innerWidth && y >= 0 && y < innerHeight
                    && element.contains(hit);
                  window.incooomingChromeScroll = {
                    target: element.tagName, left: rect.left, top: rect.top,
                    width: rect.width, height: rect.height,
                    viewport_width: innerWidth, viewport_height: innerHeight,
                    hit: hit?.tagName || null, settled, unblocked
                  };
                  done(settled && unblocked);
                }));
                """,
                element,
            )
        )

    def click_element(element) -> None:
        scroll_to(element)
        element.click()

    def click(selector: str) -> None:
        click_element(wait.until(expected.element_to_be_clickable((By.CSS_SELECTOR, selector))))

    def capture(name: str) -> None:
        dimensions = driver.execute_script(
            "return {width:document.documentElement.clientWidth,"
            "height:document.documentElement.clientHeight,"
            "content:document.documentElement.scrollWidth,"
            "device_pixel_ratio:window.devicePixelRatio};"
        )
        require(dimensions["content"] <= dimensions["width"] + 2, f"{name} overflows the window.")
        require(
            driver.save_screenshot(str(evidence_dir() / f"chrome-{name}.png")),
            f"The {name} screenshot was not saved.",
        )
        captures[name] = dimensions
        checks.append(name)

    def chart_ready() -> None:
        visible("[data-performance-compare-canvas] canvas")
        wait.until(
            lambda current: (
                current.find_element(
                    By.CSS_SELECTOR, "[data-performance-compare-empty]"
                ).get_attribute("hidden")
                is not None
            )
        )
        summary = visible("[data-performance-compare]").text
        for line in ("MANAGED", "STARTING SHARES", "SPY", "SPY \u00d7 EXPOSURE"):
            require(line in summary, f"The benchmark line {line} is missing.")
        chart = driver.find_element(By.CSS_SELECTOR, "[data-performance-compare-chart]")
        scroll_to(chart)
        ActionChains(driver).move_to_element(chart).click().perform()
        wait.until(
            lambda current: current.execute_script(
                "return document.activeElement === arguments[0];", chart
            )
        )
        ActionChains(driver).send_keys(Keys.HOME).perform()
        first_date = visible("[data-performance-inspector-date]").text
        require(bool(first_date), "The keyboard inspector did not identify a date.")
        ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform()
        wait.until(
            lambda current: (
                current.find_element(By.CSS_SELECTOR, "[data-performance-inspector-date]").text
                != first_date
            )
        )
        ActionChains(driver).send_keys(Keys.ARROW_LEFT).perform()
        wait.until(
            lambda current: (
                current.find_element(By.CSS_SELECTOR, "[data-performance-inspector-date]").text
                == first_date
            )
        )

    def preview_ready(current) -> bool:
        preview = current.find_element(By.CSS_SELECTOR, "[data-import-preview]")
        if not preview.is_displayed():
            return False
        if "2 POSITIONS / 2 ACTIVITY" in preview.text:
            require(
                bool(
                    current.find_element(
                        By.CSS_SELECTOR, "[data-preview-fingerprint]"
                    ).get_attribute("value")
                ),
                "The valid CSV preview did not approve the reviewed bytes for import.",
            )
            return True
        observed = current.execute_script("return window.incooomingChromePreview;")
        if observed and observed.get("status"):
            raise RuntimeError(
                f"CSV preview did not accept both files (HTTP {observed['status']}); "
                "see chrome.json diagnostics."
            )
        if current.find_element(By.CSS_SELECTOR, "[data-import-submit]").is_enabled():
            raise RuntimeError("CSV preview failed before upload; see Chrome diagnostics.")
        return False

    def require_invalidated() -> None:
        require(
            driver.find_element(By.CSS_SELECTOR, "[data-preview-fingerprint]").get_attribute(
                "value"
            )
            == "",
            "An input change retained approval for the old preview.",
        )
        require(
            not driver.find_element(By.CSS_SELECTOR, "[data-import-preview]").is_displayed(),
            "The old preview remained visible after an input change.",
        )

    try:
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(15)
        driver.set_window_size(1440, 1000)
        driver.get(f"{base}/sources")
        capture("source-gateway")
        click("button[aria-label='Open demo book']")
        visible("body[data-demo-mode='true']")
        require(
            "SIMULATED DATA" in driver.find_element(By.TAG_NAME, "body").text,
            "Demo label missing.",
        )
        capture("demo-desk")
        driver.get(f"{base}/workspaces/attribution")
        chart_ready()
        capture("results-all")
        previous = driver.find_element(By.CSS_SELECTOR, "[data-performance-compare-chart]")
        click(".performance-period-selector a[href$='period=1m']")
        wait.until(expected.staleness_of(previous))
        wait.until(expected.url_contains("period=1m"))
        visible(".performance-period-selector a[href$='period=1m'][aria-current='page']")
        chart_ready()
        capture("results-month")

        driver.get(f"{base}/workspaces/risk")
        lens = driver.find_element(By.CSS_SELECTOR, "[data-open-book-section='risk-lens']")
        if lens.get_attribute("open") is None:
            click_element(lens.find_element(By.TAG_NAME, "summary"))
        require("100% MODEL COVERAGE" in lens.text, "Risk Lens lost modeled coverage.")
        require("DELTA / NEXT +$1" in lens.text, "Risk Lens delta is missing.")
        capture("risk-lens")
        rows = driver.find_elements(By.CSS_SELECTOR, "[data-roll-board-contract]")
        row = next(item for item in rows if "URNM" in item.text and "$55.00P" in item.text)
        link = row.find_element(
            By.CSS_SELECTOR, "a[href*='targetExpiration=2026-08-28'][href*='targetStrike=54']"
        )
        require(
            "5.00" in link.find_element(By.CSS_SELECTOR, ".roll-board-choice-line strong").text,
            "The fixture roll economics changed; review this smoke case.",
        )
        source = row.get_attribute("data-roll-board-contract")
        click_element(link)
        visible("[data-radar-roll-handoff]")
        wait.until(
            lambda current: (
                current.find_element(By.CSS_SELECTOR, "[data-radar-roll-handoff]").get_attribute(
                    "data-roll-status"
                )
                not in {None, "pending"}
            )
        )
        net = visible("[data-radar-roll-net]").text
        require(
            "\u2212$0.05/SH" in net and net.endswith("\u2212$5"),
            "Radar roll cash differs from the board.",
        )
        require(
            source
            == driver.find_element(
                By.CSS_SELECTOR, "[data-radar-roll-source-picker]"
            ).get_attribute("value"),
            "Radar source selection drifted.",
        )
        capture("put-roll-radar")

        uploads = isolated / "Fictional CSV files"
        uploads.mkdir()
        files = []
        for name, contents in (
            ("positions sample.csv", POSITIONS),
            ("activity sample.csv", ACTIVITY),
        ):
            path = uploads / name
            path.write_text(contents, encoding="utf-8")
            files.append(path)
        driver.get(f"{base}/sources")
        disclosure = driver.find_element(By.CSS_SELECTOR, ".source-csv-card")
        if disclosure.get_attribute("open") is None:
            click_element(disclosure.find_element(By.TAG_NAME, "summary"))
        visible("input[name='dataset_name']").send_keys("Chrome fictional CSV check")
        click("input[name='broker'][value='generic'] + span")
        require(
            driver.find_element(
                By.CSS_SELECTOR, "input[name='broker'][value='generic']"
            ).is_selected(),
            "The generic CSV format was not selected.",
        )
        # Observe real requests without replacing file selection, file bytes, or responses.
        driver.execute_script("""
            const originalFetch = window.fetch;
            window.incooomingChromePreview = null;
            window.incooomingChromePreviewCount = 0;
            window.fetch = async function(input, init) {
              const observe = input === '/sources/csv/preview';
              if (observe) {
                window.incooomingChromePreviewCount += 1;
                window.incooomingChromePreview = {files:
                  init.body.getAll('files').map(file => ({name: file.name, size: file.size}))};
              }
              const response = await originalFetch.call(this, input, init);
              if (observe) {
                const result = window.incooomingChromePreview;
                result.status = response.status;
                try {
                  const body = await response.clone().json();
                  result.ok = body.ok ?? null;
                  result.counts = body.counts ?? null;
                  result.can_commit = body.can_commit ?? null;
                } catch { result.error = 'Non-JSON preview response'; }
              }
              return response;
            };
        """)
        oversized = uploads / "oversized sample.csv"
        with oversized.open("wb") as handle:
            handle.truncate(10 * 1024 * 1024 + 1)
        file_input = driver.find_element(By.CSS_SELECTOR, "[data-source-files]")
        file_input.send_keys(str(oversized))
        click("[data-import-submit]")
        wait.until(
            lambda current: (
                "10 MB or smaller"
                in current.find_element(By.CSS_SELECTOR, "[data-import-preview]").text
            )
        )
        require(
            driver.execute_script("return window.incooomingChromePreviewCount;") == 0,
            "An oversized upload reached the server.",
        )
        checks.append("csv-oversized-rejected-before-upload")
        file_input.clear()
        file_input.send_keys("\n".join(str(path) for path in files))
        reads = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            Promise.all([...document.querySelector('[data-source-files]').files].map(async file => {
              try { return {name: file.name, size: file.size,
                            bytes: (await file.arrayBuffer()).byteLength}; }
              catch (error) { return {name: file.name, size: file.size, error: error.name}; }
            })).then(done).catch(() => done([]));
        """)
        captures["csv_disk_reads"] = reads
        require(
            len(reads) == 2
            and all(
                item.get("bytes") == path.stat().st_size == item.get("size")
                for item, path in zip(reads, files, strict=True)
            ),
            "Native Chrome could not read the selected disk files.",
        )
        checks.append("csv-native-disk-files-readable")
        click("[data-import-submit]")
        wait.until(preview_ready)

        file_input.clear()
        file_input.send_keys("\n".join(str(path) for path in reversed(files)))
        require_invalidated()
        click("[data-import-submit]")
        wait.until(preview_ready)
        checks.append("csv-reselection-invalidates-reviewed-upload")
        visible("input[name='dataset_name']").send_keys(" revised")
        require_invalidated()
        click("[data-import-submit]")
        wait.until(preview_ready)
        require(
            driver.execute_script("return window.incooomingChromePreviewCount;") == 3,
            "The CSV preview flow made unexpected requests.",
        )
        checks.append("csv-name-edit-invalidates-reviewed-upload")
        captures["csv_preview"] = driver.execute_script("return window.incooomingChromePreview;")
        capture("csv-preview")

        # Committing must use the reviewed bytes even after the selected disk file changes.
        files[0].write_text("This fictional file changed after preview.\n", encoding="utf-8")
        previous = driver.find_element(By.CSS_SELECTOR, ".csv-import-form")
        click("[data-import-submit]")
        wait.until(expected.staleness_of(previous))
        visible("body[data-demo-mode='false']")
        require(
            "CSV BOOK" in driver.find_element(By.TAG_NAME, "body").text,
            "The imported CSV source was not selected.",
        )
        imported = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            fetch('/api/v1/dashboard').then(async response => {
              const body = await response.json();
              done({status: response.status, mode: body.mode,
                    position_count: body.positions?.length,
                    total_value: body.portfolio?.total_value});
            }).catch(() => done({status: 'request-failed'}));
        """)
        require(imported.get("status") == 200, "The imported CSV dashboard API failed.")
        require(imported.get("mode") == "csv", "The imported source cookie was not applied.")
        require(imported.get("position_count") == 2, "The reviewed positions were not imported.")
        require(
            Decimal(imported["total_value"]) == Decimal("19375"),
            "The reviewed position values changed during final import.",
        )
        captures["csv_import"] = imported
        checks.append("csv-commit-preserves-reviewed-bytes")
        capture("csv-desk")
        driver.get(f"{base}/workspaces/attribution")
        visible("body[data-workspace-key='attribution']")
        require(
            not driver.find_elements(By.CSS_SELECTOR, "[data-performance-comparison-payload]"),
            "The CSV book invented a historical benchmark path.",
        )
        capture("csv-results")
        record(
            "chrome",
            {
                "status": "passed",
                "chrome": browser_version,
                "chromedriver": driver_version,
                "headed": True,
                "checks": checks,
                "captures": captures,
                "scope": "Native macOS Chrome with fictional demo and real disk CSV files only.",
            },
        )
    except Exception as exc:
        diagnostics: dict[str, object] = {}
        with suppress(Exception):
            diagnostics = driver.execute_script("""
                return {url: location.href,
                  scroll_target: window.incooomingChromeScroll || null,
                  csv_preview: window.incooomingChromePreview || null,
                  csv_preview_count: window.incooomingChromePreviewCount ?? null,
                  selected_files: [...(document.querySelector('[data-source-files]')?.files || [])]
                    .map(file => ({name: file.name, size: file.size}))};
            """)
        record(
            "chrome",
            {
                "status": "failed",
                "chrome": browser_version,
                "chromedriver": driver_version,
                "headed": True,
                "checks": checks,
                "captures": captures,
                "error_type": type(exc).__name__,
                "diagnostics": diagnostics,
            },
        )
        with suppress(Exception):
            driver.save_screenshot(str(evidence_dir() / "chrome-failure.png"))
        raise
    finally:
        driver.quit()


def run() -> None:
    require_macos()
    port = free_port()
    temp = Path(os.environ["RUNNER_TEMP"])
    executable = temp / "wheel environment/bin/schwab-dashboard"
    require(executable.is_file(), "The fresh installed-wheel environment is missing.")
    with tempfile.TemporaryDirectory(prefix="Chrome isolated run ", dir=temp) as directory:
        isolated = Path(directory)
        env = {
            **os.environ,
            "SCHWAB_DASHBOARD_DATA_DIR": str(isolated / "Isolated book"),
            "SCHWAB_DASHBOARD_HOST": "127.0.0.1",
            "SCHWAB_DASHBOARD_PORT": str(port),
            "SCHWAB_DASHBOARD_DEMO_MODE": "false",
            "SCHWAB_AUTO_SYNC_ENABLED": "false",
        }
        for key in ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "PYTHONPATH"):
            env.pop(key, None)
        with (evidence_dir() / "chrome-server.log").open("wb") as log:
            process = subprocess.Popen(
                [str(executable), "serve"],
                cwd=isolated,
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                wait_ready(process, port)
                run_browser(port, isolated)
            finally:
                stop_owned(process)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        if not (evidence_dir() / "chrome.json").exists():
            record("chrome", {"status": "failed", "error_type": type(exc).__name__})
        raise
