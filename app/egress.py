"""네트워크를 쓰는 유일한 런타임 모듈. 다른 런타임 파일은 socket·urllib·http·anthropic을 불러오지 않는다."""
import json
import socket
import urllib.request

APP_MARK = "event-effect"

# 127.0.0.1 확인에 윈도우 시스템 프록시가 끼지 않게 프록시 없이 연다
_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def port_free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def local_app_running(port):
    try:
        with _local.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return json.load(r).get("app") == APP_MARK
    except (OSError, ValueError):
        return False
