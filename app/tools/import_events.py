"""허브 「제주특별자치도 주요행사정보」 파일(cp949)을 UTF-8 data/hub/events.csv로 옮긴다. event_id는 원본 행 번호."""
import csv
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / "data" / "hub" / "events.csv"

if __name__ == "__main__":
    src = Path(sys.argv[1])
    with src.open(encoding="cp949", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = ["event_id"] + list(rows[0].keys())
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"event_id": i, **{k: (v or "").strip() for k, v in r.items()}})
    print(f"{OUT} {len(rows)}건")
