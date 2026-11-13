# 47 윈도우 패키징·배포 설계: Python 본체와 패키지를 ZIP에 통째로 넣기

작성 2026-11-13, 윈도우 패키징·배포 담당. 설계만 했고 코드는 만들거나 고치지 않았다. 확인 범위는 0절과 맨 끝 출처에 적었다.

## 결론 5줄

1. python.org의 윈도우용 embeddable 3.11.9 zip에, 맥에서 pip로 받은 윈도우용 휠을 설치해 넣는 방식을 추천한다. 개발 venv와 Python 버전이 3.11.9로 정확히 같고, 오늘 의존성 40개가 모두 윈도우용 휠로 해석되는 것을 확인했다(사용자 결정 필요).
2. embeddable Python은 `python311._pth` 파일이 있으면 환경 변수를 모두 무시하는 격리 모드로 돈다. 그래서 `PYTHONUTF8=1` 대신 실행 인자 `-X utf8`을 쓰고, 앱 폴더는 `._pth`에 직접 적는다(공식 문서 문장에서 추론, 11/15에 확인).
3. install.bat은 압축 해제 여부 확인과 자가 점검 스크립트 실행만 하고, run.bat은 폴더 고정과 서버 실행만 한다. 이미 실행 중인지 판단, 브라우저 열기, 한글 경로 경고는 Python 코드에 넣어 맥과 윈도우의 동작을 같게 만든다.
4. 최종 ZIP은 약 100~150MB로 추정되어 상한 100GB와 비교하면 크기는 문제가 아니다. 실제 위험은 스마트 앱 컨트롤, Visual C++ 런타임 누락, 260자 경로 제한, 포트 8501 충돌이다.
5. 11/15 시험 묶음은 빈 화면 서버와 자가 점검 스크립트 하나로 만들고 11/14에 맥에서 미리 준비한다. 완료 기준은 영문 경로와 한글·공백 경로 두 곳에서 자가 점검 항목이 모두 통과하는 것이다.

---

## 0. 오늘 확인한 사실

| 항목 | 확인 결과 | 확인 방법 |
|---|---|---|
| 개발 PC | arm64(Apple Silicon)다. 앱 venv는 Python 3.11.9, pip 24.0이다 | `uname -m`, venv의 pip |
| 3.11.9 embeddable zip | 있다. 크기 11,249,023바이트 | python.org FTP에 HEAD 요청(출처 4) |
| 3.11.13 embeddable zip | 없다(404). 3.11은 보안 수정만 받는 단계라 2027년 10월까지 소스 형태로만 나온다 | HEAD 요청, 3.11.13 공지(출처 3) |
| 3.11.9의 위치 | 3.11의 마지막 버그 수정 판이다. 그 뒤로 python.org 윈도우 바이너리가 없다 | 3.11.9 공지(출처 3) |
| 3.13.9 embeddable zip | 있다 | HEAD 요청 |
| python-build-standalone | 최신 태그 20261110에 `cpython-3.11.18` 윈도우 x64 install_only 49.1MB, install_only_stripped 25.5MB가 있다 | GitHub 릴리스 API(출처 7) |
| 윈도우용 휠 해석 | requirements.txt 16개와 duckdb, pandas, numpy, matplotlib, fpdf2, anthropic, httpx를 함께 넣어 해석하면 40개 패키지가 모두 `cp311-cp311-win_amd64` 또는 순수 Python 휠로 잡힌다. 휠 압축 크기 합계는 65.7MB다 | `pip install --dry-run --report`, PyPI JSON(출처 6) |
| 컴파일된 패키지 | duckdb 2.0.0(15.4MB), numpy 2.4.6(12.6MB), pandas 3.1.1(11.0MB), matplotlib 3.11.2(9.3MB), pillow 13.0.0(7.3MB), pydantic_core 2.50.4(2.3MB), fonttools 4.68.0, jiter 0.19.0, contourpy 1.3.3, kiwisolver 1.5.1 | 같은 보고서 |
| 최신판과 다른 것 | numpy는 최신 2.5.4가 아니라 2.4.6, contourpy는 최신 1.4.0이 아니라 1.3.3이 잡혔다. 최신판이 Python 3.11 지원을 뺀 것으로 추정한다 | 같은 보고서 |
| PyInstaller | 윈도우용 실행 파일은 윈도우에서 만들어야 한다. 문서는 "각 플랫폼에 PyInstaller를 설치해 따로 묶으라"고 하고 가상 머신을 권한다 | PyInstaller 문서(출처 8) |
| 스마트 앱 컨트롤 | 클라우드 평판으로 판단하지 못하면 서명을 보고, 서명이 없거나 잘못되면 막는다. 앱 하나만 예외로 두는 방법은 없다. 회사 사용자나 개발자로 판단되면 자동으로 꺼진다 | 마이크로소프트 FAQ(출처 9) |

---

## 1. 선택지 비교와 추천 (사용자 결정 필요)

ADR-149로 "Python 본체와 패키지를 ZIP에 통째로 넣는다"는 이미 정해졌다. 여기서 고를 것은 어떤 Python 본체를 넣고 어떤 모양으로 묶느냐다.

