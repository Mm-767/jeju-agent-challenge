"""docs/*_ko.md를 A4 PDF로 만든다(개발 PC 전용, 묶음에 넣지 않는다).

python3 docs/make_pdf.py [이름 ...]    이름을 안 주면 *_ko.md 전부
필요한 것: python3의 markdown 패키지, Google Chrome, pdftotext(개인 경로·키 검사)
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
@page { size: A4; margin: 18mm 17mm; }
body { font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; font-size: 10pt; line-height: 1.62; color: #24262b; word-break: keep-all; }
h1 { font-size: 26pt; font-weight: 900; letter-spacing: -0.035em; line-height: 1.2; color: #15161a; margin: 0 0 3mm; }
h1 + p { color: #6d7079; margin-top: 0; }
h2 { font-size: 16pt; font-weight: 900; letter-spacing: -0.03em; color: #15161a; margin: 10mm 0 3mm; break-after: avoid; }
h3 { font-size: 11.5pt; font-weight: 800; color: #15161a; margin: 6mm 0 2mm; break-after: avoid; }
strong { color: #15161a; }
li::marker { color: #b85a0e; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9pt; break-inside: auto; }
tr { break-inside: avoid; }
th, td { padding: 2mm 2.5mm; vertical-align: top; text-align: left; border-bottom: 1px solid #dfe1e6; }
th { font-weight: 800; color: #15161a; border-bottom: 2px solid #15161a; white-space: nowrap; }
td:first-child { min-width: 3.5em; }
code, pre { font-family: Menlo, Consolas, monospace; font-size: 8.5pt; }
pre { margin-left: 4mm; white-space: pre-wrap; }
"""
# 개인 경로, 키 모양 문자열이 PDF에 들어가면 안 된다
LEAKS = re.compile(r"/Users/|/private/|sk-ant-|mh_02")


def print_pdf(page, out):
    # 글꼴(Pretendard)을 인터넷에서 받으므로 다 받을 때까지 기다린다
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--print-to-pdf={out}", page.as_uri()], check=True, capture_output=True)


def build(md_path):
    out = md_path.with_suffix(".pdf")
    if md_path.suffix == ".html":  # 기획서: 쪽 나눔과 그림이 든 HTML을 그대로 인쇄
        print_pdf(md_path, out)
    else:
        body = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
        title = re.search(r"<h1>(.*?)</h1>", body).group(1)
        html = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>'
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "doc.html"
            page.write_text(html, encoding="utf-8")
            print_pdf(page, out)
    text = subprocess.run(["pdftotext", str(out), "-"], check=True, capture_output=True, text=True).stdout
    leaks = sorted(set(LEAKS.findall(text)))
    pages = text.count("\f")
    if leaks:
        out.unlink()
        raise SystemExit(f"{out.name}: 개인 정보 모양 {leaks}, PDF를 지웠다")
    print(f"{out.name} {pages}쪽")


if __name__ == "__main__":
    names = sys.argv[1:]
    paths = [DOCS / n if n.endswith(".html") else DOCS / f"{n}.md" for n in names] if names else sorted(DOCS.glob("*_ko.md"))
    for path in paths:
        build(path)
