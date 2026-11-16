"""시연 영상 배경 음악을 코드로 만든다(내려받은 음원 없음, 저작권 문제 없음).

app/.venv/bin/python docs/video/music.py 초   → build/video/music.wav (44.1kHz 스테레오)
108BPM 다장조, C-G-Am-F 진행: 퉁기는 분산 화음, 베이스, 패드, 북·하이햇, 실로폰 선율.
"""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 108
BEAT = 60 / BPM
BAR = BEAT * 4
OUT = Path(__file__).resolve().parents[2] / "build" / "video" / "music.wav"

CHORDS = [  # 화음(셋째 음까지)과 베이스
    ([261.63, 329.63, 392.00], 130.81),  # C
    ([196.00, 246.94, 293.66], 98.00),   # G
    ([220.00, 261.63, 329.63], 110.00),  # Am
    ([174.61, 220.00, 261.63], 87.31),   # F
]
MELODY = [  # 네 마디 선율: (마디, 박, 주파수)
    (0, 0, 659.25), (0, 1.5, 783.99), (0, 2, 880.00), (0, 3, 783.99),
    (1, 0, 587.33), (1, 2, 783.99),
    (2, 0, 523.25), (2, 1.5, 659.25), (2, 2, 880.00), (2, 3.5, 783.99),
    (3, 0, 523.25), (3, 2, 440.00), (3, 3, 392.00),
]


def t_of(sec):
    return np.arange(int(sec * SR)) / SR


def pluck(f, dur=0.6):
    t = t_of(dur)
    y = sum((1 / k ** 1.2) * np.sin(2 * np.pi * k * f * t) * np.exp(-(3 + 2.2 * k) * t) for k in range(1, 9))
    return y * np.minimum(1, t / 0.003)


def bell(f, dur=1.2):
    t = t_of(dur)
    y = np.sin(2 * np.pi * f * t) * np.exp(-3 * t) + 0.4 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-6 * t) \
        + 0.15 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-10 * t)
    return y * np.minimum(1, t / 0.002)


def bass(f, dur=BEAT * 0.9):
    t = t_of(dur)
    env = np.minimum(1, t / 0.01) * np.exp(-2.5 * t)
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)) * env


def pad(freqs, dur=BAR):
    t = t_of(dur)
    env = np.minimum(1, t / 0.5) * np.minimum(1, (dur - t) / 0.4)
    return sum(np.sin(2 * np.pi * f * t) + np.sin(6 * np.pi * f * t) / 9 for f in freqs) * env / len(freqs)


def kick():
    t = t_of(0.35)
    phase = 2 * np.pi * np.cumsum(50 + 70 * np.exp(-30 * t)) / SR
    return np.sin(phase) * np.exp(-9 * t)


def noise(dur, decay, seed):
    t = t_of(dur)
    n = np.diff(np.random.default_rng(seed).standard_normal(len(t) + 1))  # 차분으로 높은 소리만 남긴다
    return n * np.exp(-decay * t)


def place(track, sig, start, gain, pan=0.0):
    i = int(start * SR)
    j = min(len(track), i + len(sig))
    if i >= len(track):
        return
    left, right = gain * (1 - pan) / 2 * 2 ** 0.5, gain * (1 + pan) / 2 * 2 ** 0.5
    track[i:j, 0] += sig[: j - i] * left
    track[i:j, 1] += sig[: j - i] * right


def main(seconds):
    bars = int(np.ceil(seconds / BAR)) + 1
    mix = np.zeros((int((bars + 1) * BAR * SR), 2))
    snare, hat = noise(0.18, 25, 1), noise(0.05, 80, 2)
    for b in range(bars):
        start = b * BAR
        tones, root = CHORDS[b % 4]
        drums = 4 <= b
        melody = 20 <= b < 36 or 44 <= b
        place(mix, pad(tones), start, 0.10)
        arp = [tones[0], tones[2], tones[1], tones[2], tones[0] * 2, tones[2], tones[1], tones[2]]
        for k, f in enumerate(arp):
            place(mix, pluck(f), start + k * BEAT / 2, 0.20, pan=-0.35 if k % 2 else 0.35)
        if drums:
            for beat in range(4):
                place(mix, bass(root if beat % 2 == 0 else root * 1.5), start + beat * BEAT, 0.28)
                if beat in (0, 2):
                    place(mix, kick(), start + beat * BEAT, 0.42)
                if beat in (1, 3) and b >= 12:
                    place(mix, snare, start + beat * BEAT, 0.07)
            for k in range(8):
                place(mix, hat, start + k * BEAT / 2, 0.035 if k % 2 else 0.02, pan=0.4)
        if melody:
            for bar, beat, f in MELODY:
                if bar == b % 4:
                    place(mix, bell(f), start + beat * BEAT, 0.13, pan=0.25)
    mix = mix[: int(seconds * SR)]
    n = len(mix)
    fade = np.minimum(1, np.arange(n) / (1.5 * SR)) * np.minimum(1, (n - np.arange(n)) / (3.0 * SR))
    mix *= fade[:, None]
    mix *= 0.85 / np.max(np.abs(mix))
    rms = np.sqrt(np.mean(mix ** 2))
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"{OUT.name} {seconds:.1f}초, 최고 0.85, RMS {rms:.3f}({20 * np.log10(rms):.1f} dBFS)")


if __name__ == "__main__":
    main(float(sys.argv[1]))
