"""결과물: 빈칸 채우기, 그림(png), PDF 최소판, 활용 사유 문안, 계획 묶음 저장, 반출 폴더 점검.

반출 파일에는 증가율·상대 효과·지수·개수만 넣고 원래 금액·건수·인원과 합계는 넣지 않는다.
"""
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

import config

LIMITS = [
    "이 결과는 비교 읍면 대비 차이이며, 행사가 소비를 늘렸다는 인과 효과를 증명하지 않습니다.",
    "카드 자료가 월 단위라 행사 기간이 짧으면 효과가 한 달 합계에 묻힐 수 있습니다.",
    "카드 이용 현황은 특정 카드사 자료와 실소유자 기준 집계라 전체 소비를 대표하지 않을 수 있습니다.",
    "이 결과는 공식 통계가 아니라 분석 참고 자료입니다.",
    "매년 열리는 축제는 작년 같은 달에도 효과가 있어, 전년 같은 달 대신 행사 직전 3개월을 기준으로 삼았습니다.",
    "행사 방문객이 옆 읍면에서도 소비하면 비교 읍면도 함께 늘어 차이가 작게 나올 수 있습니다.",
    "공개 방문 인구는 내국인의 시간대별 인구를 더한 연인원이라 실제 방문자 수와 다릅니다.",
    "행사 전 3개월의 흐름이 나란했다는 것이 행사 뒤에도 나란했으리라는 보장은 아닙니다.",
    "같은 시기 다른 행사의 제외와 기준 기간 오염 판정은 행사 파일에 있는 행사만 봅니다.",
]
NOT_COMPUTED = {
    "no_comparison": "행사 전 흐름이 나란한 비교 읍면을 찾지 못해",
    "small_cells": "작은 칸을 업종 전체로 묶어도 10 미만이 남아",
    "too_few_candidates": "비교할 수 있는 읍면이 부족해",
    "few_placebo": "행사가 없던 달이 부족해 평소 흔들림을 잴 수 없어",
}
KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic"]
# 윈도우는 맑은 고딕. 맥 개발 PC의 AppleGothic.ttf는 OS/2 표가 없어 fpdf2가 못 읽으므로 Arial Unicode를 쓴다
FONT_FILES = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf",
              Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")]
EXPORT_SUFFIXES = {".png", ".pdf", ".json"}
BLANK = re.compile(r"\{\{([^}]*)\}\}")


def pct(x):
    return f"{x * 100:+.1f}%"


def period(start, end):
    if start.year == end.year:
        return f"{start.year}년 {start.month}월 {start.day}일~{end.month}월 {end.day}일"
    return f"{start.year}년 {start.month}월 {start.day}일~{end.year}년 {end.month}월 {end.day}일"


def month_span(months):
    a, b = months[0], months[-1]
    if a[:4] == b[:4]:
        return f"{a[:4]}년 {int(a[4:])}~{int(b[4:])}월" if a != b else f"{a[:4]}년 {int(a[4:])}월"
    return f"{a[:4]}년 {int(a[4:])}월~{b[:4]}년 {int(b[4:])}월"


def values(event, emd, result, months):
    v = {
        "행사_이름": event["name"], "행사_읍면": emd,
        "행사_기간": period(event["start"], event["end"]), "기준_기간": month_span(months["base"]),
        "비교_읍면": result.get("emd", ""), "차이": pct(result["E"]) if "E" in result else "",
        "계산_못한_이유": NOT_COMPUTED.get(result.get("reason"), "계산 조건을 채우지 못해"),
    }
    return v


def fill(template, vals):
    text = BLANK.sub(lambda m: str(vals[m.group(1)]), template)
    if "{{" in text or "}}" in text:
        raise ValueError("unfilled blank")
    return text


def strength(result):
    j, n = result.get("J"), result.get("n")
    if result["outcome"] in ("higher", "lower"):
        return f"행사가 없던 {j}개 달에 같은 계산을 했을 때 이번보다 큰 차이는 {n}번이었습니다."
    if result["outcome"] == "no_difference":
        return f"행사가 없던 {j}개 달에 같은 계산을 했을 때 이번만큼 큰 차이가 {n}번 나왔습니다. 평소에도 이 정도 차이는 생깁니다."
    return ""


def usage_reason(event, months_all, target):
    return (f"AI Agent 「행사 효과 나란히」(Python)의 이중차분 분석으로 분석 후, 읍면별 관광객 카드 이용 증가율 산출과 "
            f"인원·건수 10 미만 칸의 업종 묶음(범주처리)으로 가공하여, {event['name']}({period(event['start'], event['end'])}) "
            f"개최 읍면과 비교 읍면의 관광객 카드 이용 증가율 차이에 관한 보고서 작성 및 {target}에 활용. "
            f"출처: 제주빅데이터센터, 카드 이용 현황(읍면동)_v02({month_span(months_all)}), 파일 구분: 분석결과")


