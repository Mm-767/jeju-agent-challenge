"""install.bat이 부르는 설치 점검. 항목마다 PASS/FAIL을 찍고 out/install_check.txt에 남긴다.

설치 점검은 실행 중 Agent가 아니라 개발·평가 보조 도구라, 키가 있을 때 한 번만 api.anthropic.com을 부른다.
"""
import importlib
import importlib.metadata as md
import logging
import os
import platform
import sys
import time
import traceback
import warnings
from pathlib import Path

APP = Path(__file__).resolve().parent
OUT = APP / "out"
EXPECTED_VERSION = "3.11.9"
# 윈도우는 맑은 고딕, 맥 개발 PC는 AppleGothic
KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic"]

# 잠금 파일의 배포 이름과 불러올 모듈 이름이 다른 것만 적는다
IMPORT_NAME = {
    "annotated-doc": "annotated_doc", "annotated-types": "annotated_types", "docstring_parser": "docstring_parser",
    "fpdf2": "fpdf", "fonttools": "fontTools", "opentelemetry-api": "opentelemetry.trace", "pillow": "PIL.Image",
    "python-dateutil": "dateutil", "typing-inspection": "typing_inspection", "pydantic_core": "pydantic_core",
    "httpcore2": "httpcore2", "httpx2": "httpx2", "typing_extensions": "typing_extensions",
}

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


def run_checks():
    results = []
    for name, fn in CHECKS:
        started = time.perf_counter()
        try:
            detail = fn() or ""
            ok = True
        except Exception as e:  # 점검 도구라 모든 실패를 항목 결과로 남긴다
            ok = False
            detail = f"{type(e).__name__}: {e}"
        results.append((ok, name, detail, time.perf_counter() - started))
    return results


def locked_packages():
    lock = APP / "requirements-lock.txt"
    for line in lock.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            yield line.split("==")[0]


@check("Python 판 3.11.9")
def _version():
    assert platform.python_version() == EXPECTED_VERSION, platform.python_version()
    return sys.executable


@check("UTF-8 모드(-X utf8)")
def _utf8():
    assert sys.flags.utf8_mode == 1, sys.flags.utf8_mode


@check("모든 패키지 불러오기")
def _imports():
    failed = []
    for dist in locked_packages():
        mod = IMPORT_NAME.get(dist, dist.replace("-", "_"))
        try:
            importlib.import_module(mod)
        except Exception as e:
            failed.append(f"{dist}({mod}): {type(e).__name__}: {e}")
    assert not failed, "; ".join(failed)
    return f"{len(list(locked_packages()))}개"


@check("윈도우 기준 빠진 의존성 없음")
def _markers():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    installed = {canonicalize_name(d.metadata["Name"]) for d in md.distributions()}
    missing = []
    for d in md.distributions():
        for spec in d.requires or []:
            req = Requirement(spec)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            if canonicalize_name(req.name) not in installed:
                missing.append(f"{d.metadata['Name']} -> {req.name}")
    assert not missing, "; ".join(missing)


@check("한글 그림(png) 그리기")
def _korean_png():
    os.environ.setdefault("MPLCONFIGDIR", str(OUT / "cache"))
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    family = next((f for f in KOREAN_FONTS if f in available), None)
    assert family, f"한글 글꼴 없음({', '.join(KOREAN_FONTS)})"
    plt.rcParams["font.family"] = family
    OUT.mkdir(exist_ok=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = plt.subplots(figsize=(4, 1.2))
        ax.axis("off")
        ax.text(0.5, 0.5, "한글 확인 대정읍 표선면", ha="center", va="center", fontsize=16)
        fig.savefig(OUT / "install_check.png")
        plt.close(fig)
    glyph = [str(w.message) for w in caught if "Glyph" in str(w.message)]
    assert not glyph, glyph[0]
    return family


@check("현재 폴더 경로의 카드 CSV 읽기")
def _csv_path():
    import card

    files = sorted((APP / "data" / "dummy").rglob("*.csv"))
    assert files, "가상 CSV 없음"
    table = card.new_table()
    result = card.ingest(files[0].read_bytes(), files[0].name, table)
    assert result["ok"], result["message"]
    return f"{APP} / 칸 {len(table['cells'])}개"


@check("원격 측정 내보내기 부품 없음")
def _no_exporter():
    for mod in ("opentelemetry.sdk", "opentelemetry.exporter"):
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{mod}를 불러올 수 있음")


@check("외부 AI 호출(키가 있을 때만)")
def _api():
    import config

    key = config.env("ANTHROPIC_API_KEY")
    if not key:
        return "키 없음, 건너뜀"
    import anthropic

    client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=60)
    tool = {
        "name": "report_ok",
        "description": "점검 결과를 보고한다.",
        "input_schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    msg = client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=1024,
        tools=[tool],
        messages=[{"role": "user", "content": "report_ok 도구를 ok=true로 한 번 부르세요."}],
    )
    used = [b.name for b in msg.content if b.type == "tool_use"]
    return f"stop_reason={msg.stop_reason}, tool_use={used}, 입력 {msg.usage.input_tokens} 출력 {msg.usage.output_tokens} 토큰"


def main():
    OUT.mkdir(exist_ok=True)
    lines = [f"설치 점검 {time.strftime('%Y-%m-%d %H:%M:%S')}  폴더: {APP}"]
    results = run_checks()
    for ok, name, detail, secs in results:
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name} ({secs:.1f}초) {detail}")
    failed = sum(1 for r in results if not r[0])
    lines.append("모두 통과했습니다." if not failed else f"{failed}개 항목이 실패했습니다. 이 창을 찍어 보내 주세요.")
    text = "\n".join(lines)
    print(text, flush=True)
    (OUT / "install_check.txt").write_text(text + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
