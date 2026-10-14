"""Browser behavior and accessibility audit, preserving evidence on every failure."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(sys.argv[1]).resolve()
TARGET = sys.argv[2]
OUT = Path('audit')
OUT.mkdir(exist_ok=True)
server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
results = []
failures = []
(OUT/'commit.txt').write_text(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True))
(OUT/'environment.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True))
(OUT/'node-environment.json').write_text(subprocess.check_output(['npm', 'ls', '--json'], text=True))

with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height in [(1440, 1000), (390, 844)]:
        for theme in ['light', 'dark']:
            key = f'{TARGET}-{width}-{theme}'
            context = browser.new_context(viewport={'width': width, 'height': height}, color_scheme=theme, reduced_motion='reduce')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
            item = {'case': key, 'errors': errors, 'violations': [], 'checks': {}}
            try:
                page.goto(base+'/docs/simulator_flowchart/index.html#lapsim', wait_until='networkidle')
                page.locator('[data-node-id="lapsim"]').first.wait_for()
                page.screenshot(path=str(OUT/f'{key}.png'), full_page=True)
                item['checks']['rendered_root'] = True
                item['checks']['no_horizontal_overflow'] = page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
                page.locator('#collapse-all').click()
                item['checks']['collapse_to_one'] = page.locator('#nodes > g').count() == 1
                page.locator('#expand-level').click()
                item['checks']['expands'] = page.locator('#nodes > g').count() > 1
                page.locator('#search-input').fill('battery')
                page.locator('#search-next').click()
                item['checks']['search_selects_details'] = 'battery' in page.locator('#details').inner_text().lower()
                page.locator('#default-view').focus()
                page.keyboard.press('Enter')
                item['checks']['keyboard_default'] = page.locator('#nodes > g').count() > 1
                page.add_script_tag(path='node_modules/axe-core/axe.min.js')
                axe = page.evaluate("async () => await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})")
                item['violations'] = axe['violations']
                item['incomplete'] = axe['incomplete']
                item['checks']['automated_accessibility'] = not axe['violations']
                item['checks']['no_runtime_errors'] = not errors
            except Exception as exc:
                item['exception'] = str(exc)
                failures.append(key)
                page.screenshot(path=str(OUT/f'{key}-failure.png'), full_page=True)
            if not all(item['checks'].values()):
                failures.append(key)
            results.append(item)
            print(json.dumps({'case': key, 'checks': item['checks'], 'errors': errors, 'exception': item.get('exception'), 'violations': [{'id': v['id'], 'impact': v['impact'], 'nodes': len(v['nodes'])} for v in item['violations']]}), flush=True)
            context.close()
    browser.close()
server.shutdown()
(OUT/'browser-results.json').write_text(json.dumps(results, indent=2))
sys.exit(bool(failures))
