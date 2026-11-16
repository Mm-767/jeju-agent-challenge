"""윈도우 자동 시험. 압축을 푼 묶음 폴더에서 이용자가 하는 순서를 그대로 밟는다.

python\\python.exe -X utf8 win_smoke.py <묶음 폴더> <결과 복사 폴더>
키 없이 돌리므로 계획은 「미리 만든 계획」으로 나와야 한다.
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
SAVE = Path(sys.argv[2]).resolve()
SAVE.mkdir(parents=True, exist_ok=True)
PORTS = range(18501, 18511)
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)
    if not ok:
        failures.append(name)


def bat(name, timeout):
    # pause는 빈 입력으로 넘긴다
    r = subprocess.run(["cmd", "/c", name], cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


print(f"묶음 폴더: {ROOT}", flush=True)
out = bat("install.bat", 900)
report = ROOT / "app" / "out" / "install_check.txt"
text = report.read_text(encoding="utf-8") if report.exists() else out
print(text, flush=True)
(SAVE / "install_check.txt").write_text(text, encoding="utf-8")
check("install.bat 설치 점검 모두 통과", "모두 통과했습니다." in text)

log = open(SAVE / "server.log", "wb")
server = subprocess.Popen(["cmd", "/c", "run.bat"], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
base = None
for _ in range(240):
    for port in PORTS:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
            base = f"http://127.0.0.1:{port}"
            break
        except Exception:
            pass
    if base:
        break
    time.sleep(0.5)
check("run.bat 서버 응답", base is not None, base or "")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data, {"content-type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def wait(stages, limit=600):
    for _ in range(limit):
        s = call("GET", "/api/status")
        if not s["busy"] and (s["stage"] in stages or s["error"]):
            return s
        time.sleep(0.5)
    return s


BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def shot(name, height=1080):
    """센터 PC와 같은 윈도우 글꼴(맑은 고딕)로 그린 화면을 남긴다. 판정에는 넣지 않는다."""
    exe = next((b for b in BROWSERS if Path(b).exists()), None)
    if exe is None:
        print("화면 캡처: 브라우저 없음")
        return
    import tempfile
    out = SAVE / f"screen_{name}.png"
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        f"--window-size=1920,{height}", "--virtual-time-budget=5000", f"--screenshot={out}", base + "/"],
                       capture_output=True, timeout=90)
    print("화면 캡처", out.name, out.exists())


def fetch(name):
    with urllib.request.urlopen(f"{base}/api/report/{name}", timeout=60) as r:
        data = r.read()
    (SAVE / name).write_bytes(data)
    return data


try:
    if base:
        shot("1_start")
        call("POST", "/api/run", {"example": "effect"})
        call("POST", "/api/place", {"emd": "대정읍"})
        s = wait({"ready", "stopped"})
        check("계획 준비(키 없음이라 미리 만든 계획)", s["stage"] == "ready" and s["origin"] == "premade", f"{s['stage']} {s['origin']}")
        shot("2_plan", 2000)
        call("POST", "/api/files/example")
        check("파일 넣은 뒤 외부 연결 잠김", call("GET", "/api/status")["locked"])
        call("POST", "/api/calculate")
        s = wait({"done"})
        summary = s["summary"] or {}
        check("계산 완료", s["stage"] == "done" and not s["error"], f"결과 {summary.get('outcome')} 오류 {s['error']}")
        shot("3_result", 4600)
        for line in s["log"]:
            print(f"  {line['time']} {line['kind']} {line['text']}")
        if summary:
            pdf = fetch(summary["pdf"])
            check("결과 PDF", pdf.startswith(b"%PDF") and len(pdf) > 10_000, f"{len(pdf)} bytes")
            check("PDF 글꼴 맑은 고딕", b"Malgun" in pdf)
            for name in summary["images"]:
                png = fetch(name)
                check(f"그림 {name}", png.startswith(b"\x89PNG"), f"{len(png)} bytes")
            print("결과 문장:", summary.get("sentence"))
        again = bat("run.bat", 120)
        check("두 번째 run.bat은 이미 실행 중 안내", "이미 실행 중" in again, again.strip()[:80])
        try:
            call("POST", "/api/selfcheck")
            check("잠긴 동안 자가 점검 막힘", False)
        except urllib.error.HTTPError as e:
            check("잠긴 동안 자가 점검 막힘", e.code == 409)
        call("POST", "/api/reset")
        check("끝내기 뒤 잠금 풀림", not call("GET", "/api/status")["locked"])
        check("끝내기 뒤 결과 폴더 비움(자동 삭제 켜짐)", not any((ROOT / "app" / "out" / "report").glob("*")))
        rows = call("POST", "/api/selfcheck")["rows"]
        for row in rows:
            print(f"  자가 점검 {row['item']}: {row['ok']} {row['detail']}")
        check("자가 점검 7항목", len(rows) == 7 and all(r["ok"] for r in rows))
finally:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True)
    log.close()

print("실패:", failures or "없음", flush=True)
sys.exit(1 if failures else 0)
