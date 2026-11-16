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

# 화면(app/static/tokens.css)과 같은 색: 행사 읍면은 감귤, 비교 읍면은 돌 회색, 행사 달은 유채 띠(ADR-171)
INK, INK_2, MUTED, RULE = "#2f353b", "#3e454c", "#5e666d", "#dde0e3"
PAPER_2, PAPER_3, ACCENT, ACCENT_SOFT, ACCENT_SOFT_INK = "#f4f5f6", "#e9ebed", "#b85a0e", "#fdebdb", "#7a3a06"
EVENT, COMPARE, CANOLA_SOFT = "#ee7f1b", "#8a939a", "#fcf1c6"
OUTCOME_LABEL = {"higher": "평소엔 드문 차이", "lower": "평소엔 드문 차이",
                 "no_difference": "평소에도 생기는 차이", "not_computed": "계산하지 못함"}

LIMITS = [
    "이 결과는 비교 읍면 대비 차이이며, 행사가 소비를 늘렸다는 인과 효과를 증명하지 않는다.",
    "카드 자료가 월 단위라 행사 기간이 짧으면 효과가 한 달 합계에 묻힐 수 있다.",
    "카드 이용 현황은 특정 카드사 자료와 실소유자 기준 집계라 전체 소비를 대표하지 않을 수 있다.",
    "이 결과는 공식 통계가 아니라 분석 참고 자료다.",
    "매년 열리는 축제는 작년 같은 달에도 효과가 있어, 전년 같은 달 대신 행사 직전 3개월을 기준으로 삼았다.",
    "행사 방문객이 옆 읍면에서도 소비하면 비교 읍면도 함께 늘어 차이가 작게 나올 수 있다.",
    "공개 방문 인구는 내국인의 시간대별 인구를 더한 연인원이라 실제 방문자 수와 다르다.",
    "행사 전 3개월의 흐름이 나란했다는 것이 행사 뒤에도 나란했으리라는 보장은 아니다.",
    "같은 시기 다른 행사의 제외와 기준 기간 오염 판정은 행사 파일에 있는 행사만 본다.",
]
NOT_COMPUTED = {
    "no_comparison": "행사 전 흐름이 나란한 비교 읍면을 찾지 못해",
    "small_cells": "작은 칸을 업종 전체로 묶어도 10 미만이 남아",
    "too_few_candidates": "비교할 수 있는 읍면이 부족해",
    "few_placebo": "행사가 없던 달이 부족해 평소 흔들림을 계산할 수 없어",
    "missing_files": "필요한 달의 카드 파일이나 행사 읍면 자료가 없어",
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


JOSA = {"이": ("이", "가"), "가": ("이", "가"), "은": ("은", "는"), "는": ("은", "는"), "을": ("을", "를"),
        "를": ("을", "를"), "과": ("과", "와"), "와": ("과", "와"), "으로": ("으로", "로"), "로": ("으로", "로")}
# 숫자는 읽는 소리의 받침으로: 영·일·삼·육·칠·팔은 받침이 있다
DIGIT_FINAL = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True, "8": True, "9": False}
BLANK_JOSA = re.compile(r"\{\{([^}]*)\}\}(으로|이|가|은|는|을|를|과|와|로)?")


def _has_final(text):
    last = text.rstrip()[-1:] or "가"
    if "가" <= last <= "힣":
        return (ord(last) - 0xAC00) % 28 != 0
    return DIGIT_FINAL.get(last, False)  # %는 '퍼센트'라 받침 없음


def fill(template, vals):
    """빈칸을 채우고, 빈칸 바로 뒤 조사를 채운 값의 받침에 맞춘다(가파도청보리축제가, 성산읍이)."""
    def sub(m):
        value = str(vals[m.group(1)])
        josa = m.group(2)
        if not josa:
            return value
        with_final, without = JOSA[josa]
        return value + (with_final if _has_final(value) else without)

    text = BLANK_JOSA.sub(sub, template)
    if "{{" in text or "}}" in text:
        raise ValueError("unfilled blank")
    return text