| 기준 | (a) python.org embeddable 3.11.9 + 맥에서 설치한 윈도우 휠 | (b) python-build-standalone 3.11.18 + 맥에서 설치한 윈도우 휠 | (c) PyInstaller로 실행 파일 하나 | (d) 기타 |
|---|---|---|---|---|
| 맥에서 준비 | 된다. zip을 풀고 `pip install --target`에 윈도우 플랫폼 옵션을 붙인다 | 된다. tar.gz를 풀고 같은 명령을 쓴다 | 안 된다. 윈도우 PC나 윈도우 가상 머신이 있어야 한다(출처 8). Apple Silicon 맥의 가상 머신은 ARM용 윈도우라 x64 빌드가 더 꼬인다(추정) | NuGet의 python 패키지, WinPython은 확인하지 않았다. GitHub Actions 윈도우 실행기로 빌드하는 방법은 저장소와 CI 설정이 새로 든다 |
| 개발 venv와 일치 | 3.11.9로 정확히 같다 | 3.11.18이라 소수 판이 다르다. 같은 3.11이라 휠은 그대로 맞는다 | 같게 만들 수 있다 | 해당 없음 |
| 심사위원 단계 | 압축 풀기, install.bat, run.bat | 같다 | 압축 풀기, 실행 파일 더블클릭 | 같거나 많다 |
| 서명과 스마트 앱 컨트롤 | python.exe와 Python DLL은 PSF 서명이 있다(기억 기반, 11/15에 확인). 서드파티 .pyd와 .dll은 대부분 서명이 없어 평판에 기댄다(추정) | Python 본체도 서명이 없는 것으로 기억한다(추정). 위험이 (a)보다 크다 | 서명 없는 부트로더 실행 파일이 백신에 오진되는 사례가 많다(기억 기반) | 알 수 없음 |
| 보안 수정 | 2024-04 이후 Python 보안 수정이 없다. 127.0.0.1에서만 여는 평가용 앱이라 영향은 작다고 판단한다(추론) | 3.11.18까지 들어 있다 | 넣은 Python 판에 따름 | 해당 없음 |
| 크기 | 본체 zip 11.2MB | 본체 25.5~49.1MB | 비슷하거나 작음 | 해당 없음 |
| 실패 모드 | Visual C++ 런타임 누락, 격리 모드 오해(3절), 경로 길이 | (a)와 같고 서명 위험이 더 있다 | 맥에서 만들 수 없어 일정이 무너진다. 실행 때마다 임시 폴더에 풀려 느리다(기억 기반) | 해당 없음 |

추천은 (a)다. 맥에서 그대로 만들 수 있고, 개발 venv와 버전이 같으며, 본체가 서명된 쪽이 스마트 앱 컨트롤 위험이 가장 작다. (b)는 11/15 시험에서 (a)의 본체가 막히거나 알 수 없는 오류가 날 때만 바꿔 끼운다. 휠 설치 절차가 같아 바꾸는 비용은 반나절 안쪽이다(추정). (c)는 맥에서 만들 수 없어서 뺀다.

묶는 모양은 site-packages를 미리 풀어 ZIP에 그대로 넣는 한 단계 구조를 기본으로 한다. 탐색기 압축 풀기가 파일 수천 개 때문에 수 분 걸리거나 260자 경로 제한에 걸리면, site-packages만 안쪽 `packages.zip`으로 한 번 더 묶고 install.bat에서 `python\python.exe -m zipfile -e`로 풀게 바꾼다. 이 전환은 11/15 측정 결과로 정한다.

---

## 2. 맥에서 윈도우용 패키지 받기

### 2-1. 윈도우용 휠이 있는지 확인하는 명령 (다운로드 없음)

```bash
.venv/bin/python -m pip install --dry-run --ignore-installed --report report.json \
  --target ./tmp_target \
  --platform win_amd64 --python-version 3.11 --implementation cp --abi cp311 \
  --only-binary=:all: \
  -r requirements.txt duckdb pandas numpy matplotlib fpdf2 anthropic httpx
```

- `--only-binary=:all:`이라 윈도우용 휠이 없는 패키지가 하나라도 있으면 해석이 실패하고 그 이름이 나온다. 실패가 없으면 모두 있다는 뜻이다.
- `--dry-run`은 PyPI가 따로 제공하는 메타데이터 파일만 받아 의존성을 푼다(기억 기반). 오늘 이 명령은 큰 다운로드 없이 끝났다.
- `report.json`의 `install` 목록에서 파일 이름 끝이 `none-any.whl`이 아닌 것이 컴파일된 패키지다. 0절 표가 이 결과다.
- 옵션의 뜻은 pip 문서에 있다(출처 5). `--abi`를 쓸 때는 `--implementation`, `--platform`, `--python-version`을 같이 주라고 적혀 있다.

### 2-2. 잠금 파일 만들기

`report.json`의 이름과 버전으로 `requirements-lock.txt`(이름==버전 40줄)를 만든다. 맥 venv도 이 파일로 다시 설치해서, 맥과 윈도우가 같은 버전으로 돈다. numpy처럼 최신판이 3.11을 버린 패키지가 있으므로, 맥에서 따로 `pip install numpy`를 하면 윈도우와 다른 판이 잡힐 수 있다. 완료 기준은 맥 venv의 `pip freeze`와 잠금 파일이 같은 것이다.

### 2-3. 윈도우용 site-packages 만들기

```bash
.venv/bin/python -m pip install --no-compile \
  --target build/EventEffect/python/Lib/site-packages \
  --platform win_amd64 --python-version 3.11 --implementation cp --abi cp311 \
  --only-binary=:all: -r requirements-lock.txt
rm -rf build/EventEffect/python/Lib/site-packages/bin
```

