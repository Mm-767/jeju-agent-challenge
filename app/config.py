"""경로, 키, 모델 이름. 디스크 쓰기는 out_path()를 거쳐 app/out 아래로만 한다."""
import os
from pathlib import Path

APP = Path(__file__).resolve().parent
OUT = APP / "out"
PROMPTS = APP / "prompts"
MODEL = "claude-haiku-5-5"


def out_path(*parts):
    path = OUT.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def env(name):
    """센터 운영 때는 담당자가 넣은 환경변수, 없으면 app/.env(평가용 키)."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = APP / ".env"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip() or None
    return None
