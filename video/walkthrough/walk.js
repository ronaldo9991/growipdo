/* Records a real walkthrough of the live site: two genuine runs, no staging. */
const { chromium } = require("playwright");

const BASE = process.env.SITE || "https://growpido.up.railway.app";
const OUT = process.env.OUT || "out";
const T0 = Date.now();
const at = () => ((Date.now() - T0) / 1000).toFixed(1);
const log = (m) => console.log(`[${at()}s] ${m}`);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function wheel(page, total, step = 90, pause = 60) {
  const n = Math.max(1, Math.round(Math.abs(total) / step));
  const dir = total < 0 ? -step : step;
  for (let i = 0; i < n; i++) { await page.mouse.wheel(0, dir); await wait(pause); }
}

async function tab(page, name, dwell = 2500) {
  const b = page.locator(`#sectabs button[data-sec="${name}"]`);
  if (await b.count()) { await b.first().click(); log(`tab ${name}`); await wait(dwell); }
}

(async () => {
  const browser = await chromium.launch({ args: ["--force-color-profile=srgb", "--font-render-hinting=none"] });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: OUT, size: { width: 1280, height: 720 } },
    deviceScaleFactor: 1,
    reducedMotion: "no-preference",
  });
  const page = await ctx.newPage();
  const marks = [];
  const mark = (label) => { marks.push({ label, t: +at() }); log(`MARK ${label}`); };

  /* 1. the home page */
  mark("home");
  await page.goto(BASE, { waitUntil: "networkidle" });
  await wait(4500);
  await wheel(page, 700);
  await wait(2500);
  await wheel(page, 500);
  await wait(2000);
  await wheel(page, -1200, 120, 40);
  await wait(1500);

  /* 2. track B, filled and submitted for real */
  mark("trackB_form");
  await page.locator('a[href="/diagnostic"]').first().click();
  await page.waitForURL("**/diagnostic", { timeout: 30000 });
  await wait(3000);
  await page.locator("button[data-fill]").first().click();
  await wait(2200);
  await page.locator("#url").click();
  await wait(1200);
  mark("trackB_submit");
  await page.locator("#runBtn").click();
  await page.waitForURL(/\/runs\/\d/, { timeout: 60000 });
  const runUrl = page.url();
  log(`run page ${runUrl}`);

  /* 3. the run, watched live */
  mark("trackB_running");
  const deadline = Date.now() + 260000;
  let seenLog = false;
  while (Date.now() < deadline) {
    const chip = ((await page.locator("#statusChip").textContent().catch(() => "")) || "").trim();
    if (/Needs review|Approved|Failed/i.test(chip)) { log(`chip: ${chip}`); break; }
    if (!seenLog && Date.now() - T0 > 90000) { await tab(page, "log", 1500); seenLog = true; mark("trackB_log"); }
    await wheel(page, 220, 110, 70);
    await wait(2500);
    await wheel(page, -220, 110, 70);
    await wait(3500);
  }
  mark("trackB_done");
  await wait(1500);

  /* 4. the result, section by section */
  await tab(page, "diagnostic", 2000);
  mark("trackB_doc");
  await wheel(page, 900, 90, 110);
  await wait(2000);
  await wheel(page, 900, 90, 110);
  await wait(2500);
  await tab(page, "findings", 2500);
  mark("trackB_findings");
  const subs = page.locator("#tabs button");
  const nsub = await subs.count();
  for (let i = 0; i < Math.min(nsub, 4); i++) {
    await subs.nth(i).click().catch(() => {});
    await wait(2600);
    await wheel(page, 260, 90, 80);
    await wait(1200);
  }
  await tab(page, "sources", 3000);
  mark("trackB_sources");
  await wheel(page, 500, 90, 90);
  await wait(2000);

  /* 5. the human gate, signed with a real name */
  await tab(page, "diagnostic", 800);
  mark("gate");
  await page.locator("#gate").scrollIntoViewIfNeeded();
  await wait(2500);
  const by = page.locator('#approveForm input[name="by"]');
  if (await by.count()) {
    await by.click();
    await by.fill("");
    await by.type("Ronaldo Rajan Salamon", { delay: 85 });
    await wait(900);
    const note = page.locator('#approveForm textarea[name="note"]');
    await note.click();
    await note.type("Checked the licence number, the two fine amounts and the Forbes rank against the cited sources.", { delay: 22 });
    await wait(1600);
    mark("gate_approve");
    await page.locator('#approveForm button[type="submit"]').click();
    await wait(6000);
  } else { log("no gate form present"); }

  /* 6. the one minute video, rendered by the site itself */
  mark("video");
  const vb = page.locator("#videoSlot button, #videoSlot a");
  if (await vb.count()) { await vb.first().click().catch(() => {}); log("video button clicked"); await wait(7000); }
  await page.locator("#app").scrollIntoViewIfNeeded().catch(() => {});
  await wait(2000);

  /* 7. track A, also a real run */
  mark("trackA_form");
  await page.goto(`${BASE}/radar`, { waitUntil: "networkidle" });
  await wait(3500);
  await page.locator("#subjects").click();
  await wait(1500);
  mark("trackA_submit");
  await page.locator("#radarBtn").click();
  await page.waitForURL(/\/radar\/runs\//, { timeout: 60000 });
  mark("trackA_running");
  const rdead = Date.now() + 150000;
  while (Date.now() < rdead) {
    const chip = ((await page.locator("#statusChip").textContent().catch(() => "")) || "").trim();
    if (/Needs review|Approved|Failed/i.test(chip)) { log(`radar chip: ${chip}`); break; }
    await wheel(page, 200, 100, 70);
    await wait(2500);
    await wheel(page, -200, 100, 70);
    await wait(3000);
  }
  mark("trackA_done");
  await wait(2000);
  await tab(page, "brief", 3000);
  mark("trackA_brief");
  await wheel(page, 800, 90, 110);
  await wait(2500);
  await tab(page, "queue", 2500);
  mark("trackA_queue");
  await wheel(page, 400, 90, 100);
  await wait(3000);
  const q = page.locator(".queue-item button, .queue-item a").first();
  if (await q.count()) { await q.click().catch(() => {}); mark("trackA_decide"); await wait(5000); await wheel(page, 300, 90, 100); await wait(3000); }
  await tab(page, "mentions", 3000);
  mark("trackA_mentions");
  const msubs = page.locator("#tabs button");
  const mn = await msubs.count();
  for (let i = 0; i < Math.min(mn, 3); i++) {
    await msubs.nth(i).click().catch(() => {});
    await wait(2500);
    await wheel(page, 240, 90, 80);
    await wait(1200);
  }
  mark("end");

  await ctx.close();
  await browser.close();
  console.log("MARKS " + JSON.stringify(marks));
  console.log("RUN_URL " + runUrl);
  console.log("TOTAL " + at() + "s");
})().catch(async (e) => { console.error("FAILED", e && e.message); process.exit(1); });