def strength(result):
    j, n = result.get("J"), result.get("n")
    if result["outcome"] in ("higher", "lower"):
        return f"행사가 없던 {j}개 달에 같은 계산을 했을 때 이번보다 큰 차이는 {n}번이었다."
    if result["outcome"] == "no_difference":
        return f"행사가 없던 {j}개 달에 같은 계산을 했을 때 이번만큼 큰 차이가 {n}번 나왔다. 평소에도 이 정도 차이는 생긴다."
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


def _quiet_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(RULE)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.label.set_color(MUTED)


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
        ax.axvspan(i - 0.5, i + 0.5, color=CANOLA_SOFT, lw=0)
    # 색을 못 가려도 구분되게 비교 읍면은 점선
    ax.plot(labels, [t[m] / base_t * 100 for m in shown], color=EVENT, lw=2.6, marker="o", ms=4.5, label=f"{emd}(행사 읍면)")
    ax.plot(labels, [c[m] / base_c * 100 for m in shown], color=COMPARE, lw=1.8, ls="--", marker="o", ms=3.5, label=f"{comp}(비교 읍면)")
    ax.axhline(100, color=RULE, lw=1)
    ax.set_ylabel("지수(기준 기간 평균 = 100)")
    # 범례는 그림 테두리 위 왼쪽: 그림 안에 두면 첫 달의 점이나 선을 가린다
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, borderaxespad=0.2)
    _quiet_axes(ax)
    if example:
        # 그림 테두리 위에 두어 어떤 행사의 꺾은선과도 겹치지 않게 한다
        ax.text(1.0, 1.01, "예시(가상 데이터)", transform=ax.transAxes, ha="right", va="bottom", fontsize=9, color=MUTED)
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
    ax.axvspan(start, end, color=CANOLA_SOFT, lw=0)
    ax.plot(dates, index(days_t), color=EVENT, lw=2.2, label=f"{emd}(행사 읍면)")
    if days_c:
        ax.plot(dates, index(days_c), color=COMPARE, lw=1.4, ls="--", label=f"{comp}(비교 읍면)")
    ax.axhline(100, color=RULE, lw=1)
    ax.set_ylabel("방문 지수(직전 4주 평균 = 100)")
    # 범례는 그림 테두리 위 왼쪽: 그림 안에 두면 첫 달의 점이나 선을 가린다
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, borderaxespad=0.2)
    _quiet_axes(ax)
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


def _j(word, with_final, without):
    return word + (with_final if _has_final(word) else without)


def headline(emd, result):
    """결론 한 줄. 숫자는 계산 결과에서만 채운다."""
    comp, out = result.get("emd"), result["outcome"]
    if out == "not_computed":
        return f"{NOT_COMPUTED.get(result.get('reason'), '계산 조건을 채우지 못해')} 계산하지 못했다"
    size = f"{abs(result['E']) * 100:.1f}%"
    if out == "higher":
        return f"{emd}의 관광 소비가 {comp}보다 {size} 더 늘었다"
    if out == "lower":
        return f"{emd}의 관광 소비가 {comp}보다 {size} 덜 늘었다"
    return f"{_j(emd, '과', '와')} {comp}의 차이는 평소에도 생기는 크기였다"


def key_figures(result):
    if result["outcome"] == "not_computed":
        return []
    return [("상대 효과", pct(result["E"])), ("p값", f"{result['p']:.3f}"),
            ("행사 없던 달 가운데 이번보다 큰 차이", f"{result['n']}번 / {result['J']}개 달")]


