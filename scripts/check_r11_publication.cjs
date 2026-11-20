/* Public R11 publication verification only. No solver, renderer or experiment dispatch. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const root = path.resolve(__dirname,"..");
const sourceRoot = path.join(root,".r11-reviewed-source");
const names = ["README.md","app.js","data.js","data.json","index.html","parameter_display.js","scoring.js","style.css","test-bundled.cjs","video.html"];
const publicationNotice = "<p class=\"muted\">Course-source notice: repository layouts derived from <a href=\"https://github.com/AMZ-Racing/fssim/tree/cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4\">AMZ Racing FSSIM</a> retain the <a href=\"AMZ-FSSIM-LICENSE.md\">upstream MIT notice</a>. Processed approximate maps and this synthetic replay do not establish the source vehicle's accuracy. Per-course provenance remains in the bundled review JSON; this notice does not license other project material.</p>";
const readmeNotice = "\n## Pages publication notice\n\nAMZ Racing FSSIM source layouts used by repository course inputs are pinned at\n[cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4](https://github.com/AMZ-Racing/fssim/tree/cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4).\nTheir [upstream MIT notice](AMZ-FSSIM-LICENSE.md) is retained unchanged. Processed\napproximate maps and synthetic replay are not validation of this car. Individual\ncourse provenance remains in the bundled review JSON. This notice applies to AMZ\nmaterial and supplies no new license for other project code or data.\n";
const sourceCommit = "6d6f355221c66047a83003ff6ccc8ccc63467c75";
const hash = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
function writeEvidence(name, evidence) {
  fs.mkdirSync(path.join(root,"audit"),{recursive:true});
  fs.writeFileSync(path.join(root,"audit",name),JSON.stringify(evidence,null,2)+"\n");
  console.log(JSON.stringify(evidence));
}
function sourceCheck() {
  const files = [];
  for (const name of names) {
    const source = fs.readFileSync(path.join(sourceRoot,"web","tournament-review",name));
    let expected = source;
    if (name === "index.html") {
      const text = source.toString("utf8"), old = '<a href="../../">LapSim / source map</a>';
      assert.equal(text.split(old).length-1,1,"Exactly one source map anchor must be transformed");
      expected = Buffer.from(text.replace(old,'<a href="../docs/simulator_flowchart/">LapSim / source map</a>').replace("<footer>Synthetic engineering evidence",publicationNotice+"\n<footer>Synthetic engineering evidence"));
    }
    if (name === "README.md") expected = Buffer.from(source.toString("utf8")+readmeNotice);
    const actual = fs.readFileSync(path.join(root,"tournament",name));
    assert(actual.equals(expected),"Unreviewed publication drift: "+name);
    files.push({path:"tournament/"+name,sha256:hash(actual),transform:name==="index.html"?"unique map href plus scoped AMZ notice":name==="README.md"?"scoped AMZ notice appended":"exact source bytes"});
  }
  const licenseSource = fs.readFileSync(path.join(sourceRoot,"configs","courses","upstream","amz-fssim","LICENSE.md"));
  const licenseActual = fs.readFileSync(path.join(root,"tournament","AMZ-FSSIM-LICENSE.md"));
  assert(licenseActual.equals(licenseSource),"AMZ notice differs from pinned upstream copy");
  files.push({path:"tournament/AMZ-FSSIM-LICENSE.md",sha256:hash(licenseActual),transform:"exact pinned AMZ notice"});
  const media = [];
  for (const name of ["tournament-r11-stable.mp4","tournament-r11-stable.preview.png"]) {
    const expected = fs.readFileSync(path.join(sourceRoot,"web","tournament-review",name));
    const actual = fs.readFileSync(path.join(root,"tournament",name));
    assert(actual.equals(expected),"Media differs from reviewed source: "+name);
    const digest = hash(actual);
    if (name.endsWith(".mp4")) assert.equal(digest,"cdc30b1322b604d134cd46ea8a2b0f3ef46f1242a20ddb405e02732fdb66eccc");
    media.push({path:"tournament/"+name,sha256:digest,bytes:actual.length});
  }
  writeEvidence("r11-publication-source.json",{scope:"historical R11 exact publication projection; no numerical execution",sourceCommit,files,media});
}
async function browserCheck() {
  const base = process.env.LAPSIM_PUBLIC_URL;
  assert(base && /^http:\/\/127\.0\.0\.1:\d+\/$/.test(base),"Runner-local public origin required");
  const {chromium} = require("playwright");
  const browser = await chromium.launch({headless:true,executablePath:process.env.LAPSIM_BROWSER_PATH});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"reduce"});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      await page.setViewportSize(viewport);
      await page.goto(base+"tournament/");
      await page.locator("#winner").filter({hasText:"awd-p0-fsg"}).waitFor();
      assert.equal(await page.locator("#criterion").inputValue(),"points");
      assert.equal(await page.locator("#three-winners > *").count(),3);
      assert.match(await page.locator("#three-winners").innerText(),/awd-p4-fsg/);
      assert.match(await page.locator("#three-winners").innerText(),/awd-p0-fsg/);
      assert.match(await page.locator("#three-winners").innerText(),/awd-p3-fsg/);
      assert.match(await page.locator("body").innerText(),/historical R11 snapshot/i);
      assert.match(await page.locator("body").innerText(),/not official event points/i);
      assert.equal(await page.locator("header a").getAttribute("href"),"../docs/simulator_flowchart/");
      for (const [criterion,winner] of [["time","awd-p4-fsg"],["energy","awd-p3-fsg"],["points","awd-p0-fsg"]]) {
        await page.locator("#criterion").selectOption(criterion);
        assert.equal(await page.locator("#winner").textContent(),winner);
      }
      assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth+1)),"Publication overflows viewport");
      await page.screenshot({path:`/tmp/lapsim-r11-publication-${viewport.width}.png`,fullPage:true});
    }
    await page.goto(base+"tournament/video.html");
    assert.match(await page.locator("body").innerText(),/Historical fastest-only highlight/);
    const video = page.locator("#video");
    await page.waitForFunction(() => { const v=document.getElementById("video"); return v.readyState>=1 && Number.isFinite(v.duration) && v.duration>0; });
    await video.evaluate(v => {v.muted=true;});
    await page.locator("#start").click();
    await page.waitForFunction(() => document.getElementById("video").currentTime>0.1);
    const videoEvidence = await video.evaluate(v => { const result={duration:v.duration,currentTime:v.currentTime};v.pause();return result; });
    assert.deepEqual(errors,[]);
    writeEvidence("r11-publication-browser.json",{scope:"runner-local recorded R11 UI; not live production or new physics",sourceCommit,browser:browser.version(),viewports:[1440,390],criteria:["time","energy","points"],video:videoEvidence,errors});
  } finally { await browser.close(); }
}
const mode=process.argv[2];
if(mode==="source") sourceCheck();
else if(mode==="browser") browserCheck().catch(error=>{console.error(error);process.exitCode=1;});
else throw Error("Fixed CI verification mode required");
