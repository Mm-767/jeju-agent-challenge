import datetime as dt
import json
import shutil
import sys
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import calc
import card
import config
import egress
import hub
import pipeline
import selfcheck

BASE = Path(__file__).parent
# 8501은 Streamlit 기본 포트라 다른 참가작과 겹칠 수 있다
PORTS = range(18501, 18511)
EXAMPLE_EVENT = "363"  # 가파도청보리축제(대정읍), 미리 만든 계획이 있는 예시 행사
EXAMPLE_EMD = "대정읍"

app = FastAPI(title="행사 효과 나란히")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

_lock = threading.Lock()
state = {}


SETTINGS = config.OUT / "settings.json"


def _load_settings():
    # 다시 켤 때도 지난 선택을 따라야, 끄고 남긴 결과가 시작 때 reset()으로 지워지지 않는다
    try:
        return {"auto_delete": bool(json.loads(SETTINGS.read_text(encoding="utf-8")).get("auto_delete", True))}
    except (OSError, ValueError):
        return {"auto_delete": True}


settings = _load_settings()  # 센터 요구: 결과 삭제 기능 켜기·끄기(끄면 결과 그림·PDF를 남긴다)


def reset():
    """끝내기: 메모리의 센터 집계와 작업 기록을 지우고 잠금을 푼다. 결과 자동 삭제가 켜져 있으면 결과 파일도 지운다."""
    with _lock:
        state.clear()
        state.update({"stage": "start", "busy": False, "log": [], "event": None, "emd": None, "example": None,
                      "bundle": None, "origin": None, "files": [], "summary": None, "error": None})
    if settings["auto_delete"]:
        shutil.rmtree(config.OUT / "report", ignore_errors=True)
    (config.OUT / "work" / "transmissions.jsonl").unlink(missing_ok=True)  # 끝내기는 외부 전송 기록도 지운다
    egress.unlock()


reset()


def log(kind, text):
    state["log"].append({"time": dt.datetime.now().strftime("%H:%M:%S"), "kind": kind, "text": text})


def _events():
    places = hub.load_places()
    out = []
    for e in hub.load_events():
        status, why = calc.feasibility(e["start"], e["end"])
        if not e["start"] or not hub.FIRST_DAY <= e["start"] <= hub.LAST_DAY:
            continue
        p = places.get(e["event_id"], {})
        out.append({"event_id": e["event_id"], "name": e["name"], "start": str(e["start"]), "end": str(e["end"]),
                    "status": status, "why": why, "place": p.get("place", "모름"), "spot": p.get("spot", ""),
                    "confidence": p.get("confidence", "낮음"), "place_reason": p.get("reason", "")})
    return out


def _guard(locked_ok=False):
    if state["busy"]:
        raise HTTPException(409, "앞의 작업이 끝나지 않았습니다.")
    if not locked_ok and egress.is_locked():
        raise HTTPException(409, "센터 파일을 넣은 뒤에는 AI 단계로 돌아갈 수 없습니다. 끝내기 뒤 다시 시작해 주세요.")


def _background(target):
    state["busy"] = True

    def run():
        try:
            target()
        except Exception as e:  # 화면에는 셀 값이 섞일 수 있는 예외 문구를 보이지 않는다
            state["error"] = type(e).__name__
            log("오류", f"작업을 끝내지 못했습니다({type(e).__name__}).")
        finally:
            state["busy"] = False

    threading.Thread(target=run, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "app": egress.APP_MARK}


@app.get("/api/events")
def events():
    return {"events": _events(), "has_key": bool(config.env("ANTHROPIC_API_KEY"))}