def method_steps(result, months, emd):
    comp = result.get("emd")
    if result["outcome"] == "not_computed":
        tried = ", ".join(x["emd"] for x in result.get("tried", [])) or "없음"
        return [("시도한 비교 읍면", f"{tried}. {NOT_COMPUTED.get(result.get('reason'), '계산 조건을 채우지 못해')} 결과를 내지 않았다.")]
    ok = "기준 안이었다" if abs(result["L"]) <= 2 * result["sigma"] else "기준 밖이었다"
    strong = "기준 0.1 이하" if result["p"] <= 0.1 else "기준 0.1보다 큼"
    return [
        ("증가율 비교", f"행사 달({month_span(months['event'])}) 관광 소비를 기준 기간({month_span(months['base'])}) 평균과 견줘 "
                    f"증가율을 구했다. {emd} {pct(result['g_t'])}, {comp} {pct(result['g_c'])}, 상대 효과 {pct(result['E'])}."),
        ("행사 전 흐름 확인", f"행사 전 3개월({month_span(months['pretrend'])})에도 같은 계산을 해 두 읍면이 나란히 움직였는지 봤다. "
                       f"차이 {pct(result['L'])}로 평소 흔들림의 2배(±{result['sigma'] * 200:.1f}%) {ok}."),
        ("평소 차이 확인", f"행사가 없던 {result['J']}개 달을 가짜 행사 달로 두고 같은 계산을 했다. "
                     f"이번보다 큰 차이는 {result['n']}번, p값 {result['p']:.3f}({strong})."),
    ]


def build_report(event, emd, result, months, bundle, sentence, evidence, ai_rows, biz_size):
    """화면과 PDF가 같은 순서로 쓰는 보고서: 결론, 상황, 과제, 방법, 결과, 한계와 활용."""
    plan, comp = bundle["plan"], result.get("emd")
    planned = len(plan["biz_codes"]) or 42
    biz = f"{plan.get('biz_bundle') or 'AI가 고른 업종'}({planned}개 업종)"
    if biz_size and biz_size != planned:
        biz += f", 10 미만 칸 때문에 {biz_size}개로 넓힘"
    visit, judged = bundle.get("visit_summary") or {}, bundle["judgement"]["visit"]["judgement"]
    if visit.get("R_T") is not None and visit.get("R_C") is not None:
        judged += f"(행사 읍면 {pct(visit['R_T'])}, 비교 후보 가운데 값 {pct(visit['R_C'])})"
    return {
        "outcome": result["outcome"], "label": OUTCOME_LABEL[result["outcome"]],
        "headline": headline(emd, result), "sentence": sentence, "figures": key_figures(result),
        "situation": [("행사", event["name"]), ("기간", period(event["start"], event["end"])), ("개최 읍면", emd),
                      ("공개 방문 인구", judged)],
        "task": [("물음", f"행사 기간에 {emd}의 관광객 카드 소비가 비교 읍면보다 더 늘었는가"),
                 ("비교 읍면", comp or "정하지 못함"), ("기준 기간", month_span(months["base"])),
                 ("행사 달", month_span(months["event"])), ("업종", biz)],
        "method_ai": bundle["texts"]["method"], "steps": method_steps(result, months, emd),
        "ai": ai_rows, "evidence": evidence,
        "limits_event": bundle["texts"]["extra_limits"], "limits_common": LIMITS,
    }


def _rgb(hexcode):
    return tuple(int(hexcode[i:i + 2], 16) for i in (1, 3, 5))


