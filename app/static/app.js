"use strict";
// 서버가 보낸 글은 모두 textContent로만 넣는다(HTML로 해석하지 않음).
const $ = (id) => document.getElementById(id);
const EMDS = ["한림읍", "애월읍", "구좌읍", "조천읍", "한경면", "추자면", "우도면", "대정읍", "남원읍", "성산읍", "안덕면", "표선면"];
const WHY = { no_date: "날짜 없음", bad_date: "날짜 오류", long_event: "92일 넘는 장기 행사", short_event: "한 달 합계에 묻히는 짧은 행사",
  before_data: "행사 전 카드 자료 부족", diluted: "희석 주의" };
const TAG = { "AI 짐작": "ai", "조회": "ai", "검사": "code", "계산": "code", "잠금": "code", "대체 경로": "warn", "멈춤": "warn", "오류": "warn" };
let last = null;
let wantFiles = false;

async function api(method, path, body, raw) {
  const opt = { method, headers: {} };
  if (raw !== undefined) { opt.body = raw; }
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { alertLine(data.detail || "요청을 처리하지 못했습니다."); throw new Error(r.status); }
  return data;
}

function alertLine(text) {
  const li = document.createElement("li");
  li.append(span("t", "지금"), span("", ""));
  li.lastChild.append(tag("warn", "안내"), document.createTextNode(text));
  $("log").prepend(li);
}

