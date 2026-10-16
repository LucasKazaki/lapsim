"""Actual browser bicycle selection/execution/export and CPython replay."""

from functools import partial
import csv
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

from lapsim.experiments.basic_dynamics import decode_json, replay_bicycle_record

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/basic-dynamics"


def main() -> None:
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
                viewport={"width": 1440, "height": 1000}, accept_downloads=True
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("""window.__basicResults=[];const Original=window.Worker;
                window.Worker=class extends Original{constructor(...args){super(...args);this.addEventListener('message',e=>{if(e.data.type==='result')window.__basicResults.push(e.data.result);});}};""")
            page.goto(f"http://127.0.0.1:{server.server_port}/index.html", wait_until="networkidle")
            page.get_by_role("link", name="Basic dynamics", exact=True).click()
            page.wait_for_url("**/basic.html")
            assert page.locator("#basic-model").input_value() == "dynamic_bicycle_v1"
            assert page.locator("#basic-save").is_disabled()
            page.locator("#basic-run").click()
            page.locator("#basic-cancel").click()
            assert page.locator("#basic-run").is_enabled()
            page.locator("#basic-duration").fill("1")
            for index, steering in enumerate(("2.3", "-2.3"), 1):
                page.locator("#basic-steer").fill(steering)
                page.locator("#basic-run").click()
                page.wait_for_function(
                    "n=>window.__basicResults.length>=n", arg=index, timeout=180000
                )
                with page.expect_download() as event:
                    page.locator("#basic-save").click()
                path = OUT / f"bicycle-{index}.json"
                event.value.save_as(path)
                record = decode_json(path.read_bytes())
                report = replay_bicycle_record(record)
                assert report["model_agreement"]
                assert (
                    record["scenario"]["controller_backend_id"]
                    == "none_prescribed_force"
                )
                assert record["scenario"]["model_id"] == "dynamic_bicycle_v1"
                assert record["result"]["plant_ticks"] == 500
                records.append(record)
            first, second = (record["result"]["states"][-1] for record in records)
            assert abs(first["x_m"] - second["x_m"]) < 1e-10
            assert abs(first["y_m"] + second["y_m"]) < 1e-10
            assert abs(first["yaw_rate_rad_s"] + second["yaw_rate_rad_s"]) < 1e-10
            assert page.locator("#basic-path polyline").count() == 1
            with page.expect_download() as event:
                page.locator("#basic-csv").click()
            csv_path = OUT / "bicycle-samples.csv"
            event.value.save_as(csv_path)
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == len(records[-1]["result"]["states"])
            assert abs(float(rows[-1]["x_m"]) - second["x_m"]) < 1e-10
            page.add_script_tag(path=str(ROOT / "node_modules/axe-core/axe.min.js"))
            audits = []
            for name, width, height, theme in (
                ("desktop", 1440, 1000, "light"),
                ("mobile", 390, 844, "dark"),
            ):
                page.set_viewport_size({"width": width, "height": height})
                page.emulate_media(color_scheme=theme, reduced_motion="reduce")
                audit = page.evaluate(
                    "async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})"
                )
                assert not audit["violations"], [
                    (item["id"], item["description"]) for item in audit["violations"]
                ]
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                audits.append(
                    {
                        "viewport": name,
                        "theme": theme,
                        "automatic_accessibility_violations": len(audit["violations"]),
                    }
                )
            page.locator("#basic-speed").fill("9")
            assert page.locator("#basic-save").is_disabled()
            assert page.locator("#basic-results").is_hidden()
            assert not errors, errors
            summary = {
                "model_id": "dynamic_bicycle_v1",
                "actual_worker_runs": 2,
                "downloaded_records_replay_natively": True,
                "mirrored_maneuver": True,
                "cancel_retry": True,
                "changed_input_invalidates_result": True,
                "views": audits,
                "source": records[0]["runtime"]["source"],
                "limits": "Synthetic browser/host numerical evidence; no controller/firmware/physical validation",
            }
            (OUT / "summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(summary))
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
