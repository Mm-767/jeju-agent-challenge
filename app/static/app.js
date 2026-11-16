"use strict";
// 서버가 보낸 글은 모두 textContent로만 넣는다(HTML로 해석하지 않음).
const $ = (id) => document.getElementById(id);
const EMDS = ["한림읍", "애월읍", "구좌읍", "조천읍", "한경면", "추자면", "우도면", "대정읍", "남원읍", "성산읍", "안덕면", "표선면"];
const WHY = { no_date: "날짜 없음", bad_date: "날짜 오류", long_event: "92일 넘는 장기 행사", short_event: "한 달 합계에 묻히는 짧은 행사",
  before_data: "행사 전 카드 자료 부족", diluted: "희석 주의" };
// 작업 기록 표시: AI가 한 일은 기본, 코드가 한 일은 테두리, 주의는 먹색(ink 테마는 두 번째 색을 쓰지 않는다)
const KIND = { "AI 짐작": "", "조회": "", "검사": "tag--out", "계산": "tag--out", "잠금": "tag--out", "확인": "tag--out",
  "대체 경로": "tag--on", "멈춤": "tag--on", "오류": "tag--on", "안내": "tag--on" };
let last = null;
let wantFiles = false;
let events = [];

async function api(method, path, body, raw) {
  const opt = { method, headers: {} };
  if (raw !== undefined) { opt.body = raw; }
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { alertLine(data.detail || "요청을 처리하지 못했습니다."); throw new Error(r.status); }
  return data;
}