function span(cls, text) { const s = document.createElement("span"); if (cls) s.className = cls; s.textContent = text; return s; }
function tag(kind, text) { const s = span("tag " + kind, text); return s; }
function pct(x) { return (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%"; }
function show(id) { for (const a of document.querySelectorAll(".area")) a.hidden = a.id !== id; }

function fillVisit(text, v) {
  return text.replace(/\{\{visit\.(R_T|R_C|V)\}\}/g, (_, k) => (v && v[k] !== null && v[k] !== undefined ? pct(v[k]) : "값 없음"));
}

function renderLog(log) {
  const ol = $("log");
  ol.textContent = "";
  for (const e of log.slice().reverse()) {
    const li = document.createElement("li");
    const body = span("", "");
    body.append(tag(TAG[e.kind] || "", e.kind), document.createTextNode(e.text));
    li.append(span("t", e.time), body);
    ol.append(li);
  }
}

function renderBand(s) {
  $("b-example").hidden = !s.example;
  $("b-ai").textContent = s.locked ? "외부 AI 연결: 잠김" : "외부 AI 연결: 열림";
  $("b-ai").className = "pill " + (s.locked ? "warn" : "ok");
  $("b-sent").textContent = "외부 전송 " + s.sent + "건";
  $("b-delete").textContent = "결과 자동 삭제: " + (s.auto_delete ? "켜짐" : "꺼짐");
  $("b-delete").dataset.on = s.auto_delete ? "1" : "";
  $("finish-text").textContent = s.auto_delete
    ? "작업 기록, 메모리의 센터 집계, 결과 폴더의 그림과 PDF를 지우고 처음 화면으로 돌아갑니다."
    : "작업 기록과 메모리의 센터 집계를 지웁니다. 결과 자동 삭제가 꺼져 있어 결과 폴더(app\\out\\report)의 그림과 PDF는 남깁니다.";
}

function renderPlace(s) {
  const ev = s.event;
  $("place-event").textContent = ev.name + " (" + ev.start + " ~ " + ev.end + ")";
  const sel = $("place-emd");
  if (!sel.options.length) for (const e of EMDS) sel.append(new Option(e, e));
  const guess = (window.placeGuess || {})[ev.event_id];
  if (guess) {
    $("place-guess").textContent = guess.place + (guess.spot ? " · " + guess.spot : "") + " (확신도 " + guess.confidence + ")";
    $("place-reason").textContent = guess.place_reason;
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
  if (!p) return;
  $("plan-origin").textContent = s.origin === "premade" ? "미리 만든 계획(" + p.model + ", " + p.created_at.slice(0, 10) + ")" : "AI가 방금 세운 계획(" + p.model + ")";
  $("plan-judgement").textContent = "방문 판단: " + p.judgement.visit.judgement;
  $("plan-reason").textContent = fillVisit(p.judgement.visit.reason, p.visit_summary);
  const kept = $("plan-kept"); kept.textContent = "";
  for (const k of p.kept) {
    const why = (p.judgement.kept.find((x) => x.emd === k) || {}).reason || "";
    const li = document.createElement("li"); li.append(span("", k + ": "), span("small", why)); kept.append(li);
  }
  const ex = $("plan-excluded"); ex.textContent = "";
  for (const x of p.judgement.extra_excluded) { const li = document.createElement("li"); li.append(tag("ai", "AI"), document.createTextNode(x.emd + ": " + x.reason)); ex.append(li); }
  for (const x of p.rule_excluded) { const li = document.createElement("li"); li.append(tag("code", "규칙"), document.createTextNode(x.emd + ": " + x.why + (x.name ? "(" + x.name + ")" : ""))); ex.append(li); }
  $("plan-biz").textContent = (p.plan.biz_codes.length ? p.plan.biz_codes.length + "개 업종. " : "42개 업종 전체. ") + p.plan.biz_reason;
}

function renderFiles(s) {
  const c = s.checklist;
  if (c) $("check-count").textContent = "필요한 달: 필수 " + c.required.length + "개, 평소 흔들림 계산용 " + c.for_sigma.length + "개, 모두 " + c.all.length + "개월";
  $("files-count").textContent = s.files ? s.files + "개 파일을 받았습니다." : "";
  $("btn-calc").disabled = !s.files || s.busy || s.stage === "computing";
  $("btn-calc").textContent = s.stage === "computing" ? "계산 중…" : "계산 시작";
}

function renderResult(s) {
  const r = s.summary;
  $("r-sentence").textContent = r.sentence;
  const t = Date.now();
  $("r-index").hidden = !r.images.includes("index.png");
  $("r-index").src = "/api/report/index.png?t=" + t;
  $("r-visit").hidden = !r.images.includes("visit.png");
  $("r-visit").src = "/api/report/visit.png?t=" + t;
  for (const [id, rows] of [["r-evidence", r.evidence], ["r-ai", r.ai]]) {
    const tb = $(id); tb.textContent = "";
    for (const [k, v] of rows) { const tr = document.createElement("tr"); tr.append(cell(k), cell(v)); tb.append(tr); }
  }
  $("r-method").textContent = r.method;
  const ul = $("r-limits"); ul.textContent = "";
  for (const l of r.limits) { const li = document.createElement("li"); li.textContent = l; ul.append(li); }
  $("r-pdf").href = "/api/report/" + r.pdf + "?t=" + t;
  $("r-usage").value = r.usage_reason;
}

function cell(text) { const td = document.createElement("td"); td.textContent = text; return td; }

function render(s) {
  renderBand(s); renderLog(s.log);
  const key = s.stage + "|" + s.files + "|" + (s.summary ? 1 : 0) + "|" + (s.plan ? 1 : 0) + "|" + s.busy + "|" + s.log.length;
  if (last === key) return;
  last = key;
  if (s.stage === "start") { show("a-start"); wantFiles = false; }
  else if (s.stage === "place") { show("a-place"); renderPlace(s); }
  else if (["thinking", "stopped"].includes(s.stage) || (s.stage === "ready" && !wantFiles)) { show("a-plan"); renderPlan(s); }
  else if (["ready", "files", "computing"].includes(s.stage)) { show("a-files"); renderFiles(s); }
  else if (s.stage === "done") { show("a-result"); renderResult(s); }
}

async function poll() {
  try { render(await api("GET", "/api/status")); } catch (e) { /* 서버가 잠시 바쁘면 다음 조회에서 다시 그린다 */ }
}

async function loadEvents() {
  const data = await api("GET", "/api/events");
  window.placeGuess = Object.fromEntries(data.events.map((e) => [e.event_id, e]));
  const tb = $("events"); tb.textContent = "";
  const onlyOk = $("only-ok").checked;
  for (const e of data.events) {
    const dong = !EMDS.includes(e.place) && e.place !== "모름";
    const usable = e.status !== "unavailable" && !dong;
    if (onlyOk && !usable) continue;
    const tr = document.createElement("tr");
    const can = e.status === "unavailable" ? "볼 수 없음: " + WHY[e.why] : dong ? "볼 수 없음: " + e.place + "(읍면만 지원)" : (e.status === "diluted" ? "희석 주의" : "볼 수 있음");
    const btn = document.createElement("button"); btn.textContent = "고르기"; btn.disabled = !usable;
    btn.onclick = () => api("POST", "/api/run", { event_id: e.event_id }).then(poll);
    const last = document.createElement("td"); last.append(btn);
    tr.append(cell(e.name), cell(e.start + " ~ " + e.end), cell(e.place + (e.spot ? " · " + e.spot : "")), cell(can), last);
    tb.append(tr);
  }
}

async function sendFiles(list) {
  for (const f of list) await api("PUT", "/api/files/" + encodeURIComponent(f.name), undefined, await f.arrayBuffer());
  poll();
}

$("btn-example").onclick = async () => { await loadEvents(); await api("POST", "/api/run", { example: "effect" }); poll(); };
$("btn-example-none").onclick = async (ev) => { ev.preventDefault(); await loadEvents(); await api("POST", "/api/run", { example: "none" }); poll(); };
$("btn-direct").onclick = async () => { $("events-wrap").hidden = false; await loadEvents(); };
$("only-ok").onchange = loadEvents;
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
$("btn-finish-cancel").onclick = () => $("d-finish").close();
$("btn-finish-ok").onclick = async () => { $("d-finish").close(); await api("POST", "/api/reset"); wantFiles = false; last = null; poll(); };
$("b-sent").onclick = async () => {
  const data = await api("GET", "/api/transmissions");
  const ol = $("sent-list"); ol.textContent = "";
  for (const e of data.entries) {
    const li = document.createElement("li");
    li.append(document.createTextNode(new Date(e.time * 1000).toLocaleTimeString() + " " + e.purpose + " " + e.status));
    if (e.request) {
      const d = document.createElement("details"); const sm = document.createElement("summary"); sm.textContent = "보낸 본문 펼치기";
      const pre = document.createElement("pre"); pre.textContent = JSON.stringify(e.request, null, 1).slice(0, 4000);
      pre.style.whiteSpace = "pre-wrap"; d.append(sm, pre); li.append(d);
    }
    ol.append(li);
  }
  $("d-sent").showModal();
};
$("b-delete").onclick = async () => { await api("POST", "/api/settings", { auto_delete: !$("b-delete").dataset.on }); poll(); };
$("btn-close-sent").onclick = () => $("d-sent").close();
$("btn-selfcheck").onclick = async () => {
  const ul = $("selfcheck-rows"); ul.textContent = "점검 중…";
  let data;
  try { data = await api("POST", "/api/selfcheck"); }
  catch (e) { ul.textContent = "지금은 점검할 수 없습니다. 계획·계산 중이거나 센터 파일을 넣은 상태라면 「끝내기」 뒤에 눌러 주세요."; return; }
  ul.textContent = "";
  for (const r of data.rows) { const li = document.createElement("li"); li.textContent = (r.ok ? "통과 " : "실패 ") + r.item + ": " + r.detail; ul.append(li); }
};

loadEvents().catch(() => {});
poll();
setInterval(poll, 1000);
