# Audio Decibel Game Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 마이크 입력이 100 dB 이상을 5초 연속 유지하면 잠금 앱 실행을 허용하는 오디오 데시벨 미니게임을 AimGuard에 추가한다.

**Architecture:** `sounddevice.InputStream` 콜백 방식으로 오디오 청크를 받는 `AudioThread(QThread)`가 RMS → dBFS → 표시 dB로 변환해 Signal을 발행하고, `AudioGameWidget`이 이를 받아 수직 막대 미터 UI와 게임 로직을 처리한다. 마이크 없음/권한 거부 시 `game_quit` Signal로 즉시 폴백하며, 기존 motion_game 폴백 패턴과 동일하다.

**Tech Stack:** PySide6 6.10+, sounddevice, numpy, Python 3.11+

---

## Chunk 1: 의존성 + 설정 (config.py, requirements.txt)

### Task 1: requirements.txt에 sounddevice 추가

**Files:**
- Modify: `mouse-game/requirements.txt`

- [ ] **Step 1: sounddevice 줄 추가**

`mouse-game/requirements.txt` 내용을 다음으로 교체:

```
PySide6>=6.10
psutil>=5.9
opencv-python>=4.8
mediapipe>=0.10
numpy>=1.24
sounddevice>=0.4
```

- [ ] **Step 2: 설치 확인**

```bash
python3 -c "import sounddevice; print(sounddevice.__version__)"
```

Expected: 버전 문자열 출력 (이미 설치되어 있으므로 에러 없음)

- [ ] **Step 3: 커밋**

```bash
git add mouse-game/requirements.txt
git commit -m "deps: sounddevice 의존성 추가"
```

---

### Task 2: config.py에 db_threshold / time_limit_audio 필드 추가

**Files:**
- Modify: `mouse-game/config.py`

현재 `AppConfig.__init__` 끝 부분:
```python
        self.motion_reps = 5
        self.time_limit_motion = 40
```

- [ ] **Step 1: `__init__` 에 필드 2개 추가**

`self.time_limit_motion = 40` 바로 뒤에 추가:

```python
        # 오디오 게임
        self.db_threshold = 100
        self.time_limit_audio = 30
```

- [ ] **Step 2: `save()` 메서드에 직렬화 추가**

`"time_limit_motion": self.time_limit_motion,` (save() 딕셔너리의 마지막 줄) 바로 뒤에 추가:

```python
            "db_threshold": self.db_threshold,
            "time_limit_audio": self.time_limit_audio,
```

- [ ] **Step 3: `load()` 메서드에 역직렬화 추가**

`c.time_limit_motion = data.get("time_limit_motion", 40)` 바로 뒤에 추가:

```python
            c.db_threshold = data.get("db_threshold", 100)
            c.time_limit_audio = data.get("time_limit_audio", 30)
```

- [ ] **Step 4: 빠른 동작 확인**

```bash
cd mouse-game && python3 -c "
from config import AppConfig
c = AppConfig()
print(c.db_threshold, c.time_limit_audio)  # 100 30
c2 = AppConfig.load()
print(c2.db_threshold, c2.time_limit_audio)
"
```

Expected: `100 30` 두 줄 출력 (오류 없음)

- [ ] **Step 5: 커밋**

```bash
git add mouse-game/config.py
git commit -m "feat(config): db_threshold, time_limit_audio 필드 추가"
```

---

## Chunk 2: AudioGameWidget (audio_game.py 신규)

### Task 3: audio_game.py 전체 구현

**Files:**
- Create: `mouse-game/audio_game.py`

- [ ] **Step 1: 파일 생성**

`mouse-game/audio_game.py`를 아래 내용으로 생성:

