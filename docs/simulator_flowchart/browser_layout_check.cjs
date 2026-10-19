/* Real layout/drag regression for both the source map and its published version.
   Requires Playwright; set LAPSIM_BROWSER_PATH for an installed browser. */
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const {chromium} = require('playwright');

const mapUrl = process.env.LAPSIM_MAP_URL || pathToFileURL(path.join(__dirname, 'index.html')).href;
const launchOptions = {headless: true};
if (process.env.LAPSIM_BROWSER_PATH) launchOptions.executablePath = process.env.LAPSIM_BROWSER_PATH;
if (process.env.LAPSIM_BROWSER_CHANNEL) launchOptions.channel = process.env.LAPSIM_BROWSER_CHANNEL;

async function settle(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function layout(page) {
  await settle(page);
  return page.evaluate(() => {
    const rect = selector => {
      const {x, y, width, height} = document.querySelector(selector).getBoundingClientRect();
      return {x, y, width, height};
    };
    return {
      header: rect('.app-header'), toolbar: rect('.toolbar'),
      workspace: rect('.workspace'), graph: rect('#graph-panel'), details: rect('#details'),
      overflow: document.documentElement.scrollWidth > innerWidth + 1,
    };
  });
}

function equalSize(actual, expected, label) {
  assert(Math.abs(actual - expected) <= 1, `${label}: ${actual}px instead of ${expected}px`);
}

async function dragDivider(page, dx, dy) {
  const divider = page.locator('#panel-divider');
  await divider.scrollIntoViewIfNeeded();
  const box = await divider.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy, {steps: 8});
  await page.mouse.up();
  await settle(page);
}

(async () => {
  const browser = await chromium.launch(launchOptions);
  try {
    const context = await browser.newContext({viewport: {width: 900, height: 2200}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(mapUrl);
    await page.waitForFunction(() => window.LAPSIM_FLOWCHART?.totalNodeCount > 0);
    await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('lapsim'));
    const root = await layout(page);
    await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('condition-inputs'));
    const branch = await layout(page);
    equalSize(branch.header.height, root.header.height, 'Opening a subtree must not stretch the header');
    equalSize(branch.toolbar.height, root.toolbar.height, 'Opening a subtree must not stretch the toolbar');

    await page.setViewportSize({width: 1440, height: 1000});
    await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('lapsim'));
    const before = await layout(page);
    const divider = page.getByRole('separator', {name: 'Resize graph and details panels'});
    assert.equal(await divider.getAttribute('aria-orientation'), 'vertical');
    assert.equal(await divider.evaluate(el => getComputedStyle(el).cursor), 'col-resize');
    await dragDivider(page, -140, 0);
    const after = await layout(page);
    equalSize(after.details.width, before.details.width + 140, 'Dragging left widens details');
    equalSize(after.graph.width, before.graph.width - 140, 'Dragging left narrows graph');
    equalSize(after.header.height, before.header.height, 'Dragging preserves header');
    equalSize(after.toolbar.height, before.toolbar.height, 'Dragging preserves toolbar');

    await page.evaluate(() => window.LAPSIM_FLOWCHART.revealNode('condition-inputs'));
    equalSize((await layout(page)).details.width, after.details.width, 'Subtree selection preserves the split');
    await divider.focus();
    await page.keyboard.press('ArrowRight');
    assert((await layout(page)).graph.width > after.graph.width, 'Keyboard resizing changes the graph width');
    await page.keyboard.press('Home');
    assert((await layout(page)).graph.width >= 279, 'Graph keeps a usable minimum width');
    await page.keyboard.press('End');
    assert((await layout(page)).details.width >= 239, 'Details keep a usable minimum width');
    await divider.dblclick();
    equalSize((await layout(page)).details.width, before.details.width, 'Double-click restores the default split');

    await page.setViewportSize({width: 390, height: 844});
    const mobileBefore = await layout(page);
    assert.equal(await divider.getAttribute('aria-orientation'), 'horizontal');
    assert.equal(await divider.evaluate(el => getComputedStyle(el).cursor), 'row-resize');
    assert(!mobileBefore.overflow, 'Mobile document has no horizontal overflow');
    await dragDivider(page, 0, 90);
    const mobileAfter = await layout(page);
    equalSize(mobileAfter.graph.height, mobileBefore.graph.height + 90, 'Stacked graph resizes vertically');
    equalSize(mobileAfter.details.height, mobileBefore.details.height - 90, 'Stacked details share the available height');
    assert(mobileAfter.details.height >= 199, 'Stacked details remain usable');
    await divider.focus();
    await page.keyboard.press('ArrowUp');
    assert((await layout(page)).graph.height < mobileAfter.graph.height, 'Keyboard resizes stacked panels');
    await page.keyboard.press('Enter');
    equalSize((await layout(page)).graph.height, mobileBefore.graph.height, 'Enter restores the default split');

    await page.setViewportSize({width: 1024, height: 768});
    const resized = await layout(page);
    assert(!resized.overflow && resized.graph.width >= 279 && resized.details.width >= 239, 'Viewport change preserves usable panel bounds');
    assert.equal(await divider.getAttribute('aria-orientation'), 'vertical');
    assert.equal(await page.locator('html').getAttribute('data-panel-resizing'), null, 'Drag state is cleaned up');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({browser: browser.version(), mapUrl, checks: 'stable subtree header, pointer and keyboard resizing, reset, desktop/mobile bounds, no runtime errors'}));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