function el(name, cls, text) { const e = document.createElement(name); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function tag(kind, text) { return el("span", "tag " + (kind || ""), text); }
function pct(x) { return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%"; }
function show(id) { for (const a of document.querySelectorAll("main > .area")) a.hidden = a.id !== id; }
function cell(text) { return el("td", "", text); }

function logItem(time, kind, text) {
  const li = el("li");
  const body = el("span");
  body.append(tag("k " + (KIND[kind] ?? ""), kind), document.createTextNode(text));
  li.append(el("span", "t", time), body);
  return li;
}

function alertLine(text) { $("log").prepend(logItem("지금", "안내", text)); }

function fillVisit(text, v) {
  return text.replace(/\{\{visit\.(R_T|R_C|V)\}\}/g, (_, k) => (v && v[k] !== null && v[k] !== undefined ? pct(v[k]) : "값 없음"));
}

function setStep(n) {
  for (const li of document.querySelectorAll("#steps li")) {
    const k = Number(li.dataset.step);
    li.classList.toggle("done", k < n);
    if (k === n) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
  }
}

function renderLog(log) {
  const ol = $("log");
  ol.textContent = "";
  if (!log.length) { const li = el("li"); li.append(el("span", "empty", "아직 기록이 없습니다. 「예시로 해 보기」나 「직접 분석하기」로 시작하세요.")); ol.append(li); return; }
  for (const e of log.slice().reverse()) ol.append(logItem(e.time, e.kind, e.text));
}

function renderBand(s) {
  $("b-example").hidden = !s.example;
  $("b-ai").textContent = s.locked ? "외부 AI 연결 잠김" : "외부 AI 연결 열림";
  $("b-ai").className = "tag " + (s.locked ? "tag--on" : "tag--in");
  $("b-sent").textContent = "외부 전송 " + s.sent + "건";
  $("b-delete").textContent = "결과 자동 삭제 " + (s.auto_delete ? "켜짐" : "꺼짐");
  $("b-delete").dataset.on = s.auto_delete ? "1" : "";
  $("b-delete").setAttribute("aria-pressed", s.auto_delete ? "true" : "false");
  $("finish-text").textContent = s.auto_delete
    ? "작업 기록, 메모리의 센터 집계, 결과 폴더의 그림과 PDF를 지우고 처음 화면으로 돌아갑니다."
    : "작업 기록과 메모리의 센터 집계를 지웁니다. 결과 자동 삭제가 꺼져 있어 결과 폴더(app\\out\\report)의 그림과 PDF는 남깁니다.";
}

function renderPlace(s) {
  const ev = s.event;
  $("place-event").textContent = ev.name + ", " + ev.start + " ~ " + ev.end;
  const sel = $("place-emd");
  if (!sel.options.length) for (const e of EMDS) sel.append(new Option(e, e));
  const guess = events.find((e) => e.event_id === ev.event_id);
  if (guess) {
    $("place-guess").textContent = guess.place + (guess.spot ? ", " + guess.spot : "");
    $("place-reason").textContent = (guess.place_reason ? guess.place_reason + " " : "") + "확신도 " + guess.confidence + ".";
    if (EMDS.includes(guess.place)) sel.value = guess.place;
  }
  sel.disabled = !!s.example;
  if (s.example) sel.value = "대정읍";
}

function renderPlan(s) {
  const p = s.plan;
  $("plan-wait").hidden = s.stage !== "thinking";
  $("plan-stopped").hidden = s.stage !== "stopped";
  $("plan-body").hidden = !p;
  const latest = s.log.filter((e) => ["조회", "검사"].includes(e.kind)).pop();
  $("plan-latest").textContent = latest ? "지금: " + latest.text : "";
  if (!p) return;
  $("plan-origin").textContent = s.origin === "premade" ? "미리 만든 계획, " + p.model + ", " + p.created_at.slice(0, 10) : "AI가 방금 세운 계획, " + p.model;
  $("plan-origin").className = "tag " + (s.origin === "premade" ? "tag--out" : "");
  $("plan-judgement").textContent = "방문 판단 " + p.judgement.visit.judgement;
  $("plan-reason").textContent = fillVisit(p.judgement.visit.reason, p.visit_summary);
  const kept = $("plan-kept"); kept.textContent = "";
  p.kept.forEach((k, i) => {
    const why = (p.judgement.kept.find((x) => x.emd === k) || {}).reason || "";
    const li = el("li", "block"); li.append(el("strong", "", (i + 1) + "순위 " + k), el("span", "small", why)); kept.append(li);
  });
  const ex = $("plan-excluded"); ex.textContent = "";
  for (const x of p.judgement.extra_excluded) { const li = el("li"); li.append(tag("", "AI"), document.createTextNode(" " + x.emd + ": " + x.reason)); ex.append(li); }
  for (const x of p.rule_excluded) { const li = el("li"); li.append(tag("tag--out", "규칙"), document.createTextNode(" " + x.emd + ": " + x.why + (x.name ? "(" + x.name + ")" : ""))); ex.append(li); }
  if (!ex.children.length) ex.append(el("li", "small", "뺀 읍면이 없습니다."));
  $("plan-biz").textContent = (p.plan.biz_bundle || "AI가 고른 업종") + "(" + (p.plan.biz_codes.length || 42) + "개 업종). " + p.plan.biz_reason;
}

function pairs(dl, rows) {
  dl.textContent = "";
  for (const [k, v] of rows) { const d = el("div"); d.append(el("dt", "", k), el("dd", "", v)); dl.append(d); }
}

function renderFiles(s) {
  const c = s.checklist;
  if (c) pairs($("check-count"), [["필수 달", c.required.length + "개"], ["평소 흔들림 계산용", c.for_sigma.length + "개"], ["모두", c.all.length + "개월"]]);
  $("files-count").textContent = s.files ? s.files + "개 파일을 받았습니다. 외부 연결이 잠겼습니다." : "아직 넣은 파일이 없습니다.";
  const computing = s.stage === "computing";
  $("btn-calc").disabled = !s.files || s.busy || computing;
  $("btn-calc").setAttribute("aria-busy", computing ? "true" : "false");
  $("btn-calc").textContent = computing ? "계산 중…" : "계산 시작";
}

function rowsTable(tb, rows) {
  tb.textContent = "";
  for (const [k, v] of rows) { const tr = el("tr"); tr.append(cell(k), cell(v)); tb.append(tr); }
}

function bullets(ul, lines, empty) {
  ul.textContent = "";
  for (const l of lines) ul.append(el("li", "", l));
  if (!lines.length && empty) ul.append(el("li", "", empty));
}

function renderResult(s) {
  const r = s.summary;
  const rep = r.report;
  const t = Date.now();
  $("r-title").textContent = s.event.name + " 관광객 카드 소비 비교" + (s.example ? " (예시, 가상 데이터)" : "");
  $("r-verdict").textContent = rep.label;
  $("r-verdict").className = "tag " + ({ higher: "tag--in", lower: "tag--in", not_computed: "tag--out" }[rep.outcome] || "");
  $("r-headline").textContent = rep.headline;
  $("r-sentence").textContent = rep.sentence;
  pairs($("r-figures"), rep.figures);
  $("r-figures").hidden = !rep.figures.length;
  pairs($("r-situation"), rep.situation);
  pairs($("r-task"), rep.task);
  $("r-method").textContent = rep.method_ai;
  const steps = $("r-steps"); steps.textContent = "";
  for (const [k, v] of rep.steps) { const li = el("li"); li.append(el("strong", "", k), el("span", "", v)); steps.append(li); }
  rowsTable($("r-ai"), rep.ai);
  rowsTable($("r-evidence"), rep.evidence);
  for (const [id, name] of [["r-index", "index.png"], ["r-visit", "visit.png"]]) {
    const img = $(id);
    img.closest("figure").hidden = !r.images.includes(name);
    img.src = "/api/report/" + name + "?t=" + t;
  }
  bullets($("r-limits"), rep.limits_event, "이 행사만의 주의점은 없습니다.");
  bullets($("r-limits-common"), rep.limits_common);
  $("r-pdf").href = "/api/report/" + r.pdf + "?t=" + t;
  $("r-usage").value = r.usage_reason;
  $("btn-copy").textContent = "활용 사유 복사";
}

function render(s) {
  renderBand(s); renderLog(s.log);
  const key = s.stage + "|" + s.files + "|" + (s.summary ? 1 : 0) + "|" + (s.plan ? 1 : 0) + "|" + s.busy + "|" + s.log.length + "|" + wantFiles;
  if (last === key) return;
  last = key;
  if (s.stage === "start") { show("a-start"); setStep(1); wantFiles = false; }
  else if (s.stage === "place") { show("a-place"); setStep(2); renderPlace(s); }
  else if (["thinking", "stopped"].includes(s.stage) || (s.stage === "ready" && !wantFiles)) { show("a-plan"); setStep(3); renderPlan(s); }
  else if (["ready", "files", "computing"].includes(s.stage)) { show("a-files"); setStep(4); renderFiles(s); }
  else if (s.stage === "done") { show("a-result"); setStep(5); renderResult(s); }
}

async function poll() {
  try { render(await api("GET", "/api/status")); } catch (e) { /* 서버가 잠시 바쁘면 다음 조회에서 다시 그린다 */ }
}

function stateTag(e, dong) {
  if (e.status === "unavailable") return tag("tag--out", "볼 수 없음: " + WHY[e.why]);
  if (dong) return tag("tag--out", "볼 수 없음: 동 지역");
  return e.status === "diluted" ? tag("", "희석 주의") : tag("tag--in", "볼 수 있음");
}

function drawEvents() {
  const tb = $("events"); tb.textContent = "";
  const onlyOk = $("only-ok").checked;
  const q = $("ev-q").value.trim();
  let shown = 0;
  for (const e of events) {
    const dong = !EMDS.includes(e.place) && e.place !== "모름";
    const usable = e.status !== "unavailable" && !dong;
    if ((onlyOk && !usable) || (q && !e.name.includes(q))) continue;
    const tr = el("tr");
    const btn = el("button", "btn btn--s", "고르기"); btn.type = "button"; btn.disabled = !usable;
    btn.setAttribute("aria-label", e.name + " 고르기");
    btn.onclick = () => api("POST", "/api/run", { event_id: e.event_id }).then(poll);
    const pick = el("td"); pick.append(btn);
    const state = el("td"); state.append(stateTag(e, dong));
    tr.append(cell(e.name), el("td", "period", e.start + " ~ " + e.end), cell(e.place + (e.spot ? ", " + e.spot : "")), state, pick);
    tb.append(tr);
    shown += 1;
  }
  $("events-empty").hidden = shown > 0;
}

async function loadEvents() {
  events = (await api("GET", "/api/events")).events;
  drawEvents();
}

async function sendFiles(list) {
  for (const f of list) await api("PUT", "/api/files/" + encodeURIComponent(f.name), undefined, await f.arrayBuffer());
  poll();
}

$("btn-example").onclick = async () => { await loadEvents(); await api("POST", "/api/run", { example: "effect" }); poll(); };
$("btn-example-none").onclick = async (ev) => { ev.preventDefault(); await loadEvents(); await api("POST", "/api/run", { example: "none" }); poll(); };
$("btn-direct").onclick = async () => { $("events-wrap").hidden = false; await loadEvents(); $("ev-q").focus(); };
$("only-ok").onchange = drawEvents;
$("ev-q").oninput = drawEvents;
$("btn-place").onclick = async () => { await api("POST", "/api/place", { emd: $("place-emd").value }); poll(); };
$("btn-to-files").onclick = () => { wantFiles = true; last = null; poll(); };
$("btn-example-files").onclick = async () => { await api("POST", "/api/files/example"); poll(); };
$("file-input").onchange = (ev) => sendFiles(ev.target.files);
const drop = $("drop");
drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove("over"); sendFiles(ev.dataTransfer.files); };
$("btn-calc").onclick = async () => { await api("POST", "/api/calculate"); poll(); };
$("btn-copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("r-usage").value); $("btn-copy").textContent = "복사했습니다"; }
  catch (e) { $("r-usage").select(); }
};
$("btn-finish").onclick = () => $("d-finish").showModal();
$("btn-stop-finish").onclick = () => $("d-finish").showModal();
$("btn-finish-cancel").onclick = () => $("d-finish").close();
$("btn-finish-ok").onclick = async () => { $("d-finish").close(); await api("POST", "/api/reset"); wantFiles = false; last = null; poll(); };
$("b-sent").onclick = async () => {
  const data = await api("GET", "/api/transmissions");
  const ol = $("sent-list"); ol.textContent = "";
  for (const e of data.entries) {
    const li = el("li");
    const head = el("span"); head.append(document.createTextNode(new Date(e.time * 1000).toLocaleTimeString() + " " + e.purpose + " "), tag(e.status === "sent" ? "" : "tag--out", e.status));
    li.append(head);
    if (e.request) {
      const d = el("details"); d.append(el("summary", "", "보낸 본문 펼치기"), el("pre", "", JSON.stringify(e.request, null, 1).slice(0, 4000)));
      li.append(d);
    }
    ol.append(li);
  }
  if (!data.entries.length) ol.append(el("li", "", "아직 밖으로 보낸 요청이 없습니다."));
  $("d-sent").showModal();
};
$("b-delete").onclick = async () => { await api("POST", "/api/settings", { auto_delete: !$("b-delete").dataset.on }); poll(); };
$("btn-close-sent").onclick = () => $("d-sent").close();
$("btn-selfcheck").onclick = async () => {
  const ul = $("selfcheck-rows"); ul.textContent = "";
  ul.append(el("li", "", "점검 중…"));
  let data;
  try { data = await api("POST", "/api/selfcheck"); }
  catch (e) { ul.textContent = ""; ul.append(el("li", "", "지금은 점검할 수 없습니다. 계획·계산 중이거나 센터 파일을 넣은 상태라면 「끝내기」 뒤에 눌러 주세요.")); return; }
  ul.textContent = "";
  for (const r of data.rows) { const li = el("li"); li.append(tag(r.ok ? "tag--in" : "tag--on", r.ok ? "통과" : "실패"), document.createTextNode(" " + r.item + ": " + r.detail)); ul.append(li); }
};

loadEvents().catch(() => {});
poll();
setInterval(poll, 1000);