```python
"""오디오 데시벨 게임 위젯 모듈

마이크 입력이 100 dB 이상을 HOLD_SECONDS 초 연속 유지하면 게임 성공.
sounddevice 콜백 + QThread 방식으로 오디오 처리.
"""

import numpy as np
from PySide6.QtCore import QThread, Signal, QTimer, Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFrame,
)
from PySide6.QtGui import QFont

# ── UI 색상 상수 (main_window.py와 동일 값, 순환 참조 방지를 위해 직접 정의) ──
_DARK_BG = "#0f0f23"
_CARD_BG = "#1a1a2e"
_ACCENT = "#4ECDC4"
_DANGER = "#FF6B6B"
_TEXT_PRIMARY = "#e2e8f0"
_TEXT_SECONDARY = "#94a3b8"

# dBFS → 표시 dB 변환 상수
# float32 기준: 샘플 범위 [-1.0, 1.0], 0 dBFS = 최대 진폭
_DBFS_MIN = -60.0    # 이 값 이하는 0 dB로 표시
_DISPLAY_MAX = 110.0  # 0 dBFS를 110 dB로 매핑

HOLD_SECONDS = 5.0   # 연속 유지 필요 시간 (고정)
_SAMPLERATE = 44100
_BLOCKSIZE = 2048


def _dbfs_to_display(dbfs: float) -> float:
    """raw dBFS → 표시 dB (0 ~ 110+)
    공식: (dbfs + 60) * (110 / 60)
    """
    return max(0.0, (dbfs - _DBFS_MIN) * (_DISPLAY_MAX / (-_DBFS_MIN)))


class AudioThread(QThread):
    """백그라운드에서 마이크 입력을 읽어 dB 레벨을 발행하는 스레드

    sounddevice 기본 dtype(float32)을 사용하므로 샘플 범위는 [-1.0, 1.0].
    hold_elapsed는 frames/samplerate 기반으로 정확한 경과 시간을 누적한다.
    """

    level_updated = Signal(float, float)  # (표시 dB, 청크 경과 시간(초))

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def run(self):
        import sounddevice as sd

        self._running = True

        def _callback(indata, frames, time, status):
            if not self._running:
                return
            # float32 기본 dtype: 샘플 범위 [-1.0, 1.0]
            rms = float(np.sqrt(np.mean(indata ** 2)))
            dbfs = 20.0 * np.log10(max(rms, 1e-10))
            elapsed = frames / _SAMPLERATE  # 이번 청크의 정확한 경과 시간
            self.level_updated.emit(_dbfs_to_display(dbfs), elapsed)

        with sd.InputStream(
            channels=1,
            samplerate=_SAMPLERATE,
            blocksize=_BLOCKSIZE,
            callback=_callback,
        ):
            while self._running:
                self.msleep(50)

    def stop(self):
        self._running = False
        if self.isRunning():
            self.wait(2000)


class AudioGameWidget(QWidget):
    """오디오 데시벨 게임 UI + 로직"""

    game_success = Signal()
    game_failed = Signal()
    game_quit = Signal()

    def __init__(self, db_threshold: int = 100, time_limit: int = 30, parent=None):
        super().__init__(parent)
        self._db_threshold = db_threshold
        self._time_limit = time_limit
        self._hold_timer = 0.0
        self._remaining = time_limit
        self._active = False
        self.app_name = ""
        self.app_path = ""

        self._audio_thread: AudioThread | None = None

        # 1초 countdown 타이머
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)

        self._build_ui()

    # ─── 설정 ────────────────────────────────────────────

    def update_settings(self, db_threshold: int, time_limit: int):
        self._db_threshold = db_threshold
        self._time_limit = time_limit

    # ─── 게임 시작 ────────────────────────────────────────

    def start_game(self, app_name: str, app_path: str):
        """게임 시작. 마이크 없거나 권한 거부 시 즉시 game_quit."""
        self.app_name = app_name
        self.app_path = app_path

        try:
            import sounddevice as sd
            sd.check_input_settings(channels=1, samplerate=_SAMPLERATE)
        except Exception:
            QTimer.singleShot(0, lambda: self.game_quit.emit())
            return

        self._reset_state()
        self._title_label.setText(f"🎤  소리질러!")
        self._subtitle_label.setText(
            f"[{app_name}] 실행을 위해 {HOLD_SECONDS:.0f}초 유지!"
        )
        self._update_db_bar(0.0)
        self._update_hold_bar(0.0)
        self._update_countdown(self._time_limit)
        self._result_label.setText("")

        self._audio_thread = AudioThread(self)
        self._audio_thread.level_updated.connect(self._on_level_updated)  # (db, elapsed)
        self._audio_thread.start()
        self._countdown_timer.start()
        self._active = True

    def _reset_state(self):
        self._hold_timer = 0.0
        self._remaining = self._time_limit
        self._active = False

    # ─── UI 빌드 ─────────────────────────────────────────

    def _build_ui(self):
        # 색상 상수는 모듈 최상단 _DARK_BG 등을 사용 (순환 참조 방지)
        self.setStyleSheet(f"background-color: {_DARK_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 제목
        self._title_label = QLabel("🎤  소리질러!")
        self._title_label.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {_ACCENT};")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._title_label)

        # 부제목
        self._subtitle_label = QLabel("")
        self._subtitle_label.setFont(QFont("Arial", 14))
        self._subtitle_label.setStyleSheet(f"color: {_TEXT_SECONDARY};")
        self._subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._subtitle_label)

        # ── 메인 카드 ──────────────────────────────────────
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {_CARD_BG};
                border-radius: 16px;
                padding: 16px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)

        # dB 막대 + 레이블
        db_row = QHBoxLayout()
        db_row.setSpacing(12)

        self._db_bar = QProgressBar()
        self._db_bar.setRange(0, 120)
        self._db_bar.setValue(0)
        self._db_bar.setTextVisible(False)
        self._db_bar.setFixedHeight(36)
        self._db_bar.setStyleSheet(self._bar_style("#4ECDC4"))
        db_row.addWidget(self._db_bar, 1)

        self._db_label = QLabel("0 dB")
        self._db_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._db_label.setStyleSheet(f"color: {_TEXT_PRIMARY};")
        self._db_label.setFixedWidth(80)
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        db_row.addWidget(self._db_label)
        card_layout.addLayout(db_row)

        # 목표선 표시
        target_label = QLabel(f"── 목표: {self._db_threshold} dB ──────────────────────────")
        target_label.setFont(QFont("Arial", 11))
        target_label.setStyleSheet("color: #FF6B6B;")
        card_layout.addWidget(target_label)
        self._target_label = target_label

        # 유지 막대
        hold_header = QHBoxLayout()
        hold_title = QLabel("연속 유지:")
        hold_title.setFont(QFont("Arial", 13))
        hold_title.setStyleSheet(f"color: {_TEXT_SECONDARY};")
        hold_header.addWidget(hold_title)
        hold_header.addStretch()
        self._hold_label = QLabel(f"0.0 / {HOLD_SECONDS:.0f}s")
        self._hold_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self._hold_label.setStyleSheet(f"color: {_TEXT_PRIMARY};")
        hold_header.addWidget(self._hold_label)
        card_layout.addLayout(hold_header)

        self._hold_bar = QProgressBar()
        self._hold_bar.setRange(0, int(HOLD_SECONDS * 100))
        self._hold_bar.setValue(0)
        self._hold_bar.setTextVisible(False)
        self._hold_bar.setFixedHeight(20)
        self._hold_bar.setStyleSheet(self._bar_style("#FFD93D"))
        card_layout.addWidget(self._hold_bar)

        root.addWidget(card)

        # 남은 시간
        self._countdown_label = QLabel(f"남은 시간: {self._time_limit}s")
        self._countdown_label.setFont(QFont("Arial", 14))
        self._countdown_label.setStyleSheet(f"color: {_TEXT_SECONDARY};")
        self._countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._countdown_label)

        # 결과 레이블
        self._result_label = QLabel("")
        self._result_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._result_label)

        root.addStretch()

        # 포기 버튼
        self._quit_btn = QPushButton("포기")
        self._quit_btn.setFont(QFont("Arial", 14))
        self._quit_btn.setFixedHeight(44)
        self._quit_btn.setFixedWidth(160)
        self._quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._quit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_DANGER};
                color: #ffffff;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: #e05555; }}
        """)
        self._quit_btn.clicked.connect(self._on_quit)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self._quit_btn)
        btn_layout.addStretch()
        root.addLayout(btn_layout)

    @staticmethod
    def _bar_style(color: str) -> str:
        return f"""
            QProgressBar {{
                background-color: #2d3748;
                border-radius: 8px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 8px;
            }}
        """

    # ─── UI 갱신 헬퍼 ─────────────────────────────────────

    def _update_db_bar(self, db: float):
        self._db_bar.setValue(int(min(db, 120)))
        self._db_label.setText(f"{db:.0f} dB")
        color = "#4ECDC4" if db < self._db_threshold else "#56CF6F"
        self._db_bar.setStyleSheet(self._bar_style(color))

    def _update_hold_bar(self, hold: float):
        self._hold_bar.setValue(int(hold * 100))
        self._hold_label.setText(f"{hold:.1f} / {HOLD_SECONDS:.0f}s")

    def _update_countdown(self, remaining: int):
        self._countdown_label.setText(f"남은 시간: {remaining}s")

    # ─── 이벤트 핸들러 ────────────────────────────────────

    @Slot(float, float)
    def _on_level_updated(self, db: float, elapsed: float):
        """elapsed: 이번 콜백 청크의 정확한 경과 시간 = frames / samplerate"""
        if not self._active:
            return
        self._update_db_bar(db)

        if db >= self._db_threshold:
            self._hold_timer += elapsed   # 정확한 경과 시간 누적
            self._update_hold_bar(min(self._hold_timer, HOLD_SECONDS))
            if self._hold_timer >= HOLD_SECONDS:
                self._on_success()
        else:
            self._hold_timer = 0.0
            self._update_hold_bar(0.0)

    @Slot()
    def _on_countdown_tick(self):
        if not self._active:
            return
        self._remaining -= 1
        self._update_countdown(self._remaining)
        if self._remaining <= 0:
            self._on_fail()

    def _on_success(self):
        self._active = False
        self._stop_audio()
        self._result_label.setText("✅ 성공!")
        self._result_label.setStyleSheet("color: #56CF6F;")
        QTimer.singleShot(600, lambda: self.game_success.emit())

    def _on_fail(self):
        self._active = False
        self._stop_audio()
        self._result_label.setText("❌ 시간 초과!")
        self._result_label.setStyleSheet("color: #FF6B6B;")
        QTimer.singleShot(600, lambda: self.game_failed.emit())

    @Slot()
    def _on_quit(self):
        self._active = False
        self._stop_audio()
        self.game_quit.emit()

    def _stop_audio(self):
        self._countdown_timer.stop()
        if self._audio_thread and self._audio_thread.isRunning():
            self._audio_thread.stop()
            self._audio_thread = None
```

