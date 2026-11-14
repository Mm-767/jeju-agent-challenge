"""맥에서 윈도우용 제출 묶음을 만든다.

python tools/build_zip.py lock               윈도우 기준 잠금 파일(requirements-lock.txt)
python tools/build_zip.py bundle [--env F]   build/EventEffect 묶음과 ZIP. --env는 평가용 키 파일
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
ROOT = APP.parent
BUILD = ROOT / "build"
DL = BUILD / "dl"
STAGE = BUILD / "EventEffect"
PIP = [str(APP / ".venv" / "bin" / "pip")]
EMBED = "python-3.11.9-embed-amd64.zip"
EMBED_URL = f"https://www.python.org/ftp/python/3.11.9/{EMBED}"
# python.org 3.11.9 릴리스 페이지의 MD5(11/13 대조)
EMBED_MD5 = "6d9aa08531d48fcc261ba667e2df17c4"
WIN_TARGET = [
    "--platform", "win_amd64", "--python-version", "3.11",
    "--implementation", "cp", "--abi", "cp311", "--only-binary=:all:",
]
# 260자 경로 한도에서 압축 풀기 기본 경로(약 90자)를 뺀 값
MAX_REL_PATH = 170

# 포함 목록 방식: 여기 없는 파일은 ZIP에 들어가지 않는다(.env는 --env로만)
INCLUDE = [
    "*.py", ".env.example", "requirements-lock.txt", "prompts/*", "static/*", "spec/card_v02.json",
    "data/hub/events.csv", "data/hub/places.json", "data/hub/population/*.csv", "data/premade/*.json",
    "data/dummy/card_effect/*.csv", "data/dummy/card_none/*.csv", "data/dummy/card_rehearsal/*.csv",
    "tests/*.py", "tools/*.py",
]

PTH = ["python311.zip", ".", "Lib\\site-packages", "..\\app", "import site"]
INSTALL_BAT = [
    "@echo off",
    "cd /d \"%~dp0\"",
    "if not exist \"python\\python.exe\" (",
    "  echo Please extract the ZIP file first, then run install.bat again.",
    "  pause",
    "  exit /b 1",
    ")",
    "\"python\\python.exe\" -X utf8 \"app\\install_check.py\"",
    "pause",
]
RUN_BAT = [
    "@echo off",
    "cd /d \"%~dp0\"",
    "\"python\\python.exe\" -X utf8 \"app\\server.py\"",
    "if errorlevel 1 pause",
]

WIN_ENV = {
    "os_name": "nt", "sys_platform": "win32", "platform_system": "Windows", "platform_machine": "AMD64",
    "implementation_name": "cpython", "platform_python_implementation": "CPython",
    "python_version": "3.11", "python_full_version": "3.11.9", "extra": "",
}
SYSTEM_DLLS = {
    "kernel32.dll", "user32.dll", "advapi32.dll", "ws2_32.dll", "ole32.dll", "oleaut32.dll", "shell32.dll",
    "gdi32.dll", "msvcrt.dll", "bcrypt.dll", "crypt32.dll", "secur32.dll", "ntdll.dll", "shlwapi.dll",
    "comctl32.dll", "comdlg32.dll", "rpcrt4.dll", "iphlpapi.dll", "version.dll", "winmm.dll", "imm32.dll",
    "setupapi.dll", "cfgmgr32.dll", "dwrite.dll", "d2d1.dll", "gdiplus.dll", "userenv.dll", "psapi.dll",
    "dbghelp.dll", "ncrypt.dll", "mswsock.dll", "normaliz.dll", "winhttp.dll", "wininet.dll",
    "powrprof.dll", "uxtheme.dll", "dwmapi.dll", "opengl32.dll", "msimg32.dll", "usp10.dll", "ucrtbase.dll",
    "cabinet.dll", "msi.dll", "bcryptprimitives.dll",
}


def lock():
    report = DL / "lock_report.json"
    DL.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        PIP + ["install", "--dry-run", "--quiet", "--ignore-installed", "--report", str(report)]
        + WIN_TARGET + ["-r", str(APP / "requirements.in")],
        check=True,
    )
    items = sorted(
        (i["metadata"]["name"], i["metadata"]["version"]) for i in json.loads(report.read_text())["install"]
    )
    lines = ["# tools/build_zip.py lock 이 윈도우(win_amd64, cp311) 기준으로 만든다. 손으로 고치지 않는다."]
    lines += [f"{n}=={v}" for n, v in items]
    (APP / "requirements-lock.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"requirements-lock.txt {len(items)}개")


def download_embed():
    path = DL / EMBED
    if not path.exists():
        DL.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(EMBED_URL, timeout=120) as r, path.open("wb") as f:
            shutil.copyfileobj(r, f)
    md5 = hashlib.md5(path.read_bytes()).hexdigest()
    if md5 != EMBED_MD5:
        raise SystemExit(f"{EMBED} MD5 불일치: {md5}")
    return path


def pe_imports(path):
    """PE 파일의 가져오기 표에서 DLL 이름을 읽는다(지연 로드 표는 보지 않는다)."""
    b = path.read_bytes()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    if b[pe:pe + 4] != b"PE\0\0":
        return []
    sections = struct.unpack_from("<H", b, pe + 6)[0]
    opt_size = struct.unpack_from("<H", b, pe + 20)[0]
    opt = pe + 24
    dirs = opt + (112 if struct.unpack_from("<H", b, opt)[0] == 0x20B else 96)
    import_rva = struct.unpack_from("<I", b, dirs + 8)[0]
    table = []
    for i in range(sections):
        vsize, va, rsize, raw = struct.unpack_from("<IIII", b, opt + opt_size + i * 40 + 8)
        table.append((va, max(vsize, rsize), raw))

    def offset(rva):
        for va, size, raw in table:
            if va <= rva < va + size:
                return rva - va + raw
        raise ValueError(rva)

    names = []
    if not import_rva:
        return names
    p = offset(import_rva)
    while True:
        desc = struct.unpack_from("<IIIII", b, p)
        if not any(desc):
            return names
        n = offset(desc[3])
        names.append(b[n:b.index(b"\0", n)].decode("ascii"))
        p += 20


def missing_windows_deps(site):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    metas = list(site.glob("*.dist-info/METADATA"))
    installed = set()
    requires = []
    for meta in metas:
        name = None
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.startswith("Name: "):
                name = line[6:].strip()
            elif line.startswith("Requires-Dist: "):
                requires.append((name, line[15:].strip()))
            elif not line:
                break
        installed.add(canonicalize_name(name))
    missing = []
    for owner, spec in requires:
        req = Requirement(spec)
        if req.marker and not req.marker.evaluate(WIN_ENV):
            continue
        if canonicalize_name(req.name) not in installed:
            missing.append(f"{owner} -> {req.name}")
    return missing


def static_checks(stage):
    files = [p for p in stage.rglob("*") if p.is_file()]
    rel = [p.relative_to(stage.parent).as_posix() for p in files]
    problems = []
    pyd = [p for p in files if p.suffix == ".pyd"]
    if not pyd:
        problems.append(".pyd가 없다")
    for bad, why in (
        ([r for r in rel if r.endswith((".so", ".dylib"))], "맥용 바이너리"),
        ([r for r in rel if r.endswith(".pyc") or "__pycache__" in r], ".pyc"),
        ([r for r in rel if Path(r).name == ".env"], ".env"),
        ([r for r in rel if r.endswith("direct_url.json") and "/Users/" in (stage.parent / r).read_text()], "개인 경로"),
    ):
        if bad:
            problems.append(f"{why} {len(bad)}개: {bad[:3]}")
    longest = max(rel, key=len)
    if len(longest) > MAX_REL_PATH:
        problems.append(f"경로 {len(longest)}자 > {MAX_REL_PATH}: {longest}")
    missing = missing_windows_deps(stage / "python" / "Lib" / "site-packages")
    if missing:
        problems.append(f"윈도우 기준 빠진 의존성: {missing}")
    bundled = {p.name.lower() for p in files if p.suffix.lower() in (".dll", ".pyd")}
    unknown = {}
    for p in files:
        if p.suffix.lower() in (".dll", ".pyd"):
            for dll in pe_imports(p):
                low = dll.lower()
                if low in bundled or low in SYSTEM_DLLS or low.startswith(("api-ms-win-", "ext-ms-win-")):
                    continue
                unknown.setdefault(dll, []).append(p.relative_to(stage).as_posix())
    return problems, unknown, files, longest


def license_of(meta):
    lines = meta.splitlines()
    spdx = next((l[20:] for l in lines if l.startswith("License-Expression: ")), "")
    if spdx:
        return spdx
    value = next((l[9:] for l in lines if l.startswith("License: ")), "")
    if value and len(value) <= 40 and "copyright" not in value.lower() and "=" not in value:
        return value
    found = [l.rsplit(" :: ", 1)[1] for l in lines if l.startswith("Classifier: License ::")]
    return " / ".join(found) or "원문 참고"


def notices(stage):
    site = stage / "python" / "Lib" / "site-packages"
    rows = []
    infos = sorted(site.glob("*.dist-info"), key=lambda p: p.name.lower())
    for info in infos:
        meta = (info / "METADATA").read_text(encoding="utf-8")
        name = next(l[6:] for l in meta.splitlines() if l.startswith("Name: "))
        version = next(l[9:] for l in meta.splitlines() if l.startswith("Version: "))
        texts = sorted(p.relative_to(stage).as_posix() for p in info.rglob("*")
                       if p.is_file() and p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")))
        if not texts:
            raise SystemExit(f"{name} 라이선스 원문이 없다")
        rows += [f"{name} {version}", f"  라이선스: {license_of(meta)}"] + [f"  원문: {t}" for t in texts] + [""]
    head = [
        "제3자 소프트웨어 고지",
        "",
        "이 묶음은 아래 오픈소스를 고치지 않고 그대로 담았다. 각 라이선스 원문은 적힌 경로에 있다.",
        "",
        "Python 3.11.9 (embeddable, python.org)",
        "  라이선스: PSF-2.0 외",
        "  원문: python/LICENSE.txt",
        "",
    ]
    tail = [
        "fpdf2(LGPL-3.0-only)는 수정하지 않은 파이썬 원본(python/Lib/site-packages/fpdf)으로 들어 있어,",
        "이용자가 같은 폴더를 다른 버전으로 바꿔 넣을 수 있다.",
        "PDF 글꼴은 동봉하지 않고 윈도우에 깔린 맑은 고딕(C:\\Windows\\Fonts\\malgun.ttf)을 읽기만 한다.",
    ]
    (stage / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(head + rows + tail) + "\n", encoding="utf-8")
    return len(infos)


def bundle(env_file):
    if STAGE.exists():
        shutil.rmtree(STAGE)
    py = STAGE / "python"
    py.mkdir(parents=True)
    embed = download_embed()
    with zipfile.ZipFile(embed) as z:
        z.extractall(py)
    (py / "python311._pth").write_text("\r\n".join(PTH) + "\r\n", encoding="ascii")
    site = py / "Lib" / "site-packages"
    subprocess.run(
        PIP + ["install", "--quiet", "--no-compile", "--no-deps", "--target", str(site)]
        + WIN_TARGET + ["-r", str(APP / "requirements-lock.txt")],
        check=True,
    )
    shutil.rmtree(site / "bin", ignore_errors=True)

    app = STAGE / "app"
    for pattern in INCLUDE:
        matches = sorted(APP.glob(pattern))
        if not matches:
            raise SystemExit(f"포함 목록 {pattern}에 맞는 파일이 없다")
        for src in matches:
            dst = app / src.relative_to(APP)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    if env_file:
        # 허브 프로젝트 키는 넣지 않는다. 실행 중 허브를 부르지 않는다.
        keep = [l for l in env_file.read_text(encoding="utf-8").splitlines() if l.startswith("ANTHROPIC_API_KEY=")]
        if not keep:
            raise SystemExit("ANTHROPIC_API_KEY가 없다")
        (app / ".env").write_text("\n".join(keep) + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "docs" / "README.txt", STAGE / "README.txt")
    print(f"라이선스 고지 {notices(STAGE)}개 패키지")
    for name, lines in (("install.bat", INSTALL_BAT), ("run.bat", RUN_BAT)):
        (STAGE / name).write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))

    problems, unknown, files, longest = static_checks(STAGE)
    if env_file:
        problems = [p for p in problems if not p.startswith(".env")]
    manifest = [f"{p.relative_to(STAGE).as_posix()}\t{p.stat().st_size}" for p in sorted(files)]
    manifest.append(f"# files={len(files)} longest={len(longest)} {longest}")
    (app / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    out = BUILD / "EventEffect_test.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(BUILD).as_posix())
    print(f"embed sha256 {hashlib.sha256(embed.read_bytes()).hexdigest()} ({embed.stat().st_size} bytes)")
    print(f"files {len(files)}, .pyd {sum(p.suffix == '.pyd' for p in files)}, longest {len(longest)}자")
    print(f"zip {out} {out.stat().st_size / 1e6:.1f}MB")
    for dll, users in sorted(unknown.items()):
        print(f"[DLL] {dll}: {len(users)}개 파일, 예 {users[0]}")
    for p in problems:
        print(f"[문제] {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["lock", "bundle"])
    parser.add_argument("--env", type=Path)
    args = parser.parse_args()
    if args.command == "lock":
        lock()
    else:
        sys.exit(bundle(args.env))
