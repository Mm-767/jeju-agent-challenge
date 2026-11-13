"""센터 「카드 이용 현황(읍면동)_v02」 CSV를 받아 읍면 12곳 관광객 집계를 메모리에 만든다.

집계(table)는 calc.py와 report.py로만 간다. 오류 문구에는 셀 값과 파이썬 예외 문구를 넣지 않는다.
"""
import csv
import io
import json
from pathlib import Path

SPEC = json.loads((Path(__file__).parent / "spec" / "card_v02.json").read_text(encoding="utf-8"))
COLUMNS = [c["name"] for c in SPEC["csv_columns"]]
EUP_MYEON = set(SPEC["eup_myeon"])
TOURIST = {"개별", "단체"}
DIMENSIONS = ("base_year_month", "bjd", "biz_cd", "user_type", "tour_type", "age", "sex")
NUMBERS = ("use_amt", "use_cnt", "user_cnt")

MESSAGES = {
    "excel": "엑셀에서 저장한 파일로 보입니다. 센터에서 받은 원래 파일을 넣어 주세요.",
    "format": "이 파일은 카드 이용 현황(읍면동)_v02 형식이 아닙니다.",
    "duplicate_row": "같은 행이 두 번 들어 있습니다. 센터에서 받은 원래 파일을 넣어 주세요.",
    "duplicate_month": "{months} 자료가 이미 넣은 파일({other})에도 있습니다. 하나만 남기고 다시 넣어 주세요.",
    "empty": "자료가 들어 있지 않은 파일입니다.",
}


def new_table():
    # cells[(읍면, 연월, 업종)] = [이용금액, 이용건수, 이용자수, 빈 숫자 칸 수]
    return {"cells": {}, "files": {}}


def month_label(ym):
    return f"{ym[:4]}년 {int(ym[4:])}월"


def _reject(name, code, **kw):
    return {"name": name, "ok": False, "problem": code, "message": MESSAGES[code].format(**kw), "months": []}


def _number(text):
    text = text.strip()
    if text in ("", "NA"):
        return None
    return int(text)


def ingest(data, name, table):
    """파일 하나를 검사하고, 받을 수 있으면 table에 더한다. 거절하면 table은 그대로다."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _reject(name, "excel")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames or set(COLUMNS) - set(reader.fieldnames):
        return _reject(name, "format")

    cells = {}
    seen = set()
    months = set()
    blanks = 0
    try:
        for row in reader:
            ym = row["base_year_month"].strip()
            if len(ym) != 6 or not ym.isdigit():
                return _reject(name, "format")
            months.add(ym)
            if row["bjd"] not in EUP_MYEON:
                continue
            key = tuple(row[d] for d in DIMENSIONS)
            if key in seen:
                return _reject(name, "duplicate_row")
            seen.add(key)
            if row["tour_type"] not in TOURIST:
                continue
            values = [_number(row[n]) for n in NUMBERS]
            cell = cells.setdefault((row["bjd"], ym, row["biz_cd"]), [0, 0, 0, 0])
            for i, v in enumerate(values):
                if v is not None:
                    cell[i] += v
            if None in values:
                cell[3] += 1
                blanks += 1
    except (ValueError, KeyError, csv.Error):
        return _reject(name, "format")
    if not months:
        return _reject(name, "empty")

    taken = sorted(m for m in months if m in table["files"])
    if taken:
        label = ", ".join(month_label(m) for m in taken)
        return _reject(name, "duplicate_month", months=label, other=table["files"][taken[0]])

    for key, cell in cells.items():
        table["cells"][key] = cell
    for m in months:
        table["files"][m] = name
    return {"name": name, "ok": True, "problem": None, "message": "", "months": sorted(months), "blank_cells": blanks}


def check_coverage(table, months, emds):
    """필요한 달 가운데 파일이 없는 달, 파일은 있지만 읍면 관광객 행이 없는 (달, 읍면)."""
    present = {(emd, ym) for emd, ym, _ in table["cells"]}
    return {
        "missing_months": [m for m in months if m not in table["files"]],
        "missing_rows": [(m, e) for m in months if m in table["files"] for e in emds if (e, m) not in present],
    }


def series(table, emd, biz=None):
    """읍면의 달별 관광객 이용금액. biz가 있으면 그 업종들만."""
    out = {}
    for (e, ym, b), cell in table["cells"].items():
        if e == emd and (biz is None or b in biz):
            out[ym] = out.get(ym, 0) + cell[0]
    return out
