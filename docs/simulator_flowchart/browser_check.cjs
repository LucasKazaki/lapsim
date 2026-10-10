/* Optional real-browser regression check. Requires Playwright and installed Edge.
   NODE_PATH may point to the Codex bundled Node packages; no install is needed. */
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const {chromium} = require('playwright');
let activeBrowser;

(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  activeBrowser = browser;
  const context = await browser.newContext({viewport:{width:1440,height:1000}, reducedMotion:'reduce', offline:true});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href);
  await page.waitForFunction(() => window.LAPSIM_FLOWCHART?.totalNodeCount > 10000);
  assert.equal(await page.locator('#details h2').innerText(), 'LapSim simulator');
  const count = await page.evaluate(() => window.LAPSIM_FLOWCHART.totalNodeCount);

  await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('aero-pressure'));
  await page.getByRole('button', {name:'Equation 1 equation · 3 children', exact:false}).click().catch(async () => {
    await page.locator('[data-related-id="aero-pressure-eq-1"]').first().click();
  });
  await page.locator('[data-related-id]').filter({hasText:'rho'}).first().click();
  assert.match(await page.locator('#details').innerText(), /kg\/m³/);
  await page.locator('#search-input').fill('dynamic_pressure_pa');
  assert(await page.locator('.search-result').count() > 0);
  await page.locator('#search-input').press('ArrowDown');
  await page.keyboard.press('Enter');
  assert.match(await page.locator('#details').innerText(), /dynamic_pressure_pa/);

  await page.getByRole('button', {name:'Collapse all', exact:true}).click();
  assert.equal(await page.evaluate(() => window.LAPSIM_FLOWCHART.visibleNodeCount), 1);
  let root = page.locator('[data-node-id="lapsim"]');
  await root.dblclick();
  assert.equal(await page.locator('[data-node-id="lapsim"]').getAttribute('aria-expanded'), 'true');
  await page.getByRole('button', {name:'Collapse all', exact:true}).click();
  root = page.locator('[data-node-id="lapsim"]');
  await root.focus();
  await root.press('ArrowRight');
  assert.equal(await page.locator('[data-node-id="lapsim"]').getAttribute('aria-expanded'), 'true');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.nodeId), 'lapsim');
  await page.keyboard.press('ArrowRight');
  assert.notEqual(await page.evaluate(() => document.activeElement.dataset.nodeId), 'lapsim');
  await page.keyboard.press('ArrowLeft');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.nodeId), 'lapsim');

  await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('aero-pressure'));
  await page.waitForTimeout(50);
  const dragged = page.locator('[data-node-id="aero-pressure"]');
  const before = await dragged.getAttribute('transform');
  const box = await dragged.boundingBox();
  await page.mouse.move(box.x + box.width/2, box.y + box.height/2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width/2 + 80, box.y + box.height/2 + 35, {steps:6});
  await page.mouse.up();
  assert.notEqual(await page.locator('[data-node-id="aero-pressure"]').getAttribute('transform'), before);
  await page.getByRole('button', {name:'Reset positions', exact:true}).click();
  assert.equal(await page.locator('[data-node-id="aero-pressure"]').getAttribute('transform'), before);

  const expansion = await page.evaluate(() => {
    const start = performance.now();
    window.LAPSIM_FLOWCHART.expandAll();
    return {milliseconds:performance.now()-start, expanded:window.LAPSIM_FLOWCHART.visibleNodeCount};
  });
  assert.equal(expansion.expanded, count);
  await page.waitForTimeout(100);
  const painted = await page.locator('#nodes > *').count();
  assert(painted < 2000, `Overview created ${painted} SVG nodes`);
  assert(expansion.milliseconds < 10000, `Expand all blocked for ${expansion.milliseconds}ms`);
  await page.getByRole('button', {name:'Default', exact:true}).click();
  await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('battery-rc'));
  if (process.argv[2]) await page.screenshot({path:process.argv[2]});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href + '#%invalid');
  await page.waitForFunction(() => window.LAPSIM_FLOWCHART?.selectedId === 'lapsim');
  assert.equal(await page.locator('#details h2').innerText(), 'LapSim simulator');
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({offline:true,totalNodes:count,overviewMarks:painted,expandAllMilliseconds:Math.round(expansion.milliseconds),checks:'source search, variable units, keyboard hierarchy, reduced motion, complete expansion, no console errors'}));
  await browser.close();
})().catch(error => {console.error(error);process.exitCode=1;}).finally(async () => {if(activeBrowser) await activeBrowser.close();});
