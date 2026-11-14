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
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; font-size: 10pt; line-height: 1.6; color: #1a1a1a; }
h1 { font-size: 18pt; margin: 0 0 4pt; }
h1 + p { color: #555; margin-top: 0; }
h2 { font-size: 13pt; border-bottom: 1px solid #999; padding-bottom: 2pt; margin-top: 18pt; break-after: avoid; }
h3 { font-size: 11pt; margin-top: 12pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9pt; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #eee; white-space: nowrap; }
td:first-child { min-width: 3.5em; }
code, pre { font-family: Menlo, Consolas, monospace; font-size: 8.5pt; }
pre { background: #f4f4f4; padding: 6pt 8pt; white-space: pre-wrap; }
"""
# 개인 경로, 키 모양 문자열이 PDF에 들어가면 안 된다
LEAKS = re.compile(r"/Users/|/private/|sk-ant-|mh_02")


def build(md_path):
    body = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    title = re.search(r"<h1>(.*?)</h1>", body).group(1)
    html = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>'
    out = md_path.with_suffix(".pdf")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={out}", page.as_uri()], check=True, capture_output=True)
    text = subprocess.run(["pdftotext", str(out), "-"], check=True, capture_output=True, text=True).stdout
    leaks = sorted(set(LEAKS.findall(text)))
    pages = text.count("\f")
    if leaks:
        out.unlink()
        raise SystemExit(f"{out.name}: 개인 정보 모양 {leaks}, PDF를 지웠다")
    print(f"{out.name} {pages}쪽")


if __name__ == "__main__":
    names = sys.argv[1:]
    paths = [DOCS / f"{n}.md" for n in names] if names else sorted(DOCS.glob("*_ko.md"))
    for path in paths:
        build(path)
