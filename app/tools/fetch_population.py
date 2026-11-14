"""허브 「읍면동 단위 내국인 유동인구」를 읍면 12곳, 2023-08-01~2026-08-31 일별로 받아 스냅샷 CSV로 저장한다.

중간에 멈춰도 다시 실행하면 읍면별 CSV의 마지막 날짜 다음부터 이어 받는다.
새 달을 더 받을 때: python tools/fetch_population.py --end 2026-10-31 [읍면 ...]
"""
import csv
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
DATA_ID = "Daaa1t3at3tt8a8DD3t55538t35Dab1t"
BASE = "https://open.jejudatahub.net/api/proxy"
START = dt.date(2023, 8, 1)
END = dt.date(2026, 8, 31)

# 하루 16행(성별 2 x 연령대 8), 한 번에 최대 100행이라 6일씩 끊는다
CHUNK_DAYS = 6
FIELDS = ["baseDate", "city", "emd", "gender", "ageGroup", "resdPop", "workPop", "visitPop"]


def load_key():
    for line in (APP / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("HUB_PROJECT_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("HUB_PROJECT_KEY가 .env에 없다")


def call(key, params):
    url = f"{BASE}/{DATA_ID}/{key}?{urllib.parse.urlencode(params)}"
    # ponytail: 고정 6회 재시도, 허브가 502를 자주 낸다
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 502:
                raise SystemExit(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 + attempt * 2)
    raise SystemExit(f"6회 실패: {params}")


def fetch_range(key, emd, start, end):
    rows = []
    number = 1
    while True:
        d = call(key, {
            "startDate": start.strftime("%Y%m%d"),
            "endDate": end.strftime("%Y%m%d"),
            "emd": emd,
            "limit": 100,
            "number": number,
        })
        rows.extend(d["data"])
        if not d["hasMore"]:
            return rows, d["totCnt"]
        number += 1


def last_saved_date(path):
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            last = row["baseDate"]
    return dt.datetime.strptime(last, "%Y%m%d").date() if last else None


def main(emds):
    key = load_key()
    out_dir = APP / "data" / "hub" / "population"
    out_dir.mkdir(parents=True, exist_ok=True)
    for emd in emds:
        path = out_dir / f"{emd}.csv"
        last = last_saved_date(path)
        cur = (last + dt.timedelta(days=1)) if last else START
        new_file = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                w.writeheader()
            while cur <= END:
                stop = min(cur + dt.timedelta(days=CHUNK_DAYS - 1), END)
                rows, tot = fetch_range(key, emd, cur, stop)
                expected = ((stop - cur).days + 1) * 16
                if tot != expected:
                    print(f"[경고] {emd} {cur}~{stop}: {tot}행, 기대 {expected}행", flush=True)
                rows.sort(key=lambda r: (r["baseDate"], r["gender"], r["ageGroup"]))
                for r in rows:
                    w.writerow({k: r.get(k) for k in FIELDS})
                f.flush()
                cur = stop + dt.timedelta(days=1)
                time.sleep(0.3)
        print(f"{emd} 완료", flush=True)


if __name__ == "__main__":
    spec = json.loads((APP / "spec" / "card_v02.json").read_text(encoding="utf-8"))
    args = sys.argv[1:]
    if args[:1] == ["--end"]:
        END = dt.date.fromisoformat(args[1])
        args = args[2:]
    main(args or spec["eup_myeon"])
