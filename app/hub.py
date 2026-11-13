"""동봉한 허브 공개 자료 스냅샷을 읽는다. 실행 중 허브를 부르지 않는다(하루 호출 한도가 있다)."""
import calendar
import csv
import datetime as dt
from pathlib import Path

DATA = Path(__file__).parent / "data" / "hub"
FIRST_DAY = dt.date(2023, 8, 1)
LAST_DAY = dt.date(2026, 8, 31)
ROWS_PER_DAY = 16  # 성별 2 x 연령대 8
MISSING_LIMIT = 0.10


def _date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def load_events(path=None):
    """행사 목록. 날짜가 비었거나 틀리면 None으로 둔다(분석 가능 판정이 "날짜 없음"으로 다룬다)."""
    path = path or DATA / "events.csv"
    with path.open(encoding="utf-8", newline="") as f:
        return [
            {"event_id": r["event_id"], "name": r["콘텐츠명"], "start": _date(r["시작일"]), "end": _date(r["종료일"])}
            for r in csv.DictReader(f)
        ]


def daily_visits(emd, path=None):
    """그날 16행이 다 있는 날의 visitPop 합. 파일이 없으면 None(공개 방문 자료 없음)."""
    path = path or DATA / "population" / f"{emd}.csv"
    if not path.exists():
        return None
    sums = {}
    counts = {}
    seen = set()
    duplicates = 0
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            key = (r["baseDate"], r["gender"], r["ageGroup"])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            day = dt.datetime.strptime(r["baseDate"], "%Y%m%d").date()
            sums[day] = sums.get(day, 0) + int(r["visitPop"])
            counts[day] = counts.get(day, 0) + 1
    days = {d: v for d, v in sums.items() if counts[d] == ROWS_PER_DAY}
    expected = (LAST_DAY - FIRST_DAY).days + 1
    missing = [FIRST_DAY + dt.timedelta(n) for n in range(expected) if FIRST_DAY + dt.timedelta(n) not in days]
    return {"days": days, "missing": missing, "duplicates": duplicates}


def monthly_means(visits):
    """결측일을 뺀 달별 평균. 결측일이 그 달의 10%를 넘으면 그 달은 뺀다."""
    by_month = {}
    for day, value in visits["days"].items():
        by_month.setdefault(f"{day.year}{day.month:02d}", []).append(value)
    out = {}
    for ym, values in by_month.items():
        days_in_month = calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]
        if days_in_month - len(values) <= MISSING_LIMIT * days_in_month:
            out[ym] = sum(values) / len(values)
    return out
