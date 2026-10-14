"""Run actual Pyodide physics and verify byte-preserved exports using native replay."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import math
from pathlib import Path
import sys
import threading

from playwright.sync_api import sync_playwright
from lapsim.experiments.lap_replay import replay_lap_record
from lapsim.experiments.run_record import RunRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "web-runtime"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(SimpleHTTPRequestHandler, directory=str(ROOT / "dist/web")),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    rows = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000}, accept_downloads=True
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            # Observe real worker messages; do not replace the worker or its physics.
            page.add_init_script("""window.__physicsResults=[]; const RealWorker=window.Worker;
              window.Worker=class extends RealWorker { constructor(...args){super(...args);
                this.addEventListener('message', event=>{if(event.data.type==='result')window.__physicsResults.push(event.data.result);});}};""")
            page.goto(
                f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle"
            )
            page.add_script_tag(path=str(ROOT / "node_modules/axe-core/axe.min.js"))
            spec = importlib.util.spec_from_file_location(
                "lapsim_browser_bridge", ROOT / "web/bridge.py"
            )
            bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge)
            page.locator("#advanced-settings").evaluate(
                "element => element.open = true"
            )
            page.locator("#cell-size").select_option("5")
            # Boot cancellation must leave the controls usable; retry uses a new worker.
            page.locator("#run-button").click()
            page.locator("#cancel-button").click()
            assert page.locator("#run-button").is_enabled()
            for index, profile in enumerate(
                ["repository_baseline", "prius_2026_le"], 1
            ):
                page.locator("#vehicle-profile").select_option(profile)
                page.locator("#run-button").click()
                page.wait_for_function(
                    "n => window.__physicsResults.length >= n",
                    arg=index,
                    timeout=300000,
                )
                result = page.evaluate("window.__physicsResults.at(-1)")
                assert result["status"] == "completed", result
                with page.expect_download() as event:
                    page.locator("#save-run").click()
                destination = OUT / f"{profile}.json"
                event.value.save_as(destination)
                record = RunRecord.load(destination)
                replay = replay_lap_record(destination)
                assert replay.model_agreement, replay
                settings = result["settings"]
                native = bridge.run_simulation(settings)
                # Compare the underlying numeric results, not rounded display labels.
                differences = {}
                for key in ("elapsedTimeS", "energyKwh", "socFinal"):
                    actual, expected = result[key], native[key]
                    assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (
                        key,
                        actual,
                        expected,
                    )
                    differences[key] = abs(actual - expected)
                axe = page.evaluate(
                    "async () => await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})"
                )
                (OUT / f"{profile}-accessibility.json").write_text(
                    json.dumps(axe, indent=2)
                )
                page.screenshot(path=str(OUT / f"{profile}.png"), full_page=True)
                rows.append(
                    {
                        "profile": profile,
                        "record_id": record.run_id,
                        "replay_matches": replay.model_agreement,
                        "absolute_differences": differences,
                        "accessibility_violations": [
                            v["id"] for v in axe["violations"]
                        ],
                    }
                )
                print(json.dumps(rows[-1]), flush=True)
                page.locator("#pin-run").click()
            assert not errors, errors
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            page.screenshot(path=str(OUT / "mobile-result.png"), full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        (OUT / "results.json").write_text(json.dumps(rows, indent=2))
    return int(len(rows) != 2 or any(row["accessibility_violations"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
