"""프로시저럴 사운드 이펙트 생성 모듈

WAV 파일을 코드로 생성하여 게임 사운드 제공.
외부 파일 의존 없이 순수 Python으로 사운드 생성.
"""

import math
import os
import struct
import wave

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")


def _ensure_dir():
    os.makedirs(SOUNDS_DIR, exist_ok=True)


def _write_wav(filename: str, samples: list[float], sample_rate: int = 22050):
    """float(-1.0 ~ 1.0) 샘플 리스트를 WAV 파일로 저장"""
    _ensure_dir()
    filepath = os.path.join(SOUNDS_DIR, filename)
    with wave.open(filepath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        for s in samples:
            s = max(-1.0, min(1.0, s))
            wf.writeframes(struct.pack("<h", int(s * 32767)))
    return filepath


def _generate_smash() -> str:
    """망치: 묵직한 임팩트"""
    sr = 22050
    duration = 0.25
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = max(0, 1.0 - t / duration) ** 2
        # 저주파 충격 + 노이즈
        low = math.sin(2 * math.pi * 60 * t) * 0.7
        noise = (hash(i) % 1000 / 500 - 1.0) * 0.3
        samples.append((low + noise) * env * 0.8)
    return _write_wav("smash.wav", samples, sr)


def _generate_chainsaw() -> str:
    """전기톱: 부르릉 엔진음"""
    sr = 22050
    duration = 0.15
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = 1.0 - t / duration
        # 톱니파 + 모터 진동
        saw = (t * 120 % 1.0) * 2 - 1
        buzz = math.sin(2 * math.pi * 80 * t) * 0.4
        samples.append((saw * 0.5 + buzz) * env * 0.6)
    return _write_wav("chainsaw.wav", samples, sr)


def _generate_gunshot() -> str:
    """기관총: 짧은 총성"""
    sr = 22050
    duration = 0.06
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = max(0, 1.0 - t / duration) ** 3
        noise = (hash(i * 7 + 3) % 1000 / 500 - 1.0)
        click = math.sin(2 * math.pi * 800 * t) * 0.3
        samples.append((noise * 0.7 + click) * env * 0.9)
    return _write_wav("gunshot.wav", samples, sr)


def _generate_flame() -> str:
    """화염방사기: 쉬이이 소리"""
    sr = 22050
    duration = 0.2
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = min(t / 0.03, 1.0) * max(0, 1.0 - t / duration)
        # 필터링된 노이즈
        noise = (hash(i * 13 + 7) % 1000 / 500 - 1.0)
        # 약간의 주기 성분 추가
        hiss = math.sin(2 * math.pi * 2000 * t + noise * 3) * 0.3
        samples.append((noise * 0.5 + hiss) * env * 0.5)
    return _write_wav("flame.wav", samples, sr)


def _generate_water() -> str:
    """수압기: 물 쏟아지는 소리"""
    sr = 22050
    duration = 0.4
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = min(t / 0.05, 1.0) * max(0, 1.0 - t / duration) ** 0.5
        noise = (hash(i * 17 + 11) % 1000 / 500 - 1.0)
        bubble = math.sin(2 * math.pi * (300 + noise * 200) * t) * 0.2
        samples.append((noise * 0.4 + bubble) * env * 0.6)
    return _write_wav("water.wav", samples, sr)


def _generate_laser() -> str:
    """레이저: 비이이 전자음"""
    sr = 22050
    duration = 0.3
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = min(t / 0.01, 1.0) * max(0, 1.0 - t / duration)
        # 주파수 스윕 (높은 음 → 낮은 음)
        freq = 3000 - t * 8000
        tone = math.sin(2 * math.pi * freq * t) * 0.5
        harmonic = math.sin(2 * math.pi * freq * 1.5 * t) * 0.2
        samples.append((tone + harmonic) * env * 0.7)
    return _write_wav("laser.wav", samples, sr)


def _generate_bug_death() -> str:
    """벌레 사망: 짧은 팝음"""
    sr = 22050
    duration = 0.15
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = max(0, 1.0 - t / duration) ** 2
        pop = math.sin(2 * math.pi * 400 * t) * 0.4
        squish = math.sin(2 * math.pi * 150 * t) * 0.3
        noise = (hash(i * 23) % 1000 / 500 - 1.0) * 0.2
        samples.append((pop + squish + noise) * env * 0.7)
    return _write_wav("bug_death.wav", samples, sr)


def _generate_success() -> str:
    """성공: 밝은 차임"""
    sr = 22050
    duration = 0.6
    samples = []
    n = int(sr * duration)
    notes = [523, 659, 784]  # C5, E5, G5
    for i in range(n):
        t = i / sr
        env = max(0, 1.0 - t / duration) ** 0.5
        val = 0
        for j, freq in enumerate(notes):
            delay = j * 0.08
            if t > delay:
                tt = t - delay
                val += math.sin(2 * math.pi * freq * tt) * 0.3
        samples.append(val * env * 0.6)
    return _write_wav("success.wav", samples, sr)


def _generate_fail() -> str:
    """실패: 낮은 부저"""
    sr = 22050
    duration = 0.5
    samples = []
    n = int(sr * duration)
    for i in range(n):
        t = i / sr
        env = max(0, 1.0 - t / duration)
        tone = math.sin(2 * math.pi * 150 * t) * 0.5
        tone2 = math.sin(2 * math.pi * 120 * t) * 0.3
        samples.append((tone + tone2) * env * 0.7)
    return _write_wav("fail.wav", samples, sr)


# 사운드 파일 경로 캐시
_sound_paths: dict[str, str] = {}

SOUND_GENERATORS = {
    "smash": _generate_smash,
    "chainsaw": _generate_chainsaw,
    "gunshot": _generate_gunshot,
    "flame": _generate_flame,
    "water": _generate_water,
    "laser": _generate_laser,
    "bug_death": _generate_bug_death,
    "success": _generate_success,
    "fail": _generate_fail,
}


def get_sound_path(name: str) -> str:
    """사운드 파일 경로 반환 (없으면 생성)"""
    if name not in _sound_paths:
        filepath = os.path.join(SOUNDS_DIR, f"{name}.wav")
        if not os.path.exists(filepath):
            gen = SOUND_GENERATORS.get(name)
            if gen:
                filepath = gen()
        _sound_paths[name] = filepath
    return _sound_paths[name]


def generate_all_sounds():
    """모든 사운드 파일 미리 생성"""
    _ensure_dir()
    for name, gen in SOUND_GENERATORS.items():
        filepath = os.path.join(SOUNDS_DIR, f"{name}.wav")
        if not os.path.exists(filepath):
            gen()
