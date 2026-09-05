"""Native Safari acceptance checks. Run only on the disposable macOS CI runners."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
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


def run_browser(port: int) -> None:
    base = f"http://127.0.0.1:{port}"
    driver = webdriver.Safari()
    wait = WebDriverWait(driver, 20)
    checks: list[str] = []
    captures: dict[str, object] = {}
    browser_version = driver.capabilities.get("browserVersion")
    upload_directory: tempfile.TemporaryDirectory[str] | None = None

    def visible(selector: str):
        return wait.until(expected.visibility_of_element_located((By.CSS_SELECTOR, selector)))

    def click(selector: str) -> None:
        wait.until(expected.element_to_be_clickable((By.CSS_SELECTOR, selector))).click()

    def capture(name: str) -> None:
        dimensions = driver.execute_script(
            "return {width:document.documentElement.clientWidth,"
            "height:document.documentElement.clientHeight,"
            "content:document.documentElement.scrollWidth,"
            "device_pixel_ratio:window.devicePixelRatio};"
        )
        require(dimensions["content"] <= dimensions["width"] + 2, f"{name} overflows the window.")
        require(
            driver.save_screenshot(str(evidence_dir() / f"safari-{name}.png")),
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
        # Observe native input/focus for useful failure evidence without dispatching fake events.
        driver.execute_script("""
            window.incooomingSmokeInputs = [];
            for (const eventType of ['keydown', 'focusin', 'focusout']) {
              document.addEventListener(eventType, (event) => {
                window.incooomingSmokeInputs.push({
                  type: event.type, key: event.key || null,
                  tag: event.target.tagName,
                  chart: event.target.hasAttribute?.('data-performance-compare-chart') || false
                });
                window.incooomingSmokeInputs = window.incooomingSmokeInputs.slice(-12);
              }, true);
            }
        """)
        # Click/focus and real keyboard input exercise actual interaction, beyond canvas creation.
        chart = driver.find_element(By.CSS_SELECTOR, "[data-performance-compare-chart]")
        ActionChains(driver).move_to_element(chart).click().perform()
        wait.until(
            lambda current: current.execute_script(
                "return document.activeElement === arguments[0];", chart
            )
        )
        ActionChains(driver).send_keys(Keys.HOME).perform()
        visible("[data-performance-inspector]")
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
        visible("[data-performance-inspector]")

    try:
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(15)
        driver.set_window_size(1440, 1000)
        driver.get(f"{base}/sources")
        capture("source-gateway")
        click("button[aria-label='Open demo book']")
        visible("body[data-demo-mode='true']")
        require(
            "SIMULATED DATA" in driver.find_element(By.TAG_NAME, "body").text, "Demo label missing."
        )
        capture("demo-desk")

        driver.get(f"{base}/workspaces/attribution")
        chart_ready()
        capture("results-all")
        prior_chart = driver.find_element(By.CSS_SELECTOR, "[data-performance-compare-chart]")
        click(".performance-period-selector a[href$='period=1m']")
        wait.until(expected.staleness_of(prior_chart))
        wait.until(expected.url_contains("period=1m"))
        visible(".performance-period-selector a[href$='period=1m'][aria-current='page']")
        chart_ready()
        capture("results-month")

        driver.get(f"{base}/workspaces/risk")
        lens = driver.find_element(By.CSS_SELECTOR, "[data-open-book-section='risk-lens']")
        if lens.get_attribute("open") is None:
            lens.find_element(By.TAG_NAME, "summary").click()
        require("100% MODEL COVERAGE" in lens.text, "Risk Lens lost modeled coverage.")
        require("DELTA / NEXT +$1" in lens.text, "Risk Lens delta is missing.")
        capture("risk-lens")
        # The fixture symbol is read from the page so whitespace padding cannot alter the test.
        rows = driver.find_elements(By.CSS_SELECTOR, "[data-roll-board-contract]")
        row = next(item for item in rows if "URNM" in item.text and "$55.00P" in item.text)
        link = row.find_element(
            By.CSS_SELECTOR, "a[href*='targetExpiration=2026-08-28'][href*='targetStrike=54']"
        )
        board_cash = link.find_element(By.CSS_SELECTOR, ".roll-board-choice-line strong").text
        require("5.00" in board_cash, "The fixture roll economics changed; review this smoke case.")
        source = row.get_attribute("data-roll-board-contract")
        link.click()
        visible("[data-radar-roll-handoff]")
        wait.until(
            lambda current: (
                current.find_element(By.CSS_SELECTOR, "[data-radar-roll-handoff]").get_attribute(
                    "data-roll-status"
                )
                not in {None, "pending"}
            )
        )
        source_label = visible("[data-radar-roll-source]").text
        require("55" in source_label and "P" in source_label, "Radar lost the source contract.")
        net = visible("[data-radar-roll-net]").text
        require(
            "\u2212$0.05/SH" in net and net.endswith("\u2212$5"),
            "Radar roll cash differs from board.",
        )
        picker = driver.find_element(By.CSS_SELECTOR, "[data-radar-roll-source-picker]")
        require(source == picker.get_attribute("value"), "Radar source selection drifted.")
        capture("put-roll-radar")

        driver.get(f"{base}/sources")
        disclosure = driver.find_element(By.CSS_SELECTOR, ".source-csv-card")
        if disclosure.get_attribute("open") is None:
            disclosure.find_element(By.TAG_NAME, "summary").click()
        visible("input[name='dataset_name']").send_keys("Safari fictional CSV check")
        click("input[name='broker'][value='generic'] + span")
        require(
            driver.find_element(
                By.CSS_SELECTOR, "input[name='broker'][value='generic']"
            ).is_selected(),
            "The generic CSV format was not selected.",
        )
        # SafariDriver requires world-readable uploads; do not change runner-wide permissions.
        # https://developer.apple.com/documentation/webkit/macos-webdriver-commands-for-safari-11-1-and-earlier
        upload_directory = tempfile.TemporaryDirectory(
            prefix="incoooming-safari-fictional-", dir="/private/tmp"
        )
        uploads = Path(upload_directory.name)
        uploads.chmod(0o755)
        files = []
        for name, contents in (("positions.csv", POSITIONS), ("activity.csv", ACTIVITY)):
            path = uploads / name
            path.write_text(contents, encoding="utf-8")
            path.chmod(0o644)
            files.append(str(path))
        captures["csv_filesystem"] = {
            "directories": [
                {"name": path.name, "mode": oct(stat.S_IMODE(path.stat().st_mode))}
                for path in (uploads, *uploads.parents)
            ],
            "files": [
                {"name": Path(path).name, "mode": oct(stat.S_IMODE(Path(path).stat().st_mode))}
                for path in files
            ],
        }
        # Observe the real fictional upload and response; do not alter either payload.
        driver.execute_script("""
            const originalFetch = window.fetch;
            window.incooomingSmokePreview = null;
            window.fetch = async function(input, init) {
              const observe = input === '/sources/csv/preview';
              if (observe) {
                const allowed = new Set(['dataset_name', 'broker', 'files', 'preview_fingerprint']);
                const fields = init?.body instanceof FormData
                  ? [...init.body.entries()].filter(([name]) => allowed.has(name)).map(
                      ([name, value]) => value instanceof File
                        ? {name, kind: 'file', filename: value.name,
                           media_type: value.type, size: value.size}
                        : {name, kind: 'text', length: value.length,
                           broker: name === 'broker' ? value : null})
                  : [];
                window.incooomingSmokePreview = {fields};
              }
              const response = await originalFetch.call(this, input, init);
              if (observe) {
                window.incooomingSmokePreview.status = response.status;
                try {
                  const body = await response.clone().json();
                  window.incooomingSmokePreview.response = {
                    ok: body.ok ?? null, counts: body.counts ?? null,
                    error: typeof body.error === 'string' ? body.error : null,
                    detail: Array.isArray(body.detail)
                      ? body.detail.map(({type, loc, msg}) => ({type, loc, msg})) : []
                  };
                } catch {
                  window.incooomingSmokePreview.response = {error: 'Non-JSON preview response'};
                }
              }
              return response;
            };
        """)
        oversized = uploads / "oversized.csv"
        with oversized.open("wb") as handle:
            handle.truncate(10 * 1024 * 1024 + 1)
        oversized.chmod(0o644)
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
            driver.execute_script("return window.incooomingSmokePreview;") is None,
            "An oversized upload reached the server instead of being rejected before reading.",
        )
        checks.append("csv-oversized-rejected-before-upload")
        file_input.clear()
        file_input.send_keys("\n".join(files))
        click("[data-import-submit]")

        def preview_ready(current) -> bool:
            preview = current.find_element(By.CSS_SELECTOR, "[data-import-preview]")
            if not preview.is_displayed():
                return False
            if "2 POSITIONS / 2 ACTIVITY" in preview.text:
                return True
            observed = current.execute_script("return window.incooomingSmokePreview;")
            if observed and observed.get("status"):
                raise RuntimeError(
                    f"CSV preview did not accept both files (HTTP {observed['status']}); "
                    "see the sanitized CSV diagnostics in safari.json."
                )
            if current.find_element(By.CSS_SELECTOR, "[data-import-submit]").is_enabled():
                raise RuntimeError("CSV preview failed before upload; see Safari diagnostics.")
            return False

        wait.until(preview_ready)
        visible("input[name='dataset_name']").send_keys(" revised")
        require(
            driver.find_element(By.CSS_SELECTOR, "[data-preview-fingerprint]").get_attribute(
                "value"
            )
            == "",
            "An edited book name retained approval for the old preview.",
        )
        require(
            not driver.find_element(By.CSS_SELECTOR, "[data-import-preview]").is_displayed(),
            "The old preview remained visible after an edit.",
        )
        click("[data-import-submit]")
        wait.until(preview_ready)
        checks.append("csv-edit-invalidates-reviewed-upload")
        captures["csv_upload"] = driver.execute_script("return window.incooomingSmokePreview;")
        capture("csv-preview")
        # The final import must use precisely the reviewed bytes, even if a disk file changes.
        Path(files[0]).write_text("This fictional file changed after preview.\n", encoding="utf-8")
        prior_form = driver.find_element(By.CSS_SELECTOR, ".csv-import-form")
        click("[data-import-submit]")
        wait.until(expected.staleness_of(prior_form))
        visible("body[data-demo-mode='false']")
        require(
            "CSV BOOK" in driver.find_element(By.TAG_NAME, "body").text, "CSV source not selected."
        )
        imported = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            fetch('/api/v1/dashboard').then(async (response) => {
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
            "safari",
            {
                "status": "passed",
                "safari": browser_version,
                "checks": checks,
                "captures": captures,
                "scope": "Native Safari with fictional demo and CSV data only.",
            },
        )
    except Exception as exc:
        diagnostics = driver.execute_script("""
            const active = document.activeElement;
            const inspector = document.querySelector('[data-performance-inspector]');
            return {
              url: location.href,
              focused_element: active ? {
                tag: active.tagName, id: active.id,
                chart: active.hasAttribute('data-performance-compare-chart')
              } : null,
              inspector_hidden: inspector?.hidden ?? null,
              inspector_date:
                document.querySelector('[data-performance-inspector-date]')?.textContent || null,
              input_events: window.incooomingSmokeInputs || [],
              csv_preview: window.incooomingSmokePreview || null
            };
        """)
        diagnostics["csv_file_reads"] = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            const input = document.querySelector('[data-source-files]');
            const form = document.querySelector('.csv-import-form');
            if (!input || !form) { done([]); return; }
            (async () => {
              const reads = [];
              for (const [source, files] of [
                ['input', [...input.files]], ['form_data', new FormData(form).getAll('files')]
              ]) {
                for (const file of files) {
                  try {
                    const bytes = await file.arrayBuffer();
                    reads.push({source, size: file.size, bytes: bytes.byteLength});
                  } catch (error) {
                    reads.push({source, size: file.size, error: error.name});
                  }
                }
              }
              done(reads);
            })().catch(() => done([{error: 'DiagnosticFailed'}]));
        """)
        record(
            "safari",
            {
                "status": "failed",
                "safari": browser_version,
                "checks": checks,
                "captures": captures,
                "error_type": type(exc).__name__,
                "diagnostics": diagnostics,
            },
        )
        driver.save_screenshot(str(evidence_dir() / "safari-failure.png"))
        raise
    finally:
        driver.quit()
        if upload_directory is not None:
            upload_directory.cleanup()


def run() -> None:
    require_macos()
    port = free_port()
    temp = Path(os.environ["RUNNER_TEMP"])
    env = {
        **os.environ,
        "SCHWAB_DASHBOARD_DATA_DIR": str(temp / "Safari isolated book"),
        "SCHWAB_DASHBOARD_HOST": "127.0.0.1",
        "SCHWAB_DASHBOARD_PORT": str(port),
        "SCHWAB_DASHBOARD_DEMO_MODE": "false",
        "SCHWAB_AUTO_SYNC_ENABLED": "false",
    }
    for key in ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "PYTHONPATH"):
        env.pop(key, None)
    with (evidence_dir() / "safari-server.log").open("wb") as log:
        process = subprocess.Popen(
            [str(temp / "wheel environment/bin/schwab-dashboard"), "serve"],
            cwd=temp,
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            wait_ready(process, port)
            run_browser(port)
        finally:
            stop_owned(process)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        if not (evidence_dir() / "safari.json").exists():
            record("safari", {"status": "failed", "error_type": type(exc).__name__})
        raise
