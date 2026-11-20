/* Real Chromium checks of the allowlisted staged map, in GitHub Actions only. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {chromium} = require("playwright");
const base = process.env.LAPSIM_PUBLIC_URL;
assert(/^http:\/\/127\.0\.0\.1:\d+\/$/.test(base || ""),"Runner-local HTTP origin required");
const pinned = "6d6f355221c66047a83003ff6ccc8ccc63467c75";
const stageUrl = base + "audit/map-runtime/#lapsim";
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.LAPSIM_BROWSER_PATH});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
    page.setDefaultTimeout(15000);
    const errors=[],consoleErrors=[],failedRequests=[],badResponses=[];
    page.on("pageerror",e=>errors.push(e.message));
    page.on("console",m=>{if(m.type()==="error") consoleErrors.push(m.text());});
    page.on("requestfailed",r=>failedRequests.push(r.url()));
    page.on("response",r=>{if(r.url().startsWith(base) && r.status()>=400) badResponses.push({url:r.url(),status:r.status()});});
    await page.goto(stageUrl,{waitUntil:"networkidle"});
    await page.waitForFunction(()=>window.LAPSIM_FLOWCHART?.totalNodeCount>=13000);
    assert.equal(await page.locator("#details h2").textContent(),"LapSim simulator");
    assert((await page.locator("#publication-scope").textContent()).includes("not a simulator run"));
    assert.equal(await page.getByRole("link",{name:"Historical R11 replay",exact:true}).getAttribute("href"),"../../tournament/");
    assert.equal(await page.locator("#car-title").textContent(),"2026–27 Formula SAE EV · RWD system view");
    const totals = await page.evaluate(()=>({total:window.LAPSIM_FLOWCHART.totalNodeCount,visible:window.LAPSIM_FLOWCHART.visibleNodeCount}));
    for (const href of await page.locator("#details a.source-link").evaluateAll(a=>a.map(x=>x.href)))
      assert(href.startsWith("https://github.com/LucasKazaki/lapsim/blob/"+pinned+"/"),"Root evidence must be commit-pinned");
    await page.locator("#search-input").fill("dynamic_pressure_pa");
    await page.locator("#search-input").press("ArrowDown");
    await page.locator("#search-input").press("Enter");
    await page.waitForFunction(()=>document.querySelector("#details")?.textContent.includes("Individual variable"));
    assert.match(await page.locator("#details").textContent(),/dynamic_pressure_pa/);
    assert.match(await page.locator("#details").textContent(),/Exact source expressions/);
    const variableLinks=await page.locator("#details a.source-link").evaluateAll(a=>a.map(x=>x.href));
    assert(variableLinks.length>0);
    assert(variableLinks.some(h=>h.startsWith("https://github.com/LucasKazaki/lapsim/blob/"+pinned+"/") && /#L[1-9]\d*$/.test(h)));
    const directory = await page.evaluate(() => {
      const queue=[window.LAPSIM_FLOWCHART_DATA.root];
      while(queue.length) {
        const n=queue.shift();
        const source=(n.sources||[]).find(s=>s.publicationHref.includes("/tree/"));
        if(source) return {id:n.id,href:source.publicationHref};
        queue.push(...(n.children||[]));
      }
      return null;
    });
    assert(directory,"A real directory-source case must be exercised");
    await page.evaluate(id=>window.LAPSIM_FLOWCHART.revealNode(id),directory.id);
    assert((await page.locator("#details a.source-link").evaluateAll(a=>a.map(x=>x.href))).includes(directory.href));
    assert(directory.href.startsWith("https://github.com/LucasKazaki/lapsim/tree/"+pinned+"/"));
    await page.locator("#collapse-all").click();
    assert.equal(await page.evaluate(()=>window.LAPSIM_FLOWCHART.visibleNodeCount),1);
    const root=page.locator('#nodes [data-node-id="lapsim"]');
    await root.focus();
    await page.keyboard.press("ArrowRight");
    assert(await page.evaluate(()=>window.LAPSIM_FLOWCHART.visibleNodeCount)>1);
    await page.keyboard.press("ArrowRight");
    assert.notEqual(await page.evaluate(()=>document.activeElement?.dataset.nodeId),"lapsim");
    await page.keyboard.press("ArrowLeft");
    assert.equal(await page.evaluate(()=>document.activeElement?.dataset.nodeId),"lapsim");
    await page.locator("#expand-all").click();
    assert.equal(await page.evaluate(()=>window.LAPSIM_FLOWCHART.visibleNodeCount),totals.total);
    const rendered=await page.locator("#nodes > *").count();
    assert(rendered>0 && rendered<2000,"Large inventory must use viewport culling");
    await page.locator("#default-view").click();
    await page.evaluate(()=>window.LAPSIM_FLOWCHART.revealNode("lapsim"));
    const lap=page.locator("#lapsim-anatomy"),car=page.locator("#car-anatomy");
    await page.locator("#lapsim-stage > svg.lap-figure").waitFor();
    await page.locator("#car-stage > svg.car-figure").waitFor();
    assert.equal(await lap.locator(".machine-part").count(),12);
    assert.equal(await car.locator(".machine-part").count(),14);
    await lap.locator('[data-part-id="lap-course"]').click();
    assert.equal(await lap.getAttribute("data-selected-part"),"lap-course");
    assert.equal(await lap.locator("[data-detail-title]").textContent(),"Course and curvature reel");
    assert.equal(await lap.locator('.machine-part[aria-pressed="true"]').count(),1);
    const cell=lap.locator('[data-part-id="lap-cell"]');
    await cell.focus(); await page.keyboard.press("Enter");
    assert.equal(await lap.locator("[data-detail-title]").textContent(),"Vehicle cell integrator");
    assert.equal(await lap.getByRole("link",{name:"Architecture",exact:true}).getAttribute("href"),"https://github.com/LucasKazaki/lapsim/blob/"+pinned+"/docs/architecture.md");
    assert.equal(await lap.getByRole("link",{name:"Source map",exact:true}).getAttribute("href"),"#map-top");
    await car.locator('[data-part-id="car-accumulator"]').click();
    assert.equal(await car.locator("[data-detail-title]").textContent(),"High-voltage accumulator");
    assert.equal(await car.locator('.machine-part[aria-pressed="true"]').count(),1);
    assert.equal(await car.getByRole("link",{name:"Battery model",exact:true}).getAttribute("href"),"https://github.com/LucasKazaki/lapsim/blob/"+pinned+"/docs/battery_model.md");
    for (const mode of ["signal","structure","power"]) {
      await car.locator('button[data-car-mode="'+mode+'"]').click();
      assert.equal(await car.getAttribute("data-car-mode"),mode);
      assert.equal(await car.locator("svg").getAttribute("data-mode"),mode);
      assert.equal(await car.locator('button[data-car-mode="'+mode+'"]').getAttribute("aria-pressed"),"true");
    }
    await car.locator('[data-anatomy-action="explode"]').click();
    assert((await car.getAttribute("class")).includes("is-exploded"));
    assert.equal(await car.locator('[data-anatomy-action="explode"]').textContent(),"Assemble");
    await car.locator('[data-anatomy-action="reset"]').click();
    assert(!(await car.getAttribute("class")).includes("is-exploded"));
    assert.equal(await car.getAttribute("data-selected-part"),"car-rwd");
    assert.equal(await car.getAttribute("data-car-mode"),"power");
    await lap.getByRole("link",{name:"Source map",exact:true}).click();
    assert.equal(new URL(page.url()).hash,"#map-top");
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      await page.setViewportSize(viewport);
      await page.goto(stageUrl,{waitUntil:"networkidle"});
      await page.waitForFunction(()=>window.LAPSIM_FLOWCHART?.totalNodeCount>=13000);
      assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)),"Document overflows viewport");
      await page.screenshot({path:"/tmp/lapsim-map-staged-"+viewport.width+".png",fullPage:true});
    }
    assert.deepEqual(errors,[]);
    assert.deepEqual(consoleErrors,[]);
    assert.deepEqual(failedRequests,[]);
    assert.deepEqual(badResponses,[]);
    const receipt={schema:"lapsim.static-map-browser-receipt.v1",sourceCommit:pinned,
      browser:browser.version(),stagedUrl:stageUrl,viewports:[1440,390],totals,renderedWhenExpanded:rendered,
      variableLinks,directory,controls:["variable search","directory evidence","collapse/expand","keyboard tree","virtualized expansion","anatomy pointer/keyboard","car modes","explode/reset","local source-map shortcut"],
      errors,consoleErrors,failedRequests,badResponses,scope:"Static recorded source presentation only; no simulator/model execution"};
    fs.writeFileSync("audit/map-publication-browser.json",JSON.stringify(receipt,null,2)+"\n");
    console.log(JSON.stringify(receipt,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
