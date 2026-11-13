import sys
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import egress

BASE = Path(__file__).parent
# 8501은 Streamlit 기본 포트라 다른 참가작과 겹칠 수 있다
PORTS = range(18501, 18511)

app = FastAPI(title="행사 효과 나란히")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "app": egress.APP_MARK}


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
    config = uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=open_when_ready, args=(server, f"http://127.0.0.1:{port}/"), daemon=True).start()
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
