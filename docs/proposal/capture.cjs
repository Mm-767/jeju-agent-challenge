// 기획서 캡처 다시 찍기: 앱 서버(127.0.0.1:18501)를 켠 채로 실행한다. 실제 AI를 한 번 쓴다.
// node docs/proposal/capture.cjs <playwright 모듈 경로>  → docs/proposal/img/*.png (PDF 두 장은 pdftoppm으로 따로)
const path = require("path");
const fs = require("fs");
const { chromium } = require(process.argv[2]);
const BASE = "http://127.0.0.1:18501";
const IMG = path.resolve(__dirname, "img");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  await fetch(BASE + "/api/reset", { method: "POST" });
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 860 }, reducedMotion: "reduce" })).newPage();
  const status = async () => (await fetch(BASE + "/api/status")).json();
  const waitStage = async (stages) => {
    for (let i = 0; i < 360; i++) { const s = await status(); if (!s.busy && stages.includes(s.stage)) return; await sleep(500); }
    throw new Error("기다린 단계가 오지 않음: " + stages);
  };
  const settle = async () => { await page.reload(); await sleep(1500); };
  const thumb = async (name) => {
    await page.evaluate(() => { document.documentElement.style.zoom = 1; scrollTo(0, 0); });
    await page.screenshot({ path: path.join(IMG, name + ".png"), scale: "css" });
  };
  const clip = (name, sel, w, h, dy = 0) => page.locator(sel).first().boundingBox().then((b) =>
    page.screenshot({ path: path.join(IMG, name + ".png"), scale: "css", clip: { x: b.x, y: b.y + dy, width: w || b.width, height: h } }));

  await page.goto(BASE + "/"); await sleep(2500);
  await thumb("t1");
  await page.click("#btn-example"); await sleep(1200);
  await thumb("t2"); await clip("p4-place", "#a-place", 832, 470);
  await page.click("#btn-place"); await waitStage(["ready"]); await settle();
  await thumb("t3"); await clip("p4-plan", "#a-plan", 832, 617); await clip("p4-log", ".log-wrap", 0, 490);
  await page.click("#b-sent"); await sleep(600);
  await page.locator("#sent-list details summary").first().click().catch(() => {}); await sleep(300);
  await clip("p10-sent", "#d-sent", 0, 504);
  await page.click("#btn-close-sent");
  await page.click("#btn-to-files"); await sleep(800);
  await thumb("t4");
  await page.click("#btn-example-files"); await sleep(800);
  await page.click("#btn-calc"); await waitStage(["done"]); await settle();
  await thumb("t5"); await clip("p1-result", "#a-result", 832, 475, 120);
  const s = await status();
  for (const name of [...s.summary.images, s.summary.pdf]) {
    const buf = Buffer.from(await (await fetch(BASE + "/api/report/" + name)).arrayBuffer());
    fs.writeFileSync(path.join(name.endsWith(".pdf") ? path.resolve(__dirname, "../../build") : IMG, name), buf);
  }
  console.log("pdf", s.summary.pdf);
  await browser.close();
})();
