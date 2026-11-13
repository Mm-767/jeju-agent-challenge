"""센터 명세서의 1-08 카드 이용 현황(읍면동)_v02 시트에서 Agent가 쓸 명세 JSON을 만든다."""
import json
import sys
from pathlib import Path

import openpyxl

SHEET = "1-08 카드 이용 현황(읍면동)_v02 "

# 2026-11-06 운영진 정정: 파티션 컬럼은 다운로드 CSV에 들어가지 않는다
PARTITION_COLUMNS = {"pt_year", "pt_month"}

EUP_MYEON = [
    "한림읍", "애월읍", "구좌읍", "조천읍", "한경면", "추자면", "우도면",
    "대정읍", "남원읍", "성산읍", "안덕면", "표선면",
]


def split_note(note):
    return [v.strip() for v in note.split(",")]


def build(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    rows = list(wb[SHEET].iter_rows(values_only=True))

    columns = []
    notes = {}
    for row in rows[9:25]:
        name = row[1]
        notes[name] = row[6]
        if name in PARTITION_COLUMNS:
            continue
        columns.append({"name": name, "ko": row[2], "type": row[3], "note": row[6]})

    spec = {
        "dataset": "카드 이용 현황(읍면동)_v02",
        "spec_no": "1-08",
        "spec_version": "v13 (2026-11-04)",
        "csv_columns": columns,
        "codes": {
            "dstrct_se": [r[1] for r in rows[28:35]],
            "city": split_note(notes["city"]),
            "area_type": split_note(notes["area_type"]),
            "bjd": [r[1] for r in rows[38:111]],
            "biz": {r[5]: r[6] for r in rows[28:70]},
            "user_type": split_note(notes["user_type"]),
            "tour_type": split_note(notes["tour_type"]),
            "age": {str(r[10]): r[11] for r in rows[28:35]},
            "sex": split_note(notes["sex"]),
        },
        "eup_myeon": EUP_MYEON,
    }
    return spec


def check(spec):
    codes = spec["codes"]
    assert len(spec["csv_columns"]) == 14, len(spec["csv_columns"])
    assert len(codes["dstrct_se"]) == 7, codes["dstrct_se"]
    assert len(codes["bjd"]) == 73, len(codes["bjd"])
    assert len(codes["biz"]) == 42, len(codes["biz"])
    assert len(codes["age"]) == 7, codes["age"]
    missing = [e for e in EUP_MYEON if e not in codes["bjd"]]
    assert not missing, missing


if __name__ == "__main__":
    spec = build(sys.argv[1])
    check(spec)
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ok", out, "columns", len(spec["csv_columns"]), "bjd", len(spec["codes"]["bjd"]))
