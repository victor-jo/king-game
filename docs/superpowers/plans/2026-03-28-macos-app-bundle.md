# macOS App Bundle 최적화 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mouse-game PySide6 앱을 sounddevice/audio_game 포함, 불필요 패키지 제거로 최적화된 단일 `.app` 번들로 빌드한다.

**Architecture:** py2app을 사용해 self-contained `.app` 번들 생성. `setup.py`에서 누락된 sounddevice/audio_game을 추가하고, 불필요한 패키지(PyQt5, matplotlib 등)를 excludes로 제거한다.

**Tech Stack:** py2app 0.28.x, PySide6, sounddevice, opencv-python, mediapipe, numpy, psutil

---

## Chunk 1: setup.py 수정

### Task 1: setup.py 수정 — sounddevice/audio_game 추가 및 최적화

**Files:**
- Modify: `mouse-game/setup.py`

- [ ] **Step 1: setup.py 수정**

`OPTIONS` 딕셔너리를 다음과 같이 교체:

```python
OPTIONS = {
    'no_zip': True,
    'packages': ['PySide6', 'psutil', 'cv2', 'mediapipe', 'numpy', '_sounddevice_data'],
    'includes': [
        'main_window', 'config', 'process_monitor',
        'aim_game', 'bug_game', 'keyboard_game', 'motion_game', 'audio_game', 'sounds',
        'sounddevice', '_sounddevice',
    ],
    'excludes': [
        'PyQt5', 'PyQt6',
        'matplotlib', 'mpl_toolkits',
        'pygments',
        'setuptools', 'pkg_resources', 'distutils',
        'tkinter', '_tkinter', 'Tkinter',
        'unittest', 'doctest', 'pydoc',
        'IPython', 'ipython', 'ipykernel',
        'scipy',
        'pandas',
        'PIL', 'Pillow',
        'wx', 'gi', 'gtk',
        'PyInstaller',
        'cffi',
    ],
    'strip': True,
    'optimize': 1,
}
```

- [ ] **Step 2: 변경 확인**

```bash
cat mouse-game/setup.py
```

Expected: packages에 `_sounddevice_data`, includes에 `audio_game`, `sounddevice`, `_sounddevice`, excludes 리스트, strip/optimize 확인.

- [ ] **Step 3: Commit**

```bash
cd /Users/wj.cho/dev/poc/king-game
git add mouse-game/setup.py
git commit -m "feat(bundle): sounddevice/audio_game 추가, excludes 최적화, strip/optimize 활성화"
```

---

## Chunk 2: 빌드 및 검증

### Task 2: 클린 빌드

**Files:**
- `mouse-game/build/` (삭제)
- `mouse-game/dist/` (삭제)
- `mouse-game/build.log` (생성)

- [ ] **Step 1: 기존 빌드 아티팩트 삭제**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
rm -rf build/ dist/
```

- [ ] **Step 2: py2app 빌드 실행**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
python3 setup.py py2app 2>&1 | tee build.log
```

Expected: 오류 없이 완료, `dist/AimGuard.app` 생성.

- [ ] **Step 3: 빌드 로그 ERROR 확인**

```bash
grep -i "error\|missing\|failed" mouse-game/build.log | head -30
```

Expected: 심각한 오류 없음 (WARNING은 무시 가능).

### Task 3: 검증

- [ ] **Step 1: 번들 크기 확인**

```bash
du -sh /Users/wj.cho/dev/poc/king-game/mouse-game/dist/AimGuard.app
```

Expected: ~1.2–1.4GB (이전 1.6GB 대비 감소).

- [ ] **Step 2: 앱 실행 확인**

```bash
open /Users/wj.cho/dev/poc/king-game/mouse-game/dist/AimGuard.app
```

Expected: 트레이 아이콘 표시, 크래시 없음.

- [ ] **Step 3: Push**

```bash
cd /Users/wj.cho/dev/poc/king-game
git push origin main
```
