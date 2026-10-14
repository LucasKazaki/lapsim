"""Exercise real map interactions and inspect every tested accessibility state."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import subprocess
import sys
import threading

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "browser"


def main() -> int:
    engine = sys.argv[1] if len(sys.argv) > 1 else "chromium"
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    rows = []
    (OUT / "commit.txt").write_text(
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
    )
    try:
        with sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            for width, height in [(1440, 1000), (390, 844)]:
                for theme in ["light", "dark"]:
                    name = f"{engine}-{width}-{theme}"
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        color_scheme=theme,
                        reduced_motion="reduce",
                    )
                    context.tracing.start(
                        screenshots=True, snapshots=True, sources=True
                    )
                    page = context.new_page()
                    errors: list[str] = []
                    page.on(
                        "pageerror",
                        lambda error, errors=errors: errors.append(str(error)),
                    )
                    row = {
                        "case": name,
                        "checks": [],
                        "errors": errors,
                        "accessibility": [],
                    }
                    try:
                        page.goto(
                            base + "/docs/simulator_flowchart/index.html#lapsim",
                            wait_until="networkidle",
                        )
                        page.wait_for_function(
                            "window.LAPSIM_FLOWCHART?.totalNodeCount > 10000"
                        )
                        page.add_script_tag(
                            path=str(ROOT / "node_modules/axe-core/axe.min.js")
                        )

                        def check(condition, label):
                            row["checks"].append(
                                {"check": label, "passed": bool(condition)}
                            )
                            if not condition:
                                raise AssertionError(label)

                        def accessibility(state):
                            result = page.evaluate(
                                "async () => await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})"
                            )
                            row["accessibility"].append(
                                {
                                    "state": state,
                                    "violations": result["violations"],
                                    "incomplete": result["incomplete"],
                                }
                            )

                        check(
                            page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth + 1"
                            ),
                            "responsive document",
                        )
                        check(
                            page.get_by_role(
                                "treeitem", name=re.compile("LapSim simulator")
                            ).count()
                            == 1,
                            "graph nodes expose visible accessible names",
                        )
                        accessibility("initial")
                        page.locator("#collapse-all").click()
                        check(
                            page.evaluate(
                                "window.LAPSIM_FLOWCHART.visibleNodeCount === 1"
                            ),
                            "collapse to one",
                        )
                        page.locator('[data-node-id="lapsim"]').focus()
                        page.keyboard.press("ArrowRight")
                        check(
                            page.locator('[data-node-id="lapsim"]').get_attribute(
                                "aria-expanded"
                            )
                            == "true",
                            "keyboard expand",
                        )
                        page.keyboard.press("ArrowRight")
                        check(
                            page.evaluate(
                                "document.activeElement.dataset.nodeId !== 'lapsim'"
                            ),
                            "keyboard descend",
                        )
                        page.locator("#expand-all").click()
                        check(
                            page.evaluate(
                                "window.LAPSIM_FLOWCHART.visibleNodeCount === window.LAPSIM_FLOWCHART.totalNodeCount"
                            ),
                            "complete semantic expansion",
                        )
                        check(
                            page.locator("#nodes > *").count() < 2000,
                            "large graph is virtualized",
                        )
                        page.locator("#search-input").fill("battery")
                        page.locator("#search-next").click()
                        expect(page.locator("#details")).to_contain_text(
                            re.compile("battery", re.I)
                        )
                        check(
                            "battery" in page.locator("#details").inner_text().lower(),
                            "search selects evidence",
                        )
                        page.locator("#default-view").click()
                        card = page.locator("#lapsim-anatomy")
                        card.scroll_into_view_if_needed()
                        check(
                            card.locator('[data-anatomy-action="run"]').is_disabled(),
                            "system reduced motion is respected",
                        )
                        part = card.locator('[data-part-id="lap-battery"]')
                        part.focus()
                        page.keyboard.press("Enter")
                        check(
                            card.get_attribute("data-selected-part") == "lap-battery",
                            "keyboard selects anatomy part",
                        )
                        card.locator('[data-anatomy-action="explode"]').click()
                        check("is-exploded" in card.get_attribute("class"), "explode")
                        card.locator('[data-anatomy-action="reset"]').click()
                        check("is-exploded" not in card.get_attribute("class"), "reset")
                        page.locator('button[data-car-mode="signal"]').click()
                        check(
                            page.locator("#car-anatomy").get_attribute("data-car-mode")
                            == "signal",
                            "signal overlay",
                        )
                        page.locator("#appearance-toggle").click()
                        accessibility("manual-light")
                        page.locator("#appearance-toggle").click()
                        check(
                            page.locator("html").get_attribute("data-theme") == "dark",
                            "manual appearance",
                        )
                        accessibility("interactive-dark")
                        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                        page.emulate_media(reduced_motion="no-preference")
                        expect(
                            card.locator('[data-anatomy-action="run"]')
                        ).to_be_enabled()
                        check(
                            card.locator('[data-anatomy-action="run"]').is_enabled(),
                            "motion preference updates live",
                        )
                        page.locator("#motion-toggle").click()
                        card.locator('[data-anatomy-action="run"]').click()
                        check(
                            card.get_attribute("data-running") == "true",
                            "run action after enabling motion",
                        )
                        check(not errors, "no runtime exceptions")
                    except Exception as exc:
                        row["exception"] = str(exc)
                        page.screenshot(
                            path=str(OUT / f"{name}-failure.png"), full_page=True
                        )
                    row["passed"] = (
                        not row.get("exception")
                        and not errors
                        and not any(
                            state["violations"] for state in row["accessibility"]
                        )
                    )
                    context.tracing.stop(path=str(OUT / f"{name}-trace.zip"))
                    context.close()
                    rows.append(row)
                    print(
                        json.dumps(
                            {
                                "case": name,
                                "passed": row["passed"],
                                "checks": row["checks"],
                                "exception": row.get("exception"),
                                "violations": [
                                    {
                                        "state": state["state"],
                                        "rules": [
                                            {"id": v["id"], "nodes": len(v["nodes"])}
                                            for v in state["violations"]
                                        ],
                                    }
                                    for state in row["accessibility"]
                                ],
                            }
                        ),
                        flush=True,
                    )
            browser.close()
    finally:
        server.shutdown()
        (OUT / f"{engine}-results.json").write_text(json.dumps(rows, indent=2))
    return int(len(rows) != 4 or any(not row["passed"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
