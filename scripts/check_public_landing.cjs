/* GitHub-hosted static navigation QA only: no simulator or external page execution. */
"use strict";
const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const base = process.env.LAPSIM_PUBLIC_URL;
if (!base || !/^http:\/\/127\.0\.0\.1:\d+\/$/.test(base)) throw Error("A fixed runner-local test origin is required.");
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.LAPSIM_BROWSER_PATH});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      await page.setViewportSize(viewport);
      await page.goto(base);
      await page.getByRole("heading",{name:"LapSim",exact:true}).waitFor();
      assert.equal(new URL(page.url()).pathname,"/");
      assert.equal(await page.locator('link[rel="canonical"]').getAttribute("href"),"https://lucaskazaki.github.io/lapsim/");
      for (const [name,href] of [
        ["Open the interactive map","docs/simulator_flowchart/"],
        ["Open historical R11 replay","tournament/"],
        ["Watch historical R11 ghost video","tournament/video.html"]
      ]) assert.equal(await page.getByRole("link",{name,exact:true}).getAttribute("href"),href);
      assert(await page.getByText("Historical R11 · 26 October 2026",{exact:true}).isVisible());
      assert(await page.getByText("Source only",{exact:true}).isVisible());
      assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)));
      await page.screenshot({path:`/tmp/lapsim-public-landing-${viewport.width}.png`,fullPage:true});
    }
    const response = await page.request.get(base+"public-site.json");
    assert.equal(response.status(),200);
    const manifest = await response.json();
    assert.equal(manifest.referencedPublicSourceCommit,"6d6f355221c66047a83003ff6ccc8ccc63467c75");
    assert.equal(manifest.retainedMapAndReplayBaseCommit,"d521dd5282c20c31a6a964ea4d88e4b34a004974");
    assert.equal(manifest.newSimulationResultsIncluded,false);
    assert.equal(manifest.currentMap.sourceCommit,manifest.referencedPublicSourceCommit);
    assert.equal(manifest.currentMap.runtimeAssetCount,26);
    assert.equal(manifest.currentMap.staticOnly,true);
    await page.goto(base+"?review=public#lapsim");
    await page.waitForFunction(() => window.LAPSIM_FLOWCHART?.totalNodeCount > 0);
    assert.equal(new URL(page.url()).pathname,"/docs/simulator_flowchart/");
    assert.equal(new URL(page.url()).search,"?review=public");
    assert.equal(new URL(page.url()).hash,"#lapsim");
    await page.getByRole("link",{name:"Historical R11 replay",exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({scope:"static landing/map navigation",browser:browser.version(),viewports:[1440,390],legacyFragmentPreserved:true,errors}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