- `pip install --target`은 휠을 내려받아 바로 대상 폴더에 풀어 준다. `pip download`로 받은 뒤 손으로 푸는 것보다 단계가 하나 적고, 휠 안의 `.data` 폴더 처리도 pip가 맡는다.
- `bin/`에는 맥용 실행 스크립트(uvicorn, f2py 등)가 생기므로 지운다. 윈도우에서는 `python.exe app\server.py`로만 실행한다.
- `--no-compile`은 맥에서 만든 .pyc를 넣지 않기 위해서다. ZIP의 시각 정보가 2초 단위라 윈도우에서 어차피 다시 컴파일될 수 있다(추정). install.bat의 자가 점검이 모든 패키지를 한 번 import하므로 그때 윈도우에서 컴파일된다.
- 완료 기준: site-packages 안에 `.pyd`가 있고, `.so`와 `darwin`이 들어간 파일이 0개다.

### 2-4. 각 .pyd가 필요로 하는 DLL 확인 (맥에서, 선택)

윈도우에서 가장 흔한 실패는 `DLL load failed while importing ...`다. 맥에서도 .pyd의 가져오기 표를 읽어 필요한 DLL 이름을 볼 수 있다. macOS의 `objdump -p 파일.pyd`가 PE 형식을 읽어 `DLL Name`을 보여 준다고 추정한다(확인하지 않음). 목록에 `MSVCP140.dll`이나 `VCRUNTIME140_1.dll`이 있는데 embeddable zip에 없으면 11/15 시험에서 특히 지켜본다. 시간이 없으면 이 단계는 건너뛰고 11/15 자가 점검 결과로 판단한다.

---

## 3. embeddable Python 설정

### 3-1. 공식 문서가 말하는 것 (출처 1, 2)

- embeddable 배포본은 풀면 사용자 시스템의 환경 변수, 레지스트리, 설치된 패키지와 (거의) 완전히 격리된다. 표준 라이브러리는 미리 컴파일된 .pyc가 zip 하나에 들어 있다. Tcl/tk, IDLE, pip, 문서는 들어 있지 않다.
- Microsoft C 런타임은 들어 있지 않으며 설치하는 쪽 책임이다. 윈도우 업데이트로 이미 깔려 있을 수 있고, 시스템 폴더의 `ucrtbase.dll`로 확인할 수 있다고 적혀 있다.
- 서드파티 패키지는 배포본 옆에 설치해 두라고 하고, 일반 설치처럼 pip로 관리하는 것은 지원하지 않는다고 적혀 있다. 이번 설계가 pip 없이 맥에서 미리 설치해 넣는 이유다.
- `._pth` 파일이 있으면 그 파일의 줄이 `sys.path`를 완전히 대신한다. 레지스트리와 모든 환경 변수가 무시되고, 격리 모드가 켜지며, `import site` 줄이 없으면 site 모듈을 불러오지 않는다. 각 경로는 절대 경로이거나 `._pth` 파일 위치 기준 상대 경로다. `import site`가 있으면 `.pth` 파일은 평소처럼 처리된다.

### 3-2. 여기서 나오는 결론 세 가지 (문서에서 추론, 11/15 확인)

1. **`PYTHONUTF8=1`은 효과가 없을 가능성이 크다.** 문서가 "모든 환경 변수가 무시된다"고 쓰기 때문이다. 같은 문서가 UTF-8 모드를 켜는 다른 방법으로 실행 인자 `-X utf8`을 적고 있으므로 run.bat과 install.bat에서는 이것을 쓴다. 자가 점검에서 `sys.flags.utf8_mode`가 1인지 출력해 확인한다.
2. **실행한 스크립트의 폴더가 `sys.path`에 자동으로 들어가지 않는다.** Python 3.11의 격리 모드는 스크립트 폴더를 앞에 넣지 않는 옵션을 포함한다(기억 기반). 그래서 `..\app`을 `._pth`에 적는다. 맥에서는 스크립트 폴더가 자동으로 들어가므로 결과가 같아진다.
3. **사용자 site-packages와 PYTHONPATH가 끼어들지 않는다.** 심사위원 PC에 다른 Python이 깔려 있어도 섞이지 않는다는 뜻이라, 오히려 바라던 성질이다.

### 3-3. `python311._pth` 수정안

받은 그대로의 내용은 아래와 같다고 기억한다(추정, 풀어서 확인).

```
python311.zip
.

# Uncomment to run site.main() automatically
#import site
```

다음으로 바꾼다.

```
python311.zip
.
Lib\site-packages
..\app
import site
```

- `Lib\site-packages`: 2-3에서 만든 폴더다. `import site`만으로도 이 폴더가 잡히는 것으로 기억하지만, 명시해 두면 확인하기 쉽다.
- `..\app`: `server.py`와 앱 모듈이 있는 폴더다.
- `import site`: 패키지가 `.pth` 파일을 쓰는 경우를 대비한다. 격리 모드라 사용자 site-packages는 여전히 꺼져 있다.
- 완료 기준: 자가 점검이 출력한 `sys.path`가 위 네 경로(절대 경로로 바뀐 것)와 표준 라이브러리 zip만으로 이루어진다.

### 3-4. 그 밖의 설정

- matplotlib은 tkinter가 없으므로 코드 첫머리에서 `matplotlib.use("Agg")`로 고정한다. 환경 변수 `MPLBACKEND`도 쓸 수는 있지만(PYTHON으로 시작하지 않는 변수라 격리 모드와 무관할 것으로 추정) 맥과 같게 하려고 코드에 둔다.
- matplotlib 글꼴 캐시는 기본으로 사용자 홈 아래에 생긴다(기억 기반). 결과물은 한 폴더에만 남긴다는 원칙(22번 6절 13번)에 맞춰, matplotlib을 불러오기 전에 코드에서 `MPLCONFIGDIR`을 앱의 `out\cache`로 지정한다.
- pip은 넣지 않는다. 윈도우에서 패키지를 설치하는 단계가 없다.

---

## 4. install.bat과 run.bat 초안

