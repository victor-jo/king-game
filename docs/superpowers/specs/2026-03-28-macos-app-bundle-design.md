# macOS App Bundle — 설계 문서

**날짜**: 2026-03-28
**프로젝트**: AimGuard (king-game / mouse-game)
**상태**: 승인됨

---

## 1. 목표

`mouse-game/` PySide6 앱을 다른 Mac에도 배포 가능한 자체 포함(self-contained) `.app` 번들로 패키징한다. 실행 오류 없이 동작하며, 현재 1.6GB 번들을 최대한 최적화한다.

---

## 2. 현황 분석

| 패키지 | 현재 크기 | 상태 |
|---|---|---|
| PySide6 + Qt | ~1.1GB | 필요 (전체 포함됨) |
| **PyQt5** | **133MB** | **불필요 — 제거 대상** |
| cv2 (opencv) | 107MB | 필요 |
| mediapipe | 72MB | 필요 |
| numpy | 32MB | 필요 |
| **matplotlib** | **29MB** | **불필요 — 제거 대상** |
| **pygments** | **9MB** | **불필요 — 제거 대상** |
| **setuptools** | **8MB** | **불필요 — 제거 대상** |
| sounddevice | — | **누락 → 크래시 원인** |
| audio_game | — | **누락 → 크래시 원인** |

**현재 크래시 원인**: `sounddevice` 패키지와 `audio_game` 모듈이 setup.py에 빠져 있음.

---

## 3. 접근법

**py2app 0.28.x + excludes 최적화**

- 이미 설치된 py2app 활용
- `setup.py` 수정으로 누락 패키지 추가 및 불필요 패키지 제거
- `strip=True`, `optimize=1` 적용
- 예상 절감: ~180MB (PyQt5 + matplotlib + 기타)
- 예상 최종 크기: ~1.4GB → 목표 ~1.2–1.4GB

---

## 4. setup.py 변경 사항

### 4-1. packages — sounddevice 추가

```python
'packages': ['PySide6', 'psutil', 'cv2', 'mediapipe', 'numpy', 'sounddevice'],
```

### 4-2. includes — audio_game 추가

```python
'includes': [
    'main_window', 'config', 'process_monitor',
    'aim_game', 'bug_game', 'keyboard_game', 'motion_game', 'audio_game', 'sounds',
],
```

### 4-3. excludes 추가 (신규)

```python
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
```

### 4-4. 빌드 옵션 추가

```python
'strip': True,       # 바이너리 심볼 제거
'optimize': 1,       # .pyc docstring 제거
```

---

## 5. 빌드 명령

```bash
cd mouse-game
rm -rf build/ dist/
python3 setup.py py2app 2>&1 | tee build.log
du -sh dist/AimGuard.app
```

---

## 6. 검증

빌드 완료 후:
1. `dist/AimGuard.app` 더블클릭 → 트레이 아이콘 표시 확인
2. 오디오 게임 트리거 → 크래시 없이 마이크 레벨 표시 확인
3. 빌드 로그에서 WARNING/ERROR 확인

---

## 7. .gitignore 처리

`dist/`, `build/` 디렉토리는 git에 추가하지 않는다.
`setup.py`만 커밋 대상.