def _plt():
    os.environ.setdefault("MPLCONFIGDIR", str(config.out_path("cache", "x").parent))
    import matplotlib

    matplotlib.use("Agg")
    import logging

    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    names = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = next((f for f in KOREAN_FONTS if f in names), "sans-serif")
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def index_chart(t, c, months, emd, comp, path, example):
    """두 읍면의 달별 지수(기준 기간 평균 = 100). 원래 금액은 그리지 않는다."""
    plt = _plt()
    shown = sorted(set(months["pretrend"] + months["base"] + months["excluded"] + months["event"]))
    base_t = sum(t[m] for m in months["base"]) / len(months["base"])
    base_c = sum(c[m] for m in months["base"]) / len(months["base"])
    labels = [f"{m[2:4]}.{m[4:]}" for m in shown]
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=150)
    for m in months["event"]:
        i = shown.index(m)
        ax.axvspan(i - 0.5, i + 0.5, color="#1f6273", alpha=0.10, lw=0)
    ax.plot(labels, [t[m] / base_t * 100 for m in shown], color="#1f6273", lw=2.2, marker="o", ms=4, label=f"{emd}(행사 읍면)")
    ax.plot(labels, [c[m] / base_c * 100 for m in shown], color="#7a8288", lw=1.6, marker="o", ms=3, label=f"{comp}(비교 읍면)")
    ax.axhline(100, color="#c9d0d4", lw=1)
    ax.set_ylabel("지수(기준 기간 평균 = 100)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    if example:
        ax.text(0.99, 0.97, "예시(가상 데이터)", transform=ax.transAxes, ha="right", va="top", fontsize=9, color="#a2421f")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def visit_chart(days_t, days_c, start, end, emd, comp, path):
    """공개 유동인구 날짜별 방문 지수(행사 직전 4주 평균 = 100)."""
    plt = _plt()
    first, last = start - dt.timedelta(days=28), end + dt.timedelta(days=10)
    dates = [first + dt.timedelta(n) for n in range((last - first).days + 1)]

    def index(days):
        base = [days[d] for d in dates[:28] if d in days]
        mean = sum(base) / len(base)
        return [days[d] / mean * 100 if d in days else None for d in dates]

    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=150)
    ax.axvspan(start, end, color="#1f6273", alpha=0.10, lw=0)
    ax.plot(dates, index(days_t), color="#1f6273", lw=2, label=f"{emd}(행사 읍면)")
    if days_c:
        ax.plot(dates, index(days_c), color="#7a8288", lw=1.4, label=f"{comp}(비교 읍면)")
    ax.axhline(100, color="#c9d0d4", lw=1)
    ax.set_ylabel("방문 지수(직전 4주 평균 = 100)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    import matplotlib.dates as mdates

    # %-m은 윈도우 strftime에서 쓸 수 없어 직접 만든다
    ax.xaxis.set_major_formatter(lambda x, _: f"{mdates.num2date(x).month}/{mdates.num2date(x).day}")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def evidence_rows(result, biz_size):
    if result["outcome"] == "not_computed":
        return [("결과", "계산하지 못함"), ("시도한 비교 읍면", ", ".join(x["emd"] for x in result.get("tried", [])) or "없음")]
    return [
        ("비교 읍면", result["emd"]),
        ("상대 효과", pct(result["E"])),
        ("증가율 차이", f"{result['delta'] * 100:+.1f}%p"),
        ("행사 전 흐름 차이 / 기준(평소 흔들림의 2배)", f"{pct(result['L'])} / ±{result['sigma'] * 200:.1f}%"),
        ("행사 없던 달 수 / 이번보다 큰 차이", f"{result['J']}개 / {result['n']}번"),
        ("p값", f"{result['p']:.3f}"),
        ("업종 범위", f"{biz_size}개 업종"),
    ]


def pdf(path, title, sentence, images, rows, ai_rows, limits):
    from fpdf import FPDF

    font = next((f for f in FONT_FILES if f.exists()), None)
    if font is None:
        raise RuntimeError("no_korean_font")
    doc = FPDF(format="A4")
    doc.set_margins(18, 16, 18)
    doc.add_page()
    doc.add_font("K", fname=str(font))
    doc.set_font("K", size=16)
    doc.multi_cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
    doc.ln(2)
    doc.set_font("K", size=11)
    doc.multi_cell(0, 6.5, sentence, new_x="LMARGIN", new_y="NEXT")
    for img in images:
        doc.ln(2)
        doc.image(str(img), w=170)
    doc.ln(3)
    for heading, table in (("계산 근거", rows), ("AI가 정한 것과 이유", ai_rows)):
        doc.set_font("K", size=12)
        doc.multi_cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
        doc.set_font("K", size=9)
        for k, v in table:
            doc.multi_cell(0, 5.5, f"· {k}: {v}", new_x="LMARGIN", new_y="NEXT")
        doc.ln(2)
    doc.set_font("K", size=12)
    doc.multi_cell(0, 8, "한계", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("K", size=9)
    for line in limits:
        doc.multi_cell(0, 5.5, f"· {line}", new_x="LMARGIN", new_y="NEXT")
    doc.output(str(path))


def save_bundle(bundle):
    data = json.dumps(bundle, ensure_ascii=False, sort_keys=True, default=str, indent=1)
    finger = hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]
    path = config.out_path("report", f"{dt.datetime.now():%Y%m%d_%H%M%S}_plan.json")
    path.write_text(data, encoding="utf-8")
    return path, finger


def export_check(folder):
    """반출 폴더에는 png·pdf·json만 있어야 한다."""
    return sorted(p.name for p in Path(folder).iterdir() if p.is_file() and p.suffix not in EXPORT_SUFFIXES)