- [ ] **Step 2: import 오류 없는지 확인**

```bash
cd mouse-game && python3 -c "from audio_game import AudioGameWidget; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add mouse-game/audio_game.py
git commit -m "feat: AudioGameWidget + AudioThread 구현 (sounddevice 콜백)"
```

---

## Chunk 3: main_window.py 연동

### Task 4: main_window.py — audio_widget 추가 + 랜덤 풀 업데이트

**Files:**
- Modify: `mouse-game/main_window.py`

이 태스크는 하나씩 적용한다. 수정 위치와 내용을 정확히 따를 것.

---

**4-1. import 추가**

파일 상단 `from motion_game import MotionGameWidget` 바로 다음 줄에 추가:

```python
from audio_game import AudioGameWidget
```

---

**4-2. audio_widget 생성 (stack index 5)**

`__init__` 내 `self.stack.addWidget(self.motion_widget)` 바로 다음에 추가:

```python
        # 오디오 게임 위젯 (stack index 5)
        self.audio_widget = AudioGameWidget(
            self.config.db_threshold, self.config.time_limit_audio
        )
        self.audio_widget.game_success.connect(self._on_game_success)
        self.audio_widget.game_failed.connect(self._on_game_failed)
        self.audio_widget.game_quit.connect(self._on_audio_game_quit)
        self.stack.addWidget(self.audio_widget)
```