원칙은 세 가지다. bat에는 영문만 쓰고 줄바꿈은 CRLF로 저장한다. 모든 경로를 큰따옴표로 감싸 공백 경로를 견딘다. 판단이 필요한 일은 Python으로 넘긴다. bat에서 한글 경로 판별이나 포트 검사를 하면 따옴표와 코드 페이지 문제가 생기고, 맥에서는 같은 코드가 돌지 않기 때문이다.

### 4-1. install.bat

```bat
@echo off
setlocal
cd /d "%~dp0"
if not exist "python\python.exe" goto not_extracted
echo Checking the app. The first check can take about 1 minute...
"python\python.exe" -X utf8 "app\selfcheck.py"
if errorlevel 1 goto failed
echo.
echo Check passed. Double-click run.bat to start the app.
pause
exit /b 0

:not_extracted
echo ERROR: python\python.exe was not found next to install.bat.
echo Right-click the ZIP file, choose "Extract All", then run install.bat in the extracted folder.
pause
exit /b 1

:failed
echo.
echo ERROR: The check failed. Take a screenshot of this window and see Troubleshooting in the manual.
pause
exit /b 1
```

- `python\python.exe`가 없을 때를 먼저 본다. ZIP을 풀지 않고 탐색기의 ZIP 미리보기 안에서 bat을 더블클릭하면 bat만 임시 폴더로 꺼내져 이렇게 된다(기억 기반).
- `app\selfcheck.py`가 하는 일: 설치 위치 경로가 영문인지, 공백이 있는지, 길이가 얼마인지 보고 문제가 있으면 경고하거나 `C:\EventEffect`로 옮기라고 안내한다. 빌드 때 만든 파일 목록과 실제 파일을 대조해 빠진 파일을 찾는다(압축 풀기 중 경로 길이 실패나 백신 격리를 잡는다). 모든 패키지를 import한다. 글꼴을 등록해 한글 제목 png와 한 쪽짜리 PDF를 `out`에 만든다. 결과를 항목별 PASS/FAIL로 출력하고 `out\selfcheck_result.txt`에도 쓴다. 하나라도 실패하면 종료 코드 1이다.
- 한글 경로를 오류로 막을지 경고로 둘지는 11/15 결과로 정한다. 통과하면 경고만 하고, 실패하면 오류로 바꿔 옮길 위치를 안내한다.

### 4-2. run.bat

```bat
@echo off
setlocal
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo ERROR: python\python.exe was not found. Extract the whole ZIP, then run install.bat first.
  pause
  exit /b 1
)
echo Keep this window open while you use the app. Close this window to stop the app.
"python\python.exe" -X utf8 "app\server.py"
if "%errorlevel%"=="3" exit /b 0
echo.
echo The app has stopped. If you see an error above, see Troubleshooting in the manual.
pause
```

나머지 요구는 `server.py`에서 처리한다(구현 단계에서 할 일이며 지금 고치지 않는다).

| 요구 | 처리 위치와 방법 |
|---|---|
| 127.0.0.1에서만 서버 실행 | 지금처럼 `uvicorn.run(host="127.0.0.1")`. 모든 주소로 열면 방화벽 허용 창이 뜬다(기억 기반) |
| 이미 실행 중일 때 | 시작 전에 표준 라이브러리 `urllib`로 `/api/health`를 1초 제한으로 부른다. 응답에 앱 표시 값(예: `"app": "event-effect"`)이 있으면 브라우저만 열고 종료 코드 3으로 끝낸다. run.bat은 3이면 조용히 닫힌다. 다른 프로그램이 같은 포트를 쓰면 uvicorn이 주소 사용 중 오류를 내고 run.bat이 멈춰 오류를 보여 준다 |
| 브라우저 자동 열기 | 서버 시작 직후 표준 라이브러리 `webbrowser.open`으로 주소를 연다. 기본 브라우저로 열린다. 열리지 않을 때를 위해 콘솔에 주소를 출력한다 |
| 종료 방법 | 검은 창을 닫거나 Ctrl+C. Ctrl+C 뒤 "Terminate batch job (Y/N)?"이 나오는데 어느 쪽을 눌러도 서버는 이미 멈춘다(기억 기반). 별도 stop.bat은 만들지 않는다 |
| 포트 | 8501은 Streamlit 기본 포트다. 심사위원이 다른 참가작(Streamlit)을 켜 둔 채로 우리 것을 실행하면 충돌한다(추정). 덜 쓰이는 번호(예: 18501)로 바꾸기를 권한다 |
| 콘솔 출력 | uvicorn 접근 기록을 끈다. 아래 6절의 콘솔 선택 멈춤 함정 때문이다 |

---

## 5. 최종 ZIP 폴더 구조와 크기

```
EventEffect.zip
└─ EventEffect\                 short ASCII root folder
   ├─ install.bat               CRLF, ASCII only
   ├─ run.bat                   CRLF, ASCII only
   ├─ README.txt                English pointer: "Open docs\manual_ko.pdf"
   ├─ docs\
   │   └─ manual_ko.pdf         Korean manual, English file name
   ├─ python\                   python-3.11.9-embed-amd64 unpacked
   │   ├─ python.exe, pythonw.exe, python311.dll, python3.dll
   │   ├─ python311.zip         standard library
   │   ├─ python311._pth        edited (section 3-3)
   │   ├─ *.pyd, *.dll          standard extension modules, vcruntime
   │   └─ Lib\site-packages\    40 packages from requirements-lock.txt
   ├─ app\
   │   ├─ server.py, selfcheck.py, (engine modules)
   │   ├─ static\
   │   ├─ spec\card_v02.json
   │   ├─ fonts\                one Korean TTF + its license file
   │   ├─ data\dummy\           sample CSVs for "try an example"
   │   ├─ data\hub\             public hub snapshot
   │   └─ manifest.txt          file list written at build time
   └─ out\                      created at runtime, results only
```