@app.post("/api/run")
async def run(request: Request):
    _guard()
    body = await request.json()
    example = body.get("example")
    event_id = EXAMPLE_EVENT if example else body.get("event_id")
    event = next((e for e in hub.load_events() if e["event_id"] == event_id), None)
    if event is None:
        raise HTTPException(404, "행사를 찾지 못했습니다.")
    reset()
    state.update({"stage": "place", "event": event, "example": example})
    p = hub.load_places().get(event_id, {})
    log("AI 짐작", f"장소 추정표: {p.get('place', '모름')}({p.get('spot', '')}, 확신도 {p.get('confidence', '낮음')})")
    return {"ok": True}


@app.post("/api/place")
async def place(request: Request):
    _guard()
    body = await request.json()
    emd = EXAMPLE_EMD if state["example"] else body.get("emd")
    if emd not in hub.EUP_MYEON:
        raise HTTPException(400, "읍면 12곳 가운데 하나를 골라 주세요. 동 지역 행사는 지원하지 않습니다.")
    state.update({"emd": emd, "stage": "thinking"})
    # 읍면 12곳 이름은 모두 받침(읍·면)으로 끝나 "으로"
    log("확인", f"이용자가 개최 읍면을 {emd}으로 확인했습니다.")
    event = state["event"]

    def work():
        if not config.env("ANTHROPIC_API_KEY"):
            origin, bundle, why = "premade", pipeline.premade(event["event_id"]), "no_key"
        else:
            origin, bundle, why = pipeline.public_stage(event, emd, egress.call_llm, log, _rehearsal_table())
        if bundle is None:
            state["stage"] = "stopped"
            log("멈춤", f"계산 계획을 세우지 못했습니다({why}). 미리 만든 계획도 없는 행사입니다.")
            return
        if origin == "premade":
            log("대체 경로", f"미리 만든 계획을 씁니다({why}). 모델 {bundle['model']}, 만든 날 {bundle['created_at'][:10]}.")
        state.update({"bundle": bundle, "origin": origin, "stage": "ready"})

    _background(work)
    return {"ok": True}


_rehearsal = {}


def _rehearsal_table():
    if "table" not in _rehearsal:
        table = card.new_table()
        for f in sorted((BASE / "data" / "dummy" / "card_rehearsal").glob("*.csv")):
            card.ingest(f.read_bytes(), f.name, table)
        _rehearsal["table"] = table
    return _rehearsal["table"]


@app.put("/api/files/{name}")
async def put_file(name: str, request: Request):
    _guard(locked_ok=True)
    if state["stage"] not in ("ready", "files"):
        raise HTTPException(409, "계산 계획이 준비된 뒤에 파일을 넣을 수 있습니다.")
    egress.lock()  # 센터 형식 파일을 받기 직전에 잠근다
    state["files"].append((name, await request.body()))
    state["stage"] = "files"
    log("잠금", "센터 파일을 받아 외부 연결을 잠갔습니다.")
    return {"ok": True, "count": len(state["files"])}


@app.post("/api/files/example")
def example_files():
    _guard(locked_ok=True)
    if state["stage"] not in ("ready", "files"):
        raise HTTPException(409, "계산 계획이 준비된 뒤에 파일을 넣을 수 있습니다.")
    egress.lock()
    variant = "card_none" if state["example"] == "none" else "card_effect"
    state["files"] = [(f.name, f.read_bytes()) for f in sorted((BASE / "data" / "dummy" / variant).glob("*.csv"))]
    state["example"] = state["example"] or "effect"
    state["stage"] = "files"
    log("잠금", f"동봉한 가상 데이터 {len(state['files'])}개월을 넣고 외부 연결을 잠갔습니다.")
    return {"ok": True, "count": len(state["files"])}


@app.post("/api/calculate")
def calculate():
    _guard(locked_ok=True)
    if state["stage"] != "files":
        raise HTTPException(409, "센터 파일을 먼저 넣어 주세요.")
    state["stage"] = "computing"

    def work():
        summary = pipeline.center_stage(state["bundle"], state["files"], example=bool(state["example"]))
        state["files"] = []  # 메모리의 원본 파일 바이트는 계산 뒤 바로 버린다
        state.update({"summary": summary, "stage": "done"})
        log("계산", f"이 PC 안에서 계산을 마쳤습니다. 결과: {summary['outcome']}.")

    _background(work)
    return {"ok": True}