---

**4-3. 랜덤 풀에 "audio" 추가**

`_on_process_detected` 메서드의 `random.choice(["aim", "bug", "keyboard", "motion"])` 를 다음으로 교체:

```python
        self._launch_game(random.choice(["aim", "bug", "keyboard", "motion", "audio"]), app_name, app_path)
```

---

**4-4. `_launch_game` — audio 분기 추가**

`elif game_type == "motion":` 블록 끝(`self.stack.setCurrentIndex(4)`) 바로 다음에 추가:

```python
        elif game_type == "audio":
            db_threshold = self.audio_db_combo.currentData()
            time_limit = self.audio_time_combo.currentData()
            self.audio_widget.update_settings(db_threshold, time_limit)
            self.audio_widget.start_game(app_name, app_path)
            self.stack.setCurrentIndex(5)
```

---

**4-5. `_on_game_success` dict에 5 추가**

`idx_to_widget = {1: self.aim_widget, 2: self.bug_widget, 3: self.keyboard_widget, 4: self.motion_widget}` 를:

```python
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget,
                         5: self.audio_widget}
```

---

**4-6. `_on_game_quit` dict에 5 추가**

같은 방식으로 `_on_game_quit` 내 `idx_to_widget` 딕셔너리도 동일하게 수정.

---

**4-7. `_on_audio_game_quit` 메서드 추가**

`_on_motion_game_quit` 메서드 바로 다음에 추가:

```python
    @Slot()
    def _on_audio_game_quit(self):
        """오디오 게임 포기 — audio 제외 후 재추첨"""
        pool = ["aim", "bug", "keyboard", "motion"]
        self._launch_game(
            random.choice(pool),
            self._pending_app_name,
            self._pending_app_path,
        )
```

---

**4-8. 설정 화면 — 오디오 콤보박스 추가**

