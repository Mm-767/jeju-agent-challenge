"""표시값 자가 점검(계획서 8-4). 화면 버튼, 명령줄, 시험이 같은 함수를 쓴다.

실행마다 무작위 9자리 숫자를 센터 형식 가상 CSV에 심고 센터 단계를 끝까지 돌린 뒤,
잠금 뒤 실제로 나간 외부 요청, 전송 기록과 결과 글자 속 표시값, 결과 폴더 파일 종류, 원격 측정 부품을 본다.
"""
import importlib
import json
import random
import shutil
import tempfile
import time
from pathlib import Path

import config
import egress
import pipeline

DUMMY = config.APP / "data" / "dummy" / "card_rehearsal"


def _marked_files(emd):
    """행사 읍면의 관광객 행 하나의 이용금액을 표시값으로 바꾼 파일들과 (표시값, 그 칸의 바뀐 금액 합)."""
    marker = str(random.randint(100_000_000, 999_999_999))
    files = []
    cell_total = None
    for path in sorted(DUMMY.glob("*.csv")):
        text = path.read_text(encoding="utf-8")
        if cell_total is None and f'"{emd}"' in text:
            lines = text.splitlines()
            for i, line in enumerate(lines):
                cols = [c.strip('"') for c in line.split('","')]
                if len(cols) == 14 and cols[4] == emd and cols[8] in ("개별", "단체"):
                    key = (cols[0], cols[4], cols[5])
                    old = int(cols[13])
                    cols[13] = marker
                    lines[i] = '"' + '","'.join(cols) + '"'
                    same = [l for l in lines if l.startswith(f'"{key[0]}"') and f'"{key[1]}","{key[2]}"' in l]
                    cell_total = sum(int(l.split('","')[13].strip('"')) for l in same
                                     if l.split('","')[8] in ("개별", "단체"))
                    text = "\n".join(lines) + "\n"
                    break
        files.append((path.name, text.encode("utf-8")))
    return files, marker, str(cell_total)


def run(bundle):
    """[(항목, 통과 여부, 설명)]. 끝나면 잠금을 풀고 자기 파일을 지운다."""
    rows = []
    log = config.out_path("work", "transmissions.jsonl")
    before = log.read_text(encoding="utf-8").count("\n") if log.exists() else 0
    out_dir = Path(tempfile.mkdtemp(prefix="selfcheck_"))
    try:
        files, marker, total = _marked_files(bundle["event"]["emd"])
        summary = pipeline.center_stage(bundle, files, out_dir=out_dir, example=True)
        blocked = 0
        try:
            egress.call_llm("selfcheck", {"model": config.MODEL, "max_tokens": 16, "messages": [{"role": "user", "content": "x"}]})
        except egress.Locked:
            blocked = 1
        entries = log.read_text(encoding="utf-8").splitlines()[before:] if log.exists() else []
        sent_after = [e for e in entries if json.loads(e).get("status") == "sent"]
        texts = json.dumps(summary, ensure_ascii=False)
        rows.append(("잠금 뒤 외부로 나간 요청", not sent_after, f"{len(sent_after)}건"))
        rows.append(("잠금 뒤 일부러 한 AI 호출", blocked == 1, "막힘" if blocked else "막히지 않음"))
        rows.append(("전송 기록 속 표시값과 그 칸의 합계", not any(marker in e or total in e for e in entries), "0건이어야 함"))
        rows.append(("결과 글자 속 표시값과 그 칸의 합계", marker not in texts and total not in texts, "0건이어야 함"))
        rows.append(("결과 폴더 파일 종류", not __import__("report").export_check(out_dir),
                     ", ".join(sorted({p.suffix for p in out_dir.iterdir()}))))
        exporters = []
        for mod in ("opentelemetry.sdk", "opentelemetry.exporter"):
            try:
                importlib.import_module(mod)
                exporters.append(mod)
            except ModuleNotFoundError:
                pass
        rows.append(("원격 측정 내보내기 부품", not exporters, "없음" if not exporters else ", ".join(exporters)))
    finally:
        egress.unlock()
        shutil.rmtree(out_dir, ignore_errors=True)
    rows.append(("자가 점검 뒤 잠금", not egress.is_locked(), "풀림"))
    return rows


if __name__ == "__main__":
    import sys

    bundle = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for item, ok, detail in run(bundle):
        print(f"[{'PASS' if ok else 'FAIL'}] {item}: {detail}")