@app.get("/api/status")
def status():
    b = state["bundle"]
    return {
        "stage": state["stage"], "busy": state["busy"], "locked": egress.is_locked(), "log": state["log"][-50:],
        "event": state["event"] and {k: str(v) for k, v in state["event"].items()}, "emd": state["emd"],
        "example": state["example"], "origin": state["origin"], "error": state["error"],
        "plan": b and {k: b[k] for k in ("judgement", "kept", "plan", "texts", "ranked", "rule_excluded", "visit_summary", "model", "created_at")},
        "files": len(state["files"]), "summary": state["summary"], "checklist": _checklist(b),
        "sent": sum(1 for e in _transmissions() if e.get("status") == "sent"), "auto_delete": settings["auto_delete"],
    }


def _checklist(bundle):
    if not bundle:
        return None
    ev = bundle["event"]
    months = calc.months_for(dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"]),
                             set(bundle["festival_months"].get(ev["emd"], [])))
    need = calc.required_months(months)
    return {"required": need["required"], "for_sigma": need["for_sigma"], "all": need["all"]}


def _transmissions():
    path = config.OUT / "work" / "transmissions.jsonl"
    if not path.exists():
        return []
    import json

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@app.get("/api/transmissions")
def transmissions():
    return {"entries": _transmissions()[-30:]}


@app.get("/api/report/{name}")
def report_file(name: str):
    path = config.OUT / "report" / Path(name).name
    if path.suffix not in (".png", ".pdf") or not path.exists():
        raise HTTPException(404, "파일이 없습니다.")
    return FileResponse(path)


@app.post("/api/selfcheck")
def run_selfcheck():
    _guard()
    bundle = state["bundle"] or pipeline.premade(EXAMPLE_EVENT)
    rows = selfcheck.run(bundle)
    return {"rows": [{"item": i, "ok": ok, "detail": d} for i, ok, d in rows]}


@app.post("/api/settings")
async def change_settings(request: Request):
    body = await request.json()
    settings["auto_delete"] = bool(body.get("auto_delete", True))
    config.out_path(SETTINGS.name).write_text(json.dumps(settings), encoding="utf-8")
    return settings


@app.post("/api/reset")
def finish():
    if state["busy"]:
        raise HTTPException(409, "앞의 작업이 끝나지 않았습니다.")
    reset()
    return {"ok": True}


def disable_quick_edit():
    # 윈도우 콘솔에서 글자를 마우스로 선택하면 서버가 멈춘다
    if sys.platform != "win32":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, (mode.value | 0x80) & ~0x40)


def open_when_ready(server, url):
    while not server.started:
        time.sleep(0.1)
    print(f"브라우저에서 {url} 이 열립니다. 이 창을 닫으면 프로그램이 끝납니다.", flush=True)
    webbrowser.open(url)


def main():
    import uvicorn

    disable_quick_edit()
    running = next((p for p in PORTS if egress.local_app_running(p)), None)
    if running:
        print("이미 실행 중입니다. 브라우저만 엽니다.", flush=True)
        webbrowser.open(f"http://127.0.0.1:{running}/")
        return 3
    port = next((p for p in PORTS if egress.port_free(p)), None)
    if port is None:
        print(f"포트 {PORTS.start}~{PORTS.stop - 1}을 모두 다른 프로그램이 쓰고 있습니다.", flush=True)
        return 1
    # 127.0.0.1만 연다: 모든 주소에 열면 윈도우 방화벽 창이 뜬다
    config_ = uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")
    server = uvicorn.Server(config_)
    threading.Thread(target=open_when_ready, args=(server, f"http://127.0.0.1:{port}/"), daemon=True).start()
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