- 파일과 폴더 이름은 모두 영문이다. ZIP은 Python `zipfile`로 이름을 NFC로 바꿔 만든다(22번 6절 3번). `.env`, `.venv`, `__pycache__`, `.DS_Store`, 맥에서 돌린 `out`은 넣지 않는다. 개발 폴더를 통째로 복사하지 않고 넣을 파일 목록을 빌드 스크립트에 적어 그것만 넣는다. 그래야 캡디2 키가 든 `.env`가 실수로 들어가지 않는다. 평가용 키를 어디에 둘지는 다른 설계에서 정한다.
- 루트 폴더 이름을 짧게 두는 이유는 260자 경로 제한이다. site-packages 안 가장 긴 경로는 빌드 때 측정해 `manifest.txt`와 함께 기록한다. 압축 풀 위치를 포함해 260자에 가까우면 pandas, numpy, matplotlib의 `tests` 폴더를 지운다(측정 후 필요할 때만).

| 구성 | 크기 | 근거 |
|---|---|---|
| Python 본체 | zip 11.2MB, 풀면 약 20MB | zip 크기는 확인, 푼 크기는 추정 |
| site-packages | 휠 압축 65.7MB, 풀면 약 170~220MB | 압축 크기는 확인, 푼 크기는 2.5~3.3배로 추정 |
| 가상 카드 데이터 두 판 | 약 38MB | 40번 브리핑(판마다 19MB) |
| 허브 유동인구 스냅샷 | 약 10~30MB | 추정 |
| 글꼴, 매뉴얼, 코드 | 약 10~20MB | 추정 |
| 합계 | 풀면 약 250~300MB, ZIP 약 100~150MB | 추정. CSV가 잘 압축되면 더 작다 |

파일 수는 수천에서 1만 개 남짓으로 추정한다. 빌드 때 세어 기록하고, 11/15에 탐색기 압축 풀기 시간을 측정한다.

---

## 6. 윈도우에서만 드러나는 함정과 대응

위험이 큰 것부터 적었다.