`_build_settings_page` 내 `self.motion_time_combo` 생성 블록 끝
(`settings_layout.addWidget(self.motion_time_combo)`) 바로 다음에 추가:

```python
        settings_layout.addSpacing(16)

        # ── 오디오 설정 ──────────────────────────
        settings_layout.addWidget(QLabel("🎤 오디오:"))

        self.audio_db_label = QLabel("dB 기준:")
        settings_layout.addWidget(self.audio_db_label)
        self.audio_db_combo = QComboBox()
        db_options = [80, 90, 100]
        for d in db_options:
            self.audio_db_combo.addItem(f"{d} dB", d)
        idx_db = db_options.index(self.config.db_threshold) if self.config.db_threshold in db_options else 2
        self.audio_db_combo.setCurrentIndex(idx_db)
        settings_layout.addWidget(self.audio_db_combo)

        settings_layout.addSpacing(8)

        self.audio_time_label = QLabel("제한 시간:")
        settings_layout.addWidget(self.audio_time_label)
        self.audio_time_combo = QComboBox()
        audio_time_options = [20, 30, 45]
        for t in audio_time_options:
            self.audio_time_combo.addItem(f"{t}초", t)
        idx_at = audio_time_options.index(self.config.time_limit_audio) if self.config.time_limit_audio in audio_time_options else 1
        self.audio_time_combo.setCurrentIndex(idx_at)
        settings_layout.addWidget(self.audio_time_combo)
```

---

**4-9. `_save_config` — 오디오 필드 저장**

`self.config.time_limit_motion = self.motion_time_combo.currentData()` 바로 다음에 추가:

```python
        self.config.db_threshold = self.audio_db_combo.currentData()
        self.config.time_limit_audio = self.audio_time_combo.currentData()
```

---

- [ ] **Step 1: 4-1 ~ 4-9 순서대로 main_window.py 편집 적용**

- [ ] **Step 2: import 오류 없는지 확인**

```bash
cd mouse-game && python3 -c "
from config import AppConfig
from audio_game import AudioGameWidget
from main_window import MainWindow
print('import OK')
"
```

Expected: `import OK`

- [ ] **Step 3: 커밋**

```bash
git add mouse-game/main_window.py
git commit -m "feat: main_window에 audio_widget 추가 (stack 5, 랜덤 풀 + 설정 콤보)"
```

---

## Chunk 4: 통합 확인 + 최종 커밋

### Task 5: 전체 통합 실행 확인

**Files:**
- No new files

- [ ] **Step 1: 앱 정상 기동 확인**

```bash
cd mouse-game && python3 main.py &
sleep 3
kill %1
echo "기동 OK"
```

Expected: 에러 없이 기동 후 종료

- [ ] **Step 2: AudioGameWidget 단독 동작 확인 (마이크 있는 환경에서)**

```bash
cd mouse-game && python3 -c "
import sys
from PySide6.QtWidgets import QApplication
from audio_game import AudioGameWidget
app = QApplication(sys.argv)
w = AudioGameWidget(db_threshold=100, time_limit=30)
w.start_game('Test', '/test')
w.show()
# 5초 후 자동 종료
from PySide6.QtCore import QTimer
QTimer.singleShot(5000, app.quit)
app.exec()
print('Widget smoke test OK')
"
```

Expected: 창이 뜨고 5초 후 자동 종료, `Widget smoke test OK` 출력

- [ ] **Step 3: 최종 push**

```bash
git push origin main
```

---

## 구현 주의사항

1. **색상 상수 순환 참조 방지**: `audio_game.py`는 `main_window.py`에서 import되므로, `main_window`를 역으로 import하면 순환 참조가 발생한다. 색상 상수(`_DARK_BG` 등)를 `audio_game.py` 상단에 직접 정의해 이를 방지한다.

2. **float32 dtype 필수**: `sounddevice.InputStream` 기본 dtype은 `float32`이며 샘플 범위는 [-1.0, 1.0]이다. `dtype="int16"`을 지정하면 RMS가 수천 단위가 되어 dBFS 공식이 완전히 깨진다. dtype 파라미터는 생략(기본값 사용)한다.

3. **hold_timer 정확도**: `elapsed = frames / samplerate`로 각 콜백의 실제 경과 시간을 계산해 누적함으로써 5초 판정이 실시간과 일치한다.

4. **macOS 마이크 권한**: 첫 실행 시 macOS가 마이크 권한을 요청한다. 사용자가 거부하면 `sounddevice.check_input_settings()`가 예외를 던지며 폴백이 동작한다.
