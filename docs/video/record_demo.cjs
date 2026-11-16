// 시연 영상 녹화: 앱 서버(127.0.0.1:18501)를 켠 채로 실행한다. 실제 AI를 한 번 쓴다(약 0.01달러).
// node docs/video/record_demo.cjs <playwright 모듈 경로>   → build/video/raw.webm, build/video/marks.json
// 그다음 node docs/video/edit_demo.cjs 가 AI 대기 구간을 빨리 감아 build/video/demo.mp4를 만든다.
// Playwright 영상 녹화는 자체 ffmpeg를 찾는다. 내려받지 않으려면 Homebrew ffmpeg를 잠깐 걸어 둔다:
//   mkdir -p ~/Library/Caches/ms-playwright/ffmpeg-1013 && ln -sf /opt/homebrew/bin/ffmpeg ~/Library/Caches/ms-playwright/ffmpeg-1013/ffmpeg-mac
const path = require("path");
const fs = require("fs");
const { chromium } = require(process.argv[2]);

const BASE = "http://127.0.0.1:18501";
const OUT = path.resolve(__dirname, "../../build/video");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  await fetch(BASE + "/api/reset", { method: "POST" });
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  const t0 = Date.now();
  const marks = {};
  const mark = (name) => { marks[name] = (Date.now() - t0) / 1000; };
  const status = async () => (await fetch(BASE + "/api/status")).json();
  const waitStage = async (stages, limit = 180) => {
    for (let i = 0; i < limit * 2; i++) { if (stages.includes((await status()).stage)) return; await sleep(500); }
    throw new Error("기다린 단계가 오지 않음: " + stages);
  };

  // 화면 아래 자막과 처음·끝 장면. 앱 코드는 건드리지 않고 녹화할 때만 덧씌운다.
  const caption = (text) => page.evaluate((t) => {
    let c = document.getElementById("__cap");
    if (!c) {
      c = document.createElement("div"); c.id = "__cap";
      Object.assign(c.style, { position: "fixed", left: "50%", bottom: "44px", transform: "translateX(-50%)", zIndex: 99999,
        background: "rgba(47,53,59,.94)", color: "#fff", padding: "16px 30px", borderRadius: "14px", maxWidth: "78%",
        font: '600 29px/1.45 "Apple SD Gothic Neo", "Malgun Gothic", sans-serif', textAlign: "center", boxShadow: "0 12px 30px rgba(0,0,0,.25)" });
      document.body.appendChild(c);
    }
    c.textContent = t; c.style.display = t ? "block" : "none";
  }, text);
  const card = (title, sub) => page.evaluate(([t, s]) => {
    let c = document.getElementById("__card");
    if (!c) {
      c = document.createElement("div"); c.id = "__card";
      Object.assign(c.style, { position: "fixed", inset: "0", zIndex: 100000, background: "#ffffff", display: "grid", placeContent: "center",
        textAlign: "center", gap: "24px", font: '400 30px/1.5 "Apple SD Gothic Neo", "Malgun Gothic", sans-serif', color: "#3e454c" });
      document.body.appendChild(c);
    }
    c.innerHTML = '<svg viewBox="0 0 28 20" width="168" height="120" style="margin:0 auto"><path d="M2 15 L10 13 L18 14 L26 12" fill="none" stroke="#8a939a" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="3 2"/><path d="M2 12 L10 10 L18 11 L26 3" fill="none" stroke="#ee7f1b" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const h = document.createElement("div"); h.textContent = t; Object.assign(h.style, { font: '700 64px/1.25 "Apple SD Gothic Neo", sans-serif', color: "#2f353b" });
    const p = document.createElement("div"); p.textContent = s;
    c.append(h, p); c.style.display = t ? "grid" : "none";
  }, [title, sub]);
  const scrollTo = async (selector, offset = 120, ms = 1600) => {
    await page.evaluate(([sel, off, dur]) => new Promise((done) => {
      const el = document.querySelector(sel); const from = scrollY;
      const to = Math.max(0, el.getBoundingClientRect().top + scrollY - off); const start = performance.now();
      const step = (now) => { const k = Math.min(1, (now - start) / dur); const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        scrollTo(0, from + (to - from) * e); k < 1 ? requestAnimationFrame(step) : done(); };
      requestAnimationFrame(step);
    }), [selector, offset, ms]);
  };

  await page.goto(BASE + "/");
  await card("행사 효과 나란히", "제주 읍면 축제의 관광 소비 효과를 비교 읍면과 나란히 계산하는 AI Agent");
  await sleep(4000);
  await card("", "");
  await page.evaluate(() => { const l = document.querySelector(".event-line"); if (l) { l.style.animation = "none"; l.getBoundingClientRect(); l.style.animation = ""; } });
  await caption("축제가 열린 읍면의 관광 소비가 비교 읍면보다 더 늘었는지 계산합니다");
  await sleep(4500);
  await caption("처음에는 「예시로 해 보기」로 센터 파일 없이 끝까지 해 볼 수 있습니다");
  await sleep(3500);
  await page.click("#btn-example");
  await page.waitForSelector("#a-place:not([hidden])");
  await caption("행사 파일에 장소 열이 없어, AI가 짐작한 개최 읍면을 사람이 확인합니다");
  await sleep(4500);
  await page.click("#btn-place");
  await caption("AI가 공개 유동인구를 직접 조회하며 계산 계획을 세웁니다. 센터 카드 데이터는 보지 않습니다");
  mark("think_start");
  await waitStage(["ready", "stopped"]);
  await sleep(1500);
  mark("think_end");
  await page.waitForSelector("#plan-body:not([hidden])");
  await caption("방문 판단과 이유. AI가 쓴 숫자는 입력과 대조해 근거가 있을 때만 받습니다");
  await sleep(4500);
  await scrollTo("#plan-kept", 140);
  await caption("비교 순서는 코드가 행사 전 유동인구 흐름으로 정하고, AI는 남긴 이유를 적습니다");
  await sleep(4000);
  await scrollTo("#plan-excluded", 140);
  await caption("규칙으로 뺀 읍면과, 같은 시기 다른 축제 때문에 AI가 더 뺀 읍면이 구분됩니다");
  await sleep(4500);
  await scrollTo("#plan-biz", 200);
  await caption("업종은 코드가 정해 둔 묶음 4개 가운데 행사 성격에 맞는 것을 AI가 고릅니다");
  await sleep(4000);
  await page.click("#btn-to-files");
  await page.waitForSelector("#a-files:not([hidden])");
  await page.evaluate(() => scrollTo(0, 0));
  await caption("받을 달을 알려 줍니다. 센터 파일을 넣는 순간 외부 연결이 잠깁니다");
  await sleep(4500);
  await page.click("#btn-example-files");
  await sleep(1500);
  await caption("위쪽 띠가 「AI 연결 끊김」으로 바뀌었습니다. 계산은 이 PC 안에서만 합니다");
  await sleep(4000);
  await page.click("#btn-calc");
  await waitStage(["done"], 60);
  await page.waitForSelector("#a-result:not([hidden])");
  await page.evaluate(() => scrollTo(0, 0));
  await caption("보고서는 결론부터 보여 줍니다. 비교 읍면보다 얼마나 더 늘었는지, 평소에도 생기는 차이인지");
  await sleep(6000);
  await scrollTo("#h-r2", 110, 1800);
  await caption("상황과 과제: 어떤 행사를, 어느 비교 읍면과, 어느 기간으로 비교했는지");
  await sleep(4500);
  await scrollTo("#h-r4", 110, 1800);
  await caption("방법: 증가율 비교, 행사 전 흐름 확인, 행사 없던 달과의 비교 세 단계");
  await sleep(5000);
  await scrollTo(".figures", 110, 1800);
  await caption("주황 실선이 행사 읍면, 회색 점선이 비교 읍면, 노란 띠가 행사 달입니다");
  await sleep(6000);
  await scrollTo("#h-r6", 110, 1800);
  await caption("원래 금액·건수 없이 증가율과 지수만 담고, 반출 신청용 활용 사유까지 만듭니다");
  await sleep(5500);
  await page.evaluate(() => scrollTo(0, 0));
  await page.click("#b-sent");
  await caption("밖으로 보낸 요청은 모두 기록에 남고, 보낸 본문을 그대로 펼쳐 볼 수 있습니다");
  await sleep(5000);
  await page.click("#btn-close-sent");
  await scrollTo("#btn-finish", 400, 1200);
  await page.click("#btn-finish");
  await caption("「끝내기」는 센터 집계와 기록을 지우고 처음 화면으로 돌아갑니다");
  await sleep(3500);
  await page.click("#btn-finish-ok");
  await waitStage(["start"], 20);
  await sleep(1000);
  await page.click("#b-sent");
  await page.click("#btn-selfcheck");
  await caption("자가 점검: 표시값을 심은 가상 파일로 끝까지 돌려, 잠근 뒤 외부 전송 0건 등 7개 항목을 확인합니다");
  await page.waitForFunction(() => document.querySelectorAll("#selfcheck-rows li").length >= 7, null, { timeout: 60000 });
  await page.evaluate(() => { const d = document.querySelector("#d-sent"); d.scrollTop = d.scrollHeight; });
  await sleep(6000);
  await page.click("#btn-close-sent");
  await caption("");
  await card("행사 효과 나란히", "AI는 계획만, 계산은 잠긴 PC 안에서. 센터 값 외부 전송 0건");
  await sleep(4500);
  mark("end");

  const video = page.video();
  await context.close();
  await browser.close();
  fs.renameSync(await video.path(), path.join(OUT, "raw.webm"));
  fs.writeFileSync(path.join(OUT, "marks.json"), JSON.stringify(marks, null, 1));
  console.log("녹화 끝", marks);
})().catch((e) => { console.error(e); process.exit(1); });