| 함정 | 무엇이 일어나나 | 대응 | 확인 |
|---|---|---|---|
| 스마트 앱 컨트롤 | 평판으로 판단 못 한 서명 없는 앱과 바이너리를 막고, 앱 하나만 예외로 둘 수 없다(출처 9). 서명 없는 DLL이 막혔다는 사용자 보고도 있다(출처 9의 GitHub 사례) | python.exe가 서명된 (a)를 고른다. 서드파티 .pyd는 널리 배포된 파일이라 평판이 있을 것으로 추정한다. 센터 PC는 관리되는 회사 PC라 꺼져 있을 가능성이 높다(추정). 코드 서명 인증서는 사지 않는다 | 11/15 시험 PC의 설정(Windows 보안, 앱 및 브라우저 컨트롤)에서 켜짐 여부를 기록한다. 켜져 있으면 더 엄격한 시험이 된다 |
| Visual C++ 런타임 누락 | embeddable에는 C 런타임이 없다(출처 1). 깨끗한 PC에서 `DLL load failed while importing duckdb` 같은 오류가 날 수 있다(추정) | 2-4절로 미리 본다. 빠지면 Microsoft 재배포 패키지의 `msvcp140.dll` 등을 `python\` 옆에 둔다. 앱 폴더에 함께 배포하는 것이 허용된다고 기억한다(추정, 확인 필요) | 자가 점검의 import 항목 |
| `PYTHONUTF8` 무시 | 3-2절. 환경 변수로 UTF-8 모드를 켰다고 믿었는데 꺼져 있으면 `open()`이 CP949로 읽어 센터 CSV가 깨진다 | `-X utf8` 인자, 그리고 모든 파일 열기에 `encoding`을 명시 | `sys.flags.utf8_mode` 출력 |
| 260자 경로 제한 | 긴 경로 지원은 관리자가 그룹 정책이나 레지스트리 `LongPathsEnabled`를 켜야 한다(출처 1). 심사위원에게 요구할 수 없다. 탐색기 압축 풀기는 그 설정과 상관없이 실패할 수 있다(기억 기반) | 짧은 루트 이름, 매뉴얼 첫 단계로 `C:\EventEffect`에 풀기 권장, 빌드 때 최장 경로 측정, 자가 점검의 빠진 파일 검사 | 자가 점검, 바탕화면에 풀었을 때도 시험 |
| 인터넷에서 받은 파일 표시 | 받은 ZIP에는 Zone.Identifier 정보(값 3은 인터넷에서 받음)가 붙는다(출처 10). 탐색기로 풀면 안의 파일에도 옮겨 붙어 bat 실행 때 보안 경고가 뜬다(기억 기반) | 매뉴얼에 "압축 풀기 전 ZIP 속성에서 차단 해제" 화면 캡처와, 경고가 뜨면 누를 버튼을 넣는다 | 11/15에 ZIP을 실제로 인터넷 경로(클라우드 드라이브)로 옮겨 받아 시험 |
| 한글·공백 설치 경로 | 사용자 이름이 한글이거나 바탕화면이 OneDrive의 `바탕 화면` 폴더로 옮겨져 있으면 경로에 한글과 공백이 들어간다(기억 기반) | bat의 모든 경로를 따옴표로 감싸고, 판별은 selfcheck.py가 한다 | 11/15에 한글·공백 폴더에 풀어 시험 |
| 포트 충돌 | 다른 참가작이 8501을 쓰고 있으면 시작 실패 또는 남의 화면이 열린다(추정) | 4-2절의 앱 표시 값 확인과 포트 변경 | 11/19에 포트를 미리 점유해 시험 |
| 콘솔 선택 멈춤 | 예전 콘솔 창에서 마우스로 글자를 선택하면 출력이 멈추고, 출력하려던 서버가 같이 멈춘다(기억 기반). 윈도우 11 기본 터미널에서는 다를 수 있다(추정) | 콘솔 출력을 최소로 하고, 매뉴얼에 "창 제목에 '선택'이 보이면 Esc"를 적는다 | 11/19에 창을 클릭한 뒤 화면 반응 확인 |
| 방화벽 창 | 127.0.0.1에만 열면 뜨지 않는다(기억 기반) | 지금 코드 유지 | 11/15에 뜨는지 확인 |
| Defender 실시간 검사 | 첫 실행 때 파일 수천 개를 검사해 시작이 느리다(추정) | install.bat 자가 점검이 import를 한 번 해 두어 첫 화면 대기를 줄인다 | 11/15에 install과 첫 run 시간 측정 |
| 경로 구분자와 SQL | 문자열로 경로를 이어 붙이면 깨진다. DuckDB SQL에 경로를 문자열로 끼우면 폴더 이름의 작은따옴표에서 SQL이 깨진다 | `pathlib`만 쓰고, DuckDB에는 파이썬 API나 매개변수로 경로를 넘긴다 | 자가 점검의 한글 경로 CSV 읽기 |
| 콘솔 인코딩 | bat 안의 한글은 깨진다(22번 6절 2번). Python 출력은 콘솔 API로 쓰여 한글이 보인다(기억 기반) | bat은 영문만, 콘솔 안내도 영문, 한글 안내는 브라우저 화면에 | 11/15 화면 확인 |
| 엑셀로 다시 저장한 CSV | 심사위원이 CSV를 엑셀로 열었다 저장하면 인코딩이 CP949나 BOM 붙은 UTF-8로 바뀐다(기억 기반) | 엔진이 UTF-8, BOM 붙은 UTF-8, CP949 순으로 읽고 어떤 인코딩으로 읽었는지 화면에 표시한다(엔진 설계에 전달) | 엔진 시험 |
| 글꼴 | 맥에는 맑은 고딕이 없고, 윈도우 시스템 글꼴에 기대면 맥과 결과가 달라진다 | 8절대로 글꼴 동봉 | png 비교 |
| 시간대 | 윈도우에는 IANA 시간대 자료가 없다 | `tzdata` 패키지가 의존성으로 이미 들어 있다(0절). 그래도 날짜는 시간대 없이 다룬다 | 해당 없음 |

---

## 7. 11/15 1차 윈도우 시험

11/15에는 다른 공모전 마감 때문에 약 2시간밖에 없다. 그래서 묶음은 11/14에 맥에서 다 만들어 두고, 11/15에는 시험과 기록만 한다.

### 7-1. 최소 묶음의 내용

- `python\`: embeddable 3.11.9와 `._pth` 수정, 잠금 파일 40개 패키지 전부(나중에 쓸 패키지까지 지금 시험한다).
- `app\server.py`: 지금의 빈 화면 서버에 4-2절의 이미 실행 중 확인과 브라우저 열기만 더한 것.
- `app\selfcheck.py`: 아래 7-3절 항목.
- `app\fonts\`: 한글 TTF 하나와 라이선스 파일.
- `app\data\sample\`: 가상 카드 CSV 한 달치(영문 파일 이름).
- install.bat, run.bat, `manifest.txt`.

### 7-2. 맥에서 만드는 단계 (11/14)

1. 2-1절 명령으로 해석하고 `requirements-lock.txt`를 만든다. 확인: 40줄, 맥 venv `pip freeze`와 같음.
2. python.org에서 `python-3.11.9-embed-amd64.zip`(11.2MB)을 받아 `build/EventEffect/python/`에 푼다. 확인: `python311._pth`가 있다. 3-3절대로 고친다.
3. 2-3절 명령으로 site-packages를 만들고 `bin/`을 지운다. 확인: `.pyd`가 있고 `.so`가 0개.
4. (선택) 2-4절로 .pyd의 DLL 목록을 본다.
5. 앱 파일을 목록대로 복사하고 bat 두 개를 CRLF로 저장한다. 확인: `file *.bat`가 CRLF를 보고한다.
6. 파일 목록과 최장 경로 길이, 파일 수를 `manifest.txt`에 쓴다.
7. Python `zipfile`로 NFC 이름의 ZIP을 만든다. 확인: `python3 -m zipfile -l`로 이름이 영문이고 `.env`가 없다.
8. ZIP을 클라우드 드라이브에 올린다. 시험 PC에서는 그것을 내려받아, 실제 심사처럼 인터넷에서 받은 파일 표시가 붙게 한다.

이 단계 전체를 하나의 빌드 스크립트(표준 라이브러리만, `tools/build_windows_zip.py`)로 만든다. 11/19에도 같은 스크립트를 다시 돌리기 때문이다. 작성에 1~2시간을 잡는다(추정).

### 7-3. selfcheck.py가 확인하는 항목

1. `sys.version`이 3.11.9이고, `sys.flags.utf8_mode`가 1이며, `sys.path`가 3-3절의 경로뿐이다.
2. `manifest.txt`의 파일이 모두 있다.
3. fastapi, uvicorn, pydantic_core, duckdb, pandas, numpy, matplotlib, fpdf, anthropic, httpx, openpyxl이 import된다. 실패하면 예외 메시지(DLL 이름 포함)를 그대로 출력한다.
4. 동봉 글꼴로 한글 제목 png 하나와 한글 PDF 한 쪽을 `out`에 만든다.
5. `out\selfcheck\바탕 화면 요청파일\` 폴더(한글과 공백)를 코드에서 만들고, 샘플 CSV를 `카드_2024-07.csv`라는 한글 이름으로 복사한 뒤 DuckDB(모든 열을 문자열로)와 pandas로 각각 읽어 행 수가 같은지 본다. 한글 이름을 ZIP에 넣지 않고 실행 중에 만드는 이유는 맥 ZIP의 자모 분리 문제를 피하면서 실제 센터 상황(바탕화면 요청파일 폴더)을 흉내 내기 위해서다.
6. 설치 경로가 영문인지, 공백이 있는지, 길이가 얼마인지 출력한다.

### 7-4. 윈도우에서 하는 순서와 기록 (11/15, 약 40분 추정)

1. 시험 PC 상태를 기록한다: 윈도우 판, 스마트 앱 컨트롤 켜짐 여부, Defender 실시간 보호, Python 설치 여부(`where python`), 사용자 이름에 한글이 있는지.
2. 받은 ZIP의 속성에서 차단 해제를 하지 않은 채로 `C:\EventEffect`에 푼다. 압축 풀기 시간을 잰다.
3. install.bat 더블클릭. 뜨는 경고 창을 모두 캡처한다. 자가 점검 시간을 잰다.
4. run.bat 더블클릭. 방화벽 창이 뜨는지, 브라우저가 열리는지, 빈 화면이 나오는지 본다.
5. run.bat을 한 번 더 더블클릭한다. 브라우저만 열리고 새 서버가 뜨지 않아야 한다.
6. 검은 창을 닫고 브라우저를 새로 고쳐 서버가 멈췄는지 본다.
7. 같은 ZIP을 한글과 공백이 든 폴더(예: 바탕화면의 `행사 효과 시험`)에 풀어 3~6을 반복한다.
8. PowerShell에서 `Get-AuthenticodeSignature python\python.exe`로 서명을 확인한다.

완료 기준: 두 위치 모두 자가 점검 항목 전부 PASS, 빈 화면 표시, 두 번째 실행에서 서버 중복 없음, 창을 닫으면 서버 종료. 경고 창 캡처는 매뉴얼에 그대로 쓴다. 실패한 항목은 오류 문구와 함께 기록하고 11/16 첫 작업으로 고친다.

시험 PC를 11/15까지 구하지 못하면 GitHub Actions 윈도우 실행기에서 install.bat을 돌려 import와 한글 경로 항목만 확인한다. 화면, 경고 창, 스마트 앱 컨트롤은 확인하지 못하므로 11/19 실제 PC 시험이 더 중요해진다.

---

## 8. 맥과 윈도우 결과를 같게 하는 원칙

1. **동작은 Python 코드에, bat에는 실행만.** 브라우저 열기, 그래프 백엔드, 캐시 폴더, 포트, 경로 판단은 모두 코드에 둔다. 맥에서 `python -X utf8 app/server.py`로 돌린 것과 윈도우에서 run.bat으로 돌린 것이 같은 코드를 지나게 된다.
2. **같은 버전.** 2-2절의 잠금 파일 하나로 맥 venv와 윈도우 site-packages를 만든다.
3. **글꼴 동봉.** 한글 TTF 하나를 ZIP에 넣고 matplotlib과 fpdf2에 파일 경로로 등록한다. 시스템 글꼴은 찾지 않는다. matplotlib의 마이너스 기호 글꼴 깨짐을 막는 설정도 함께 둔다. 브라우저 화면도 같은 파일을 `@font-face`로 불러 기획서 캡처가 맥과 윈도우에서 같게 한다. 나눔고딕과 Noto Sans KR 중 무엇을 쓸지는 라이선스 파일을 확인해 정한다(둘 다 OFL로 기억하나 확인하지 않았다).
4. **인코딩 명시.** 모든 `open()`에 `encoding`을 쓴다. 출력 텍스트 파일은 `newline="\n"`으로 써서 두 OS의 바이트가 같게 한다.
5. **줄바꿈.** bat만 CRLF로 바꿔 넣고 확인한다. 빌드 스크립트가 bat을 CRLF로 바꾸고 다른 파일은 그대로 둔다.
6. **정렬.** 파일 목록은 항상 `sorted()`로 정렬한다. 폴더를 읽는 순서는 OS마다 다를 수 있다. 한글 정렬은 코드 포인트 기준(Python 기본, DuckDB 기본)으로 하고 로캘 정렬 함수를 쓰지 않는다. SQL 결과는 `ORDER BY`를 빠짐없이 붙인다.
7. **숫자.** 화면과 보고서에 쓰는 값은 정한 자릿수로 반올림한 뒤 쓴다. 부동소수점 끝자리는 CPU와 라이브러리 경로에 따라 달라질 수 있다(추정). 숫자 서식은 f-string으로 하고 로캘 서식을 쓰지 않는다.
8. **날짜 문자열.** 한글이 든 날짜는 `strftime`에 한글을 넣지 않고 f-string(`f"{d.year}년 {d.month}월"`)으로 만든다. 윈도우의 `strftime`이 비영문 서식에서 문제를 낸 적이 있다(기억 기반).
9. **결과 대조.** "예시로 해 보기"를 맥에서 돌려 반올림한 결과 요약 JSON을 만들어 ZIP에 넣고, 11/19 윈도우 시험에서 같은 실행 결과와 바이트 단위로 비교한다. png는 같은 matplotlib, 같은 글꼴, 같은 dpi면 같아질 것으로 추정하고 눈으로 비교한다. PDF는 생성 시각이 들어가 바이트가 다르므로 본문 글자만 비교한다.

---

## 9. 만들지 않을 것

- 설치 프로그램(.msi, NSIS, Inno Setup), PyInstaller나 Nuitka 실행 파일, 코드 서명 인증서 구매.
- 윈도우에서의 pip 설치, venv 생성, 인터넷 패키지 다운로드. uv(ADR-149로 제외).
- 레지스트리 변경(긴 경로 설정 포함), 관리자 권한 요구, PATH 변경, 바탕화면 바로 가기, 윈도우 서비스 등록.
- stop.bat(창 닫기로 충분), 포트 자동 선택(고정 포트와 안내 문구로 충분), 자동 업데이트.
- PowerShell 스크립트(실행 정책 때문에 막힐 수 있다, 기억 기반). 매뉴얼에서 서명 확인용 한 줄만 시험자용으로 쓴다.
- 32비트, ARM64 윈도우용 묶음(센터 PC는 i7-8700, x64).
- 맥과 윈도우 이중 지원 실행 스크립트. 맥은 개발용으로 `python -X utf8 app/server.py`만 쓴다.
- GitHub Actions 상시 자동 시험(7-4절의 대체 수단으로만, 시험 PC가 없을 때 한 번).

---

## 10. 다른 설계와 맞물리는 지점

다른 설계자에게 전달할 요구다. 모두 구현 단계에서 반영하며 지금 코드는 고치지 않았다.

- 화면·서버 설계: 포트를 8501에서 덜 쓰이는 번호로 바꾸고, `/api/health`에 앱 표시 값을 넣고, 이미 실행 중 확인과 브라우저 열기를 `server.py`에 넣는다. 종료 코드 3을 "이미 실행 중"으로 쓴다.
- 엔진 설계: 파일 경로는 `pathlib`, DuckDB에는 매개변수로 경로를 넘긴다. 모든 열을 문자열로 읽는다. CSV 인코딩은 UTF-8, BOM 붙은 UTF-8, CP949 순으로 시도하고 화면에 표시한다. `matplotlib.use("Agg")`와 `MPLCONFIGDIR`을 코드에서 지정한다.
- 보안·반출 설계: 평가용 키를 어디에 둘지 정해 주면 빌드 스크립트의 포함 목록에 반영한다. 개발 `.env`는 어떤 경우에도 ZIP에 넣지 않는다.
- 일정: 11/14에 빌드 스크립트와 자가 점검을 만들고(1~2시간 추정), 11/15에 시험(약 40분 추정), 11/19에 같은 스크립트로 최종 묶음을 다시 만들어 7-4절과 8절 9번 대조를 한다.

---

## 출처

1. Python 3.11 문서 「Using Python on Windows」의 embeddable package, MAX_PATH 제한 해제, UTF-8 모드 절: https://docs.python.org/3.11/using/windows.html (원문은 cpython 3.11 브랜치 `Doc/using/windows.rst`로 읽었다)
2. Python 3.11 문서 「The initialization of the sys.path module search path」의 `._pth` files 절: https://docs.python.org/3.11/library/sys_path_init.html
3. Python 3.11.9 공지("3.11의 마지막 버그 수정 판"): https://www.python.org/downloads/release/python-3119/ , Python 3.11.13 공지("보안 수정만, 2027년 10월까지 소스 형태로만"): https://www.python.org/downloads/release/python-31113/
4. python.org FTP에 HEAD 요청(2026-11-13): `python-3.11.9-embed-amd64.zip` 200(11,249,023바이트), `python-3.11.13-embed-amd64.zip` 404, `python-3.13.9-embed-amd64.zip` 200. 주소 형식 https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
5. pip 문서 「pip download」(26.3판) 옵션 설명: https://pip.pypa.io/en/stable/cli/pip_download/
6. 2026-11-13에 실행한 `pip install --dry-run --report`(pip 24.0, 위 2-1절 명령)와 PyPI JSON API(https://pypi.org/pypi/{이름}/json)로 확인한 버전과 휠 크기.
7. python-build-standalone 릴리스 API(태그 20261110): https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest , install_only 설명: https://github.com/astral-sh/python-build-standalone/blob/main/docs/distributions.rst
8. PyInstaller 문서 「Supporting Multiple Operating Systems」: https://pyinstaller.org/en/stable/usage.html#supporting-multiple-operating-systems
9. 마이크로소프트 「Smart App Control Frequently Asked Questions」: https://support.microsoft.com/en-gb/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions , 개요(검색 요약만 봄): https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/overview , 서명 없는 DLL이 막혔다는 사용자 보고(검색 요약만 봄): https://github.com/duplicati/duplicati/issues/4915
10. PowerShell 문서 「Unblock-File」(5.1, Zone.Identifier 값 3 설명): https://learn.microsoft.com/powershell/module/microsoft.powershell.utility/unblock-file

조사 범위의 한계: 다음은 이번에 확인하지 않았고 본문에 "기억 기반" 또는 "추정"으로 표시했다. python.org 윈도우 바이너리의 서명 여부, python-build-standalone 바이너리의 서명 여부, embeddable zip 안의 vcruntime DLL 목록과 `._pth` 원래 내용, macOS `objdump`의 PE 지원, 127.0.0.1 바인딩과 방화벽 창의 관계, 탐색기 압축 풀기의 Zone.Identifier 전파와 260자 제한, 콘솔 선택 멈춤, Visual C++ 런타임 앱 폴더 배포 허용 범위, 글꼴 라이선스, 푼 뒤 크기와 파일 수. 큰 파일은 내려받지 않았다(embeddable zip 포함). 모두 11/15 시험이나 11/14 빌드에서 확인한다.
