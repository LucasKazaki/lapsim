"""Real Chromium/Pyodide matched control studies, downloads and host replay."""

import csv
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from lapsim.experiments.basic_dynamics import decode_json
from lapsim.experiments.control_study import replay_control_comparison

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/control-study"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(SimpleHTTPRequestHandler, directory=str(ROOT / "dist/web")),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    records = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1440, "height": 1100}, accept_downloads=True
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                """window.__controlResults=[];const Original=window.Worker;window.Worker=class extends Original{constructor(...args){super(...args);this.addEventListener('message',e=>{if(e.data.type==='result')window.__controlResults.push(e.data.result);});}};"""
            )
            page.goto(
                f"http://127.0.0.1:{server.server_port}/index.html",
                wait_until="networkidle",
            )
            page.get_by_role("link", name="Torque control", exact=True).click()
            page.wait_for_url("**/control.html")
            assert page.locator("#control-case").input_value() == "launch"
            page.locator("#control-run").click()
            page.locator("#control-cancel").click()
            assert page.locator("#control-run").is_enabled()
            page.locator("#control-duration").fill(".2")
            for count, case in enumerate(("launch", "split_grip", "stale"), 1):
                page.locator("#control-case").select_option(case)
                page.locator("#control-run").click()
                page.wait_for_function(
                    "n=>window.__controlResults.length>=n", arg=count, timeout=180000
                )
                with page.expect_download() as event:
                    page.locator("#control-save").click()
                path = OUT / (case + ".json")
                event.value.save_as(path)
                record = decode_json(path.read_bytes(), maximum_bytes=40_000_000)
                replay = replay_control_comparison(record)
                assert replay["model_agreement"]
                for key in ("A", "B"):
                    run = record["runs"][key]
                    assert (
                        run["scenario"]["controller_backend_id"] == "python_reference"
                    )
                    assert (
                        run["controller_source"]["runtime_source_scope"]
                        == "browser_python_owner_subset_v1"
                    )
                    assert (
                        run["result"]["controller_calls"] == 20
                        and run["result"]["plant_ticks"] == 200
                    )
                records.append(record)
            assert (
                records[0]["runs"]["A"]["result"] == records[0]["runs"]["B"]["result"]
            )
            assert (
                records[1]["runs"]["A"]["result"] != records[1]["runs"]["B"]["result"]
            )
            for key in ("A", "B"):
                late = [
                    row
                    for row in records[-1]["runs"][key]["result"]["controller_events"]
                    if row["time_us"] >= 90_000
                ]
                assert all(not row["core"]["command_allowed"] for row in late)
            assert page.locator("#control-speed-plot polyline").count() == 2
            assert page.locator("#control-stages tr").count() == 22
            with page.expect_download() as event:
                page.locator("#control-csv").click()
            csv_path = OUT / "samples.csv"
            event.value.save_as(csv_path)
            with csv_path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == sum(
                len(records[-1]["runs"][key]["result"]["observations"])
                for key in ("A", "B")
            )
            assert (
                abs(
                    float(rows[-1]["x_m"])
                    - records[-1]["runs"]["B"]["result"]["final_state"]["plant"]["x_m"]
                )
                < 1e-10
            )
            page.add_script_tag(path=str(ROOT / "node_modules/axe-core/axe.min.js"))
            views = []
            for name, width, height, theme in [
                ("desktop", 1440, 1100, "light"),
                ("mobile", 390, 844, "dark"),
            ]:
                page.set_viewport_size({"width": width, "height": height})
                page.emulate_media(
                    color_scheme="light" if theme == "light" else "dark",
                    reduced_motion="reduce",
                )
                result = page.evaluate(
                    "async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})"
                )
                assert not result["violations"], result["violations"]
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.screenshot(path=str(OUT / (name + ".png")), full_page=True)
                views.append(
                    {"viewport": name, "automatic_accessibility_violations": 0}
                )
            page.locator("#control-speed").fill("3")
            assert (
                page.locator("#control-save").is_disabled()
                and page.locator("#control-results").is_hidden()
            )
            page.locator("#control-file").set_input_files(str(OUT / "launch.json"))
            page.wait_for_function("window.__controlResults.length>=4", timeout=180000)
            assert page.locator("#control-speed").is_disabled()
            assert page.locator("#control-run").is_disabled()
            assert "Imported comparison" in page.locator("#control-status").inner_text()
            with page.expect_download() as event:
                page.locator("#control-save").click()
            imported_path = OUT / "imported-replayed.json"
            event.value.save_as(imported_path)
            imported = decode_json(imported_path.read_bytes(), maximum_bytes=40_000_000)
            assert imported == records[0] and imported["run_id"] == records[0]["run_id"]
            page.locator("#control-new").click()
            assert page.locator("#control-speed").is_enabled()
            assert page.locator("#control-results").is_hidden()
            invalid_path = OUT / "invalid-import.json"
            invalid_path.write_text(
                '{"schema":"lapsim.control-comparison.v1"}', encoding="utf-8"
            )
            page.locator("#control-file").set_input_files(str(invalid_path))
            page.locator("#control-error").wait_for(state="visible", timeout=180000)
            assert page.locator("#control-save").is_disabled()
            assert page.locator("#control-results").is_hidden()
            assert page.locator("#control-run").is_enabled()
            assert not errors, errors
            summary = {
                "actual_worker_comparisons": 3,
                "host_replayed_runs": 6,
                "browser_replayed_imported_runs": 2,
                "import_preserves_exact_record": True,
                "invalid_import_rejected": True,
                "cases": ["launch", "split_grip", "stale"],
                "nominal_strategies_identical": True,
                "split_grip_strategies_differ": True,
                "cancel_retry": True,
                "changed_input_invalidates_results": True,
                "csv_matches_record": True,
                "views": views,
                "source": records[0]["runs"]["A"]["runtime"]["source"],
                "limits": "Python browser execution only; native and emulator have separate host evidence.",
            }
            (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