def pdf(path, title, rep, images, usage):
    """결론 먼저 + STAR 순서의 보고서 PDF. 표는 가로 괘선만 쓴다(ink 테마)."""
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    font = next((f for f in FONT_FILES if f.exists()), None)
    if font is None:
        raise RuntimeError("no_korean_font")
    bold = font.with_name("malgunbd.ttf")

    class Doc(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("K", size=8)
            self.set_text_color(*_rgb(MUTED))
            self.cell(0, 5, f"행사 효과 나란히 분석 보고서   {self.page_no()}/{{nb}}", align="R")

    doc = Doc(format="A4")
    doc.set_margins(18, 16, 18)
    doc.set_auto_page_break(True, 18)
    doc.add_font("K", fname=str(font))
    doc.add_font("K", style="B", fname=str(bold if bold.exists() else font))
    doc.add_page()
    width = doc.w - doc.l_margin - doc.r_margin

    def text(size, value, color=INK_2, style="", h=None):
        doc.set_font("K", style, size)
        doc.set_text_color(*_rgb(color))
        doc.multi_cell(0, h or size * 0.55, value, new_x="LMARGIN", new_y="NEXT")

    def rule(color=INK, w=0.3):
        doc.set_draw_color(*_rgb(color))
        doc.set_line_width(w)
        doc.line(doc.l_margin, doc.get_y(), doc.l_margin + width, doc.get_y())

    def heading(value):
        doc.ln(5)
        text(12.5, value, INK, "B", 7)
        rule()
        doc.ln(1.5)

    def table(rows, first=44):
        doc.set_fill_color(255, 255, 255)  # 판정 표시의 채우기 색이 표 칸에 번지지 않게
        doc.set_font("K", size=9.5)
        doc.set_text_color(*_rgb(INK_2))
        doc.set_draw_color(*_rgb(RULE))
        doc.set_line_width(0.2)
        with doc.table(col_widths=(first, width - first), first_row_as_headings=False, borders_layout="HORIZONTAL_LINES",
                       line_height=5.4, padding=(1.6, 1.5), text_align="LEFT") as t:
            for k, v in rows:
                row = t.row()
                row.cell(k, style=FontFace(color=_rgb(MUTED)))
                row.cell(str(v))

    def bullets(lines, size=9.5, color=INK_2):
        for line in lines:
            text(size, f"- {line}", color, h=size * 0.55)

    text(9, "행사 효과 나란히 분석 보고서", MUTED)
    doc.ln(1)
    text(16, title, INK, "B", 8.5)

    heading("1. 결론")
    label_fill = {"higher": ACCENT_SOFT, "lower": ACCENT_SOFT, "no_difference": PAPER_3}.get(rep["outcome"])
    doc.set_font("K", "B", 9)
    pad = doc.get_string_width(rep["label"]) + 6
    doc.set_text_color(*_rgb(ACCENT_SOFT_INK if label_fill == ACCENT_SOFT else INK))
    if label_fill:
        doc.set_fill_color(*_rgb(label_fill))
        doc.cell(pad, 6, rep["label"], fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        doc.set_draw_color(*_rgb(RULE))
        doc.cell(pad, 6, rep["label"], border=1, align="C", new_x="LMARGIN", new_y="NEXT")
    doc.ln(2)
    text(14, rep["headline"], INK, "B", 7.5)
    doc.ln(1)
    text(10, rep["sentence"], INK_2, h=5.6)
    if rep["figures"]:
        doc.ln(3)
        col = width / len(rep["figures"])
        y = doc.get_y()
        for i, (label, value) in enumerate(rep["figures"]):
            doc.set_xy(doc.l_margin + i * col, y)
            doc.set_font("K", size=8.5)
            doc.set_text_color(*_rgb(MUTED))
            doc.cell(col, 4.5, label)
            doc.set_xy(doc.l_margin + i * col, y + 5)
            doc.set_font("K", "B", 15)
            doc.set_text_color(*_rgb(ACCENT if i == 0 else INK))  # 첫 숫자(상대 효과)는 행사 읍면 몫이라 감귤, 화면과 같게
            doc.cell(col, 8, value)
        doc.set_xy(doc.l_margin, y + 15)

    heading("2. 상황")
    table(rep["situation"])
    heading("3. 과제")
    table(rep["task"])
    heading("4. 방법")
    text(9.5, rep["method_ai"], INK_2, h=5.3)
    doc.ln(1.5)
    table([(f"{i}. {k}", v) for i, (k, v) in enumerate(rep["steps"], 1)])
    doc.ln(2)
    text(10, "AI가 정한 것과 이유", INK, "B", 6)
    table(rep["ai"])
    heading("5. 결과")
    table(rep["evidence"])
    for img in images:
        doc.ln(3)
        doc.image(str(img), w=width)
    heading("6. 한계와 활용")
    if rep["limits_event"]:
        text(10, "이 행사에서 주의할 점", INK, "B", 6)
        bullets(rep["limits_event"])
        doc.ln(2)
    text(10, "모든 결과에 공통인 한계", INK, "B", 6)
    bullets(rep["limits_common"], 8.5, MUTED)
    doc.ln(2)
    text(10, "반출 신청 활용 사유", INK, "B", 6)
    text(9, usage, INK_2, h=5)
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
