# KingGame Unified App Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mouse-game(AimGuard, PySide6) 베이스에 keyboard-game + motion-game을 통합하여, 감시 대상 앱 실행 감지 시 4종 미니게임(에임/벌레/타자/모션) 중 랜덤으로 하나를 실행하는 단일 PySide6 앱 완성

**Architecture:** mouse-game 디렉토리를 베이스로 keyboard_game.py, motion_game.py 두 파일을 추가하고 config.py와 main_window.py를 확장한다. 모든 게임 위젯은 game_success/game_failed/game_quit Signal을 공유 인터페이스로 노출하며, main_window가 스택으로 관리한다. motion-game은 lazy import와 카메라 연결 실패 시 즉시 game_quit emit으로 폴백한다.

**Tech Stack:** PySide6, psutil, opencv-python, mediapipe, numpy

**Working Directory:** `/Users/wj.cho/dev/poc/king-game/mouse-game/`

---

## Chunk 1: 기반 파일 — requirements.txt / config.py / 모델 파일

### Task 1: requirements.txt 업데이트

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: requirements.txt에 motion-game 의존성 추가**

파일 전체를 아래로 교체:

```
PySide6>=6.10
psutil>=5.9
opencv-python>=4.8
mediapipe>=0.10
numpy>=1.24
```

- [ ] **Step 2: 의존성 설치 확인**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
pip install -r requirements.txt
```

Expected: 에러 없이 설치 완료 (이미 설치됐으면 "already satisfied")

---

### Task 2: pose_landmarker_lite.task 모델 파일 복사

**Files:**
- Copy: `../motion-game/pose_landmarker_lite.task` → `pose_landmarker_lite.task`

- [ ] **Step 1: 모델 파일 복사**

```bash
cp /Users/wj.cho/dev/poc/king-game/motion-game/pose_landmarker_lite.task \
   /Users/wj.cho/dev/poc/king-game/mouse-game/pose_landmarker_lite.task
```

Expected: 파일 복사 완료

- [ ] **Step 2: 파일 존재 확인**

```bash
ls -lh /Users/wj.cho/dev/poc/king-game/mouse-game/pose_landmarker_lite.task
```

Expected: 파일 크기 약 4MB 전후

---

### Task 3: config.py 수정 — keyboard/motion 필드 추가

**Files:**
- Modify: `config.py`

현재 `AppConfig` 데이터클래스에 아래 4개 필드가 없다. `goal_score: int = 200` 아래에 추가한다.

- [ ] **Step 1: config.py의 AppConfig 데이터클래스에 필드 추가**

`goal_score: int = 200` 줄 바로 아래에 추가:

```python
    # Keyboard game
    accuracy_threshold: int = 80    # % 정확도 기준 (0-100)
    time_limit_keyboard: int = 30   # 초

    # Motion game
    motion_reps: int = 5            # 목표 반복 횟수
    time_limit_motion: int = 40     # 초
```

- [ ] **Step 2: load() 메서드에서 새 필드 읽기 추가**

`config.goal_score = data.get("goal_score", 200)` 줄 아래에 추가:

```python
                config.accuracy_threshold = data.get("accuracy_threshold", 80)
                config.time_limit_keyboard = data.get("time_limit_keyboard", 30)
                config.motion_reps = data.get("motion_reps", 5)
                config.time_limit_motion = data.get("time_limit_motion", 40)
```

- [ ] **Step 3: 파이썬 임포트로 syntax 확인**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
python -c "from config import AppConfig; c = AppConfig(); print(c.accuracy_threshold, c.motion_reps)"
```

Expected: `80 5`

---

## Chunk 2: keyboard_game.py 작성

### Task 4: KeyboardGameWidget 작성

**Files:**
- Create: `keyboard_game.py`

keyboard-game/poc.py의 `TypingPoC` 위젯을 PySide6로 포팅하되, 게임 완료 조건(정확도 ≥ threshold, 제한 시간)과 공통 시그널(game_success/failed/quit)을 추가한다.

- [ ] **Step 1: keyboard_game.py 생성**

```python
"""타자 게임 위젯 모듈 — 명언 타이핑으로 앱 잠금 해제"""

import random
import time

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton,
)
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont, QColor


# 명언 목록 (문장, 저자)
QUOTES = [
    ("삶이 있는 한 희망은 있다", "키케로"),
    ("산다는 것 그것은 치열한 전투이다", "로맹 롤랑"),
    ("하루에 3시간을 걸으면 7년 후에 지구를 한 바퀴 돌 수 있다", "새뮤얼 존슨"),
    ("언제나 현재에 집중할 수 있다면 행복할 것이다", "파울로 코엘료"),
    ("피할 수 없으면 즐겨라", "로버트 엘리엇"),
    ("내일은 내일의 태양이 뜬다", "마거릿 미첼"),
    ("행복은 습관이다, 그것을 몸에 지니라", "엘버트 허버드"),
    ("단순하게 살아라. 현대인은 쓸데없는 절차와 일 때문에 얼마나 복잡한 삶을 살아가는가?", "이디스 워튼"),
    ("먼저 자신을 비웃어라. 다른 사람이 당신을 비웃기 전에", "엘사 맥스웰"),
    ("우리를 향해 열린 문을 보지 못하게 된다", "헬렌 켈러"),
    ("자신감 있는 표정을 지으면 자신감이 생긴다", "찰스 다윈"),
    ("실패는 잊어라. 그러나 그것이 준 교훈은 절대 잊지 마라", "허버트 개서"),
    ("1퍼센트의 가능성, 그것이 나의 길이다", "나폴레옹"),
    ("꿈을 계속 간직하고 있으면 반드시 실현할 때가 온다", "괴테"),
    ("고통이 남기고 간 뒤를 보라. 고난이 지나면 반드시 기쁨이 스며든다", "괴테"),
    ("마음만을 가지고 있어서는 안 된다. 반드시 실천하여야 한다", "이소룡"),
    ("가장 큰 실수는 포기해 버리는 것이다", "조 지라드"),
    ("성공의 비결은 단 한 가지, 잘할 수 있는 일에 광적으로 집중하는 것이다", "톰 모나한"),
    ("문제점을 찾지 말고 해결책을 찾으라", "헨리 포드"),
    ("길을 잃는다는 것은 곧 길을 알게 된다는 것이다", "동아프리카 속담"),
]

DARK_BG = "#0f0f23"
CARD_BG = "#1a1a2e"
ACCENT = "#4ECDC4"
DANGER = "#FF6B6B"
TEXT_PRIMARY = "#e2e8f0"
TEXT_SECONDARY = "#94a3b8"
BORDER = "#2d3748"


class KeyboardGameWidget(QWidget):
    """타자 게임 위젯

    랜덤 명언 1문장을 제시하고 정확도 ≥ threshold% 달성 시 game_success.
    제한 시간 초과 또는 미달 시 game_failed.
    """

    game_success = Signal()
    game_failed = Signal()
    game_quit = Signal()

    def __init__(self, accuracy_threshold: int = 80, time_limit: int = 30, parent=None):
        super().__init__(parent)
        self.accuracy_threshold = accuracy_threshold
        self.time_limit = time_limit
        self.app_name = ""
        self.app_path = ""

        self._started = False
        self._start_time = 0.0
        self._remaining = float(time_limit)
        self._finished = False

        self._quotes = QUOTES[:]
        random.shuffle(self._quotes)
        self._target = ""
        self._author = ""

        self._init_ui()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._tick)

    # ── public API ──────────────────────────────────────

    def update_settings(self, accuracy_threshold: int, time_limit: int):
        self.accuracy_threshold = accuracy_threshold
        self.time_limit = time_limit

    def start_game(self, app_name: str, app_path: str):
        self.app_name = app_name
        self.app_path = app_path
        self._pick_random_quote()
        self._reset_state()
        self._fail_overlay.hide()
        self._ui_timer.start()
        self._input.setFocus()

    # ── UI 초기화 ───────────────────────────────────────

    def _init_ui(self):
        self.setStyleSheet(f"background-color: {DARK_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        # 헤더
        self._header_label = QLabel()
        self._header_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self._header_label.setStyleSheet(f"color: {ACCENT};")
        layout.addWidget(self._header_label)

        # 통계 바 (시간 / 정확도)
        stats_row = QHBoxLayout()
        self._time_label = QLabel()
        self._time_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self._time_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self._acc_label = QLabel()
        self._acc_label.setFont(QFont("Arial", 13))
        self._acc_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        stats_row.addWidget(self._time_label)
        stats_row.addStretch()
        stats_row.addWidget(self._acc_label)
        layout.addLayout(stats_row)

        # 명언 표시
        self._quote_label = QLabel()
        self._quote_label.setWordWrap(True)
        self._quote_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._quote_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background-color: {CARD_BG};"
            f"border-radius: 10px; padding: 20px;"
        )
        self._quote_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._quote_label)

        # 입력창
        input_label = QLabel("여기에 입력하세요:")
        input_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(input_label)

        self._input = QLineEdit()
        self._input.setFont(QFont("Arial", 15))
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {CARD_BG};
                color: {TEXT_PRIMARY};
                border: 2px solid {BORDER};
                border-radius: 8px;
                padding: 10px 14px;
            }}
            QLineEdit:focus {{
                border-color: {ACCENT};
            }}
        """)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_enter)
        layout.addWidget(self._input)

        # 안내 텍스트
        hint = QLabel("입력 후 Enter — 정확도가 기준 이상이면 클리어!")
        hint.setFont(QFont("Arial", 11))
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addStretch()

        # 포기 버튼
        quit_btn = QPushButton("🏠 포기하고 돌아가기")
        quit_btn.setFont(QFont("Arial", 12))
        quit_btn.setFixedHeight(40)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BORDER};
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #3d4f6f;
                color: {TEXT_PRIMARY};
            }}
        """)
        quit_btn.clicked.connect(self._quit_game)
        layout.addWidget(quit_btn)

        # 실패 오버레이
        self._fail_overlay = QWidget(self)
        self._fail_overlay.setStyleSheet("background-color: rgba(0,0,0,180);")
        self._fail_overlay.hide()

        fail_layout = QVBoxLayout(self._fail_overlay)
        fail_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.setSpacing(16)

        fail_title = QLabel("💥 실패!")
        fail_title.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        fail_title.setStyleSheet("color: #FF6B6B; background: transparent;")
        fail_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.addWidget(fail_title)

        self._fail_reason = QLabel("")
        self._fail_reason.setFont(QFont("Arial", 16))
        self._fail_reason.setStyleSheet("color: #e2e8f0; background: transparent;")
        self._fail_reason.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.addWidget(self._fail_reason)

        fail_layout.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(20)

        retry_btn = QPushButton("🔄 재도전")
        retry_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        retry_btn.setFixedSize(180, 55)
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        retry_btn.setStyleSheet("""
            QPushButton { background-color: #4ECDC4; color: #fff;
                          border: none; border-radius: 12px; }
            QPushButton:hover { background-color: #45B7B8; }
        """)
        retry_btn.clicked.connect(self._retry)
        btn_row.addWidget(retry_btn)

        back_btn = QPushButton("🏠 돌아가기")
        back_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        back_btn.setFixedSize(180, 55)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton { background-color: #2d3748; color: #e2e8f0;
                          border: 2px solid #4a5568; border-radius: 12px; }
            QPushButton:hover { background-color: #3d4f6f; }
        """)
        back_btn.clicked.connect(self._quit_game)
        btn_row.addWidget(back_btn)

        fail_layout.addLayout(btn_row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fail_overlay.isVisible():
            self._fail_overlay.setGeometry(0, 0, self.width(), self.height())

    # ── 상태 관리 ───────────────────────────────────────

    def _pick_random_quote(self):
        quote, author = random.choice(self._quotes)
        self._target = quote
        self._author = author
        self._quote_label.setText(f"{quote}\n— {author}")

    def _reset_state(self):
        self._started = False
        self._start_time = 0.0
        self._remaining = float(self.time_limit)
        self._finished = False
        self._input.clear()
        self._header_label.setText(f"⌨️ {self.app_name}을(를) 실행하려면 타자를 클리어하세요!")
        self._update_stats_labels("", 0.0)

    def _update_stats_labels(self, current_text: str, elapsed: float):
        remaining = max(self.time_limit - elapsed, 0.0)
        color = ACCENT if remaining > 5 else DANGER
        self._time_label.setText(f"⏱ {remaining:.1f}초")
        self._time_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")

        acc = self._calc_accuracy(current_text)
        acc_color = ACCENT if acc >= self.accuracy_threshold else DANGER
        self._acc_label.setText(f"정확도: {acc:.0f}% (목표 {self.accuracy_threshold}%)")
        self._acc_label.setStyleSheet(f"color: {acc_color}; font-size: 13px;")

    # ── 계산 ────────────────────────────────────────────

    def _calc_accuracy(self, text: str) -> float:
        if not text:
            return 100.0
        correct = sum(1 for i, c in enumerate(text) if i < len(self._target) and c == self._target[i])
        return (correct / len(text)) * 100.0

    # ── 이벤트 핸들러 ────────────────────────────────────

    def _on_text_changed(self, text: str):
        if not self._started and text:
            self._started = True
            self._start_time = time.time()
        elapsed = time.time() - self._start_time if self._started else 0.0
        self._update_stats_labels(text, elapsed)

    def _tick(self):
        if not self._started or self._finished:
            return
        elapsed = time.time() - self._start_time
        self._update_stats_labels(self._input.text(), elapsed)
        if elapsed >= self.time_limit:
            self._on_fail("시간 초과!")

    def _on_enter(self):
        if self._finished:
            return
        text = self._input.text()
        acc = self._calc_accuracy(text)
        if acc >= self.accuracy_threshold:
            self._on_success()
        else:
            self._on_fail(f"정확도 {acc:.0f}% — 목표 {self.accuracy_threshold}% 미달")

    def _on_success(self):
        self._finished = True
        self._ui_timer.stop()
        QTimer.singleShot(500, lambda: self.game_success.emit())

    def _on_fail(self, reason: str = ""):
        self._finished = True
        self._ui_timer.stop()
        self._fail_reason.setText(reason)
        self._fail_overlay.setGeometry(0, 0, self.width(), self.height())
        self._fail_overlay.show()
        self._fail_overlay.raise_()
        self.game_failed.emit()

    def _retry(self):
        self._fail_overlay.hide()
        self._pick_random_quote()
        self._reset_state()
        self._ui_timer.start()
        self._input.setFocus()

    def _quit_game(self):
        self._finished = True
        self._ui_timer.stop()
        self._fail_overlay.hide()
        self.game_quit.emit()
```

- [ ] **Step 2: syntax 확인**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
python -c "from keyboard_game import KeyboardGameWidget; print('OK')"
```

Expected: `OK`

---

## Chunk 3: motion_game.py 작성

### Task 5: MotionGameWidget 작성

**Files:**
- Create: `motion_game.py`

squat_poc.py / pushup_poc.py / situp_poc.py의 VideoThread + 각도 계산 로직을 1파일로 통합. PyQt5 → PySide6 마이그레이션. EXERCISES 리스트로 종목 분기. lazy import + 카메라 폴백.

- [ ] **Step 1: motion_game.py 생성**

```python
"""모션 게임 위젯 모듈 — 스쿼트/푸쉬업/싯업 카운터로 앱 잠금 해제

- PySide6 + MediaPipe Tasks API
- start_game() 시 3종목 중 랜덤 선택
- 목표 횟수(motion_reps) 달성 + 제한 시간(time_limit) 기반 클리어
- MediaPipe/카메라 불가 시 즉시 game_quit emit (폴백)
"""

import os
import random

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox,
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont

# ── 종목 정의 ────────────────────────────────────────────────
# joints: (a_idx, b_idx, c_idx)  — b가 꼭짓점
# state machine: angle < down_threshold → "DOWN", angle > up_threshold → "UP" (+1)
# situp은 반전: angle > down_threshold → "DOWN", angle < up_threshold → "UP"
EXERCISES = [
    {
        "name": "스쿼트", "emoji": "🏋️",
        "joints": (24, 26, 28),          # RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE
        "down_threshold": 90,
        "up_threshold": 160,
        "inverted": False,               # DOWN=꺾임(작은 각도), UP=펼침(큰 각도)
    },
    {
        "name": "푸쉬업", "emoji": "💪",
        "joints": (12, 14, 16),          # RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST
        "down_threshold": 90,
        "up_threshold": 160,
        "inverted": False,
    },
    {
        "name": "싯업", "emoji": "🧘",
        "joints": (12, 24, 26),          # RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE
        "down_threshold": 60,
        "up_threshold": 120,
        "inverted": True,                # DOWN=누움(큰 각도), UP=일어남(작은 각도)
    },
]

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "pose_landmarker_lite.task")

_POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
]

DARK_BG = "#0f0f23"
CARD_BG = "#1a1a2e"
ACCENT = "#4ECDC4"
DANGER = "#FF6B6B"
TEXT_PRIMARY = "#e2e8f0"
TEXT_SECONDARY = "#94a3b8"
BORDER = "#2d3748"


def _calculate_angle(a, b, c):
    """세 점(a-b-c)에서 b를 꼭짓점으로 하는 각도 계산 (0~180°)"""
    import math
    a, b, c = [float(x) for x in a], [float(x) for x in b], [float(x) for x in c]
    radians = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
    angle = abs(math.degrees(radians))
    return 360 - angle if angle > 180 else angle


def _get_available_cameras(max_test: int = 5):
    """사용 가능한 카메라 목록 반환. (index, name) 튜플 리스트."""
    import cv2
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
        av_devices = list(AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo))
        valid_opencv = []
        for i in range(max_test):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                valid_opencv.append(i)
                cap.release()
        external = [d for d in av_devices if "iPhone" in (d.modelID() or "")]
        internal = [d for d in av_devices if "iPhone" not in (d.modelID() or "")]
        ordered = external + internal
        cameras = []
        for i, opencv_idx in enumerate(valid_opencv):
            name = ordered[i].localizedName() if i < len(ordered) else f"카메라 {opencv_idx}"
            cameras.append((opencv_idx, name))
        return cameras
    except Exception:
        cameras = []
        for i in range(max_test):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append((i, f"카메라 {i}"))
                cap.release()
        return cameras


def _get_default_camera_index(cameras):
    macbook_keywords = ("MacBook", "FaceTime", "Built-in", "내장", "Apple Camera")
    for idx, name in cameras:
        if any(kw in name for kw in macbook_keywords):
            return idx
    return cameras[0][0] if cameras else 0


# ── 영상 처리 스레드 ─────────────────────────────────────────

class VideoThread(QThread):
    frame_ready = Signal(QImage)
    rep_updated = Signal(int)
    state_changed = Signal(str)
    angle_updated = Signal(float)

    def __init__(self, camera_index: int, exercise: dict, parent=None):
        super().__init__(parent)
        self._running = True
        self.camera_index = camera_index
        self.exercise = exercise
        self.count = 0
        self.stage = "UP"

    def run(self):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision as mp_vision

        a_idx, b_idx, c_idx = self.exercise["joints"]
        down_thr = self.exercise["down_threshold"]
        up_thr = self.exercise["up_threshold"]
        inverted = self.exercise["inverted"]

        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=mp_vision.RunningMode.VIDEO,
        )
        cap = cv2.VideoCapture(self.camera_index)
        timestamp_ms = 0

        with mp_vision.PoseLandmarker.create_from_options(options) as landmarker:
            while self._running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(mp_img, timestamp_ms)
                timestamp_ms += 33

                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    h, w = frame.shape[:2]

                    pa = [lm[a_idx].x, lm[a_idx].y]
                    pb = [lm[b_idx].x, lm[b_idx].y]
                    pc = [lm[c_idx].x, lm[c_idx].y]
                    angle = _calculate_angle(pa, pb, pc)
                    self.angle_updated.emit(round(angle, 1))

                    if not inverted:
                        # DOWN=작은 각도, UP=큰 각도
                        if angle < down_thr and self.stage != "DOWN":
                            self.stage = "DOWN"
                            self.state_changed.emit("DOWN")
                        if angle > up_thr and self.stage == "DOWN":
                            self.stage = "UP"
                            self.count += 1
                            self.state_changed.emit("UP")
                            self.rep_updated.emit(self.count)
                    else:
                        # inverted: DOWN=큰 각도, UP=작은 각도
                        if angle > down_thr and self.stage != "DOWN":
                            self.stage = "DOWN"
                            self.state_changed.emit("DOWN")
                        if angle < up_thr and self.stage == "DOWN":
                            self.stage = "UP"
                            self.count += 1
                            self.state_changed.emit("UP")
                            self.rep_updated.emit(self.count)

                    # 스켈레톤 오버레이
                    pts = [(int(p.x * w), int(p.y * h)) for p in lm]
                    for ai, bi in _POSE_CONNECTIONS:
                        cv2.line(frame, pts[ai], pts[bi], (0, 255, 0), 2)
                    for pt in pts:
                        cv2.circle(frame, pt, 4, (0, 0, 255), -1)

                h, w, ch = frame.shape
                qt_img = QImage(frame.data, w, h, ch * w, QImage.Format.Format_BGR888)
                self.frame_ready.emit(qt_img.copy())

        cap.release()

    def stop(self):
        self._running = False
        self.wait()


# ── 메인 위젯 ────────────────────────────────────────────────

class MotionGameWidget(QWidget):
    """모션 게임 위젯

    start_game() 시 3종목 중 랜덤으로 1종목 선택.
    목표 횟수 달성 → game_success.
    제한 시간 초과 → game_failed.
    MediaPipe/카메라 불가 → game_quit (폴백용).
    """

    game_success = Signal()
    game_failed = Signal()
    game_quit = Signal()

    def __init__(self, motion_reps: int = 5, time_limit: int = 40, parent=None):
        super().__init__(parent)
        self.motion_reps = motion_reps
        self.time_limit = time_limit
        self.app_name = ""
        self.app_path = ""

        self._thread = None
        self._rep = 0
        self._state = "UP"
        self._angle = 0.0
        self._remaining = float(time_limit)
        self._exercise = None
        self._finished = False

        self._init_ui()

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(200)
        self._countdown_timer.timeout.connect(self._tick)

    # ── public API ──────────────────────────────────────

    def update_settings(self, motion_reps: int, time_limit: int):
        self.motion_reps = motion_reps
        self.time_limit = time_limit

    def start_game(self, app_name: str, app_path: str):
        self.app_name = app_name
        self.app_path = app_path

        # 의존성/카메라 확인 (lazy)
        try:
            import cv2
            import mediapipe  # noqa: F401
            cameras = _get_available_cameras()
            if not cameras:
                raise RuntimeError("카메라 없음")
            camera_index = _get_default_camera_index(cameras)
        except Exception:
            QTimer.singleShot(0, lambda: self.game_quit.emit())
            return

        self._exercise = random.choice(EXERCISES)
        self._rep = 0
        self._state = "UP"
        self._angle = 0.0
        self._remaining = float(self.time_limit)
        self._finished = False
        self._fail_overlay.hide()

        self._header_label.setText(
            f"🏃 {app_name}을(를) 실행하려면 "
            f"{self._exercise['emoji']} {self._exercise['name']} "
            f"{self.motion_reps}회를 클리어하세요!"
        )
        self._refresh_hud()

        # 카메라 콤보 업데이트
        self._cam_combo.blockSignals(True)
        self._cam_combo.clear()
        for idx, name in _get_available_cameras():
            self._cam_combo.addItem(name, idx)
        default_idx = _get_default_camera_index(_get_available_cameras())
        for i in range(self._cam_combo.count()):
            if self._cam_combo.itemData(i) == default_idx:
                self._cam_combo.setCurrentIndex(i)
                break
        self._cam_combo.blockSignals(False)

        self._start_thread(camera_index)
        self._countdown_timer.start()

    # ── UI 초기화 ───────────────────────────────────────

    def _init_ui(self):
        self.setStyleSheet(f"background-color: {DARK_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # HUD
        hud = QWidget()
        hud.setFixedHeight(60)
        hud.setStyleSheet(f"background-color: {CARD_BG};")
        hud_layout = QHBoxLayout(hud)
        hud_layout.setContentsMargins(12, 0, 12, 0)

        self._header_label = QLabel()
        self._header_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self._header_label.setStyleSheet(f"color: {ACCENT};")
        hud_layout.addWidget(self._header_label, 1)

        self._cam_combo = QComboBox()
        self._cam_combo.setFixedWidth(180)
        self._cam_combo.setStyleSheet(f"""
            QComboBox {{ background: #16213e; color: {TEXT_PRIMARY};
                         border: 1px solid {BORDER}; padding: 2px 8px; border-radius: 4px; }}
            QComboBox::drop-down {{ border: none; }}
        """)
        self._cam_combo.currentIndexChanged.connect(self._on_camera_changed)
        hud_layout.addWidget(self._cam_combo)
        layout.addWidget(hud)

        # 상태 HUD
        self._hud_label = QLabel("횟수: 0 / 0   상태: UP   각도: 0°   ⏱ 0.0초")
        self._hud_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hud_label.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        self._hud_label.setStyleSheet(
            f"background-color: #1e1e2e; color: {ACCENT}; padding: 8px;"
        )
        self._hud_label.setFixedHeight(45)
        layout.addWidget(self._hud_label)

        # 카메라 피드
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self._video_label, 1)

        # 하단 버튼
        btn_widget = QWidget()
        btn_widget.setStyleSheet(f"background-color: {CARD_BG};")
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(16, 8, 16, 8)

        quit_btn = QPushButton("🏠 포기하고 돌아가기")
        quit_btn.setFont(QFont("Arial", 12))
        quit_btn.setFixedHeight(38)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {BORDER}; color: {TEXT_SECONDARY};
                           border: none; border-radius: 8px; }}
            QPushButton:hover {{ background-color: #3d4f6f; color: {TEXT_PRIMARY}; }}
        """)
        quit_btn.clicked.connect(self._quit_game)
        btn_layout.addStretch()
        btn_layout.addWidget(quit_btn)
        layout.addWidget(btn_widget)

        # 실패 오버레이
        self._fail_overlay = QWidget(self)
        self._fail_overlay.setStyleSheet("background-color: rgba(0,0,0,180);")
        self._fail_overlay.hide()

        fail_layout = QVBoxLayout(self._fail_overlay)
        fail_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.setSpacing(16)

        fail_title = QLabel("💥 시간 초과!")
        fail_title.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        fail_title.setStyleSheet("color: #FF6B6B; background: transparent;")
        fail_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.addWidget(fail_title)

        fail_layout.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(20)

        retry_btn = QPushButton("🔄 재도전")
        retry_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        retry_btn.setFixedSize(180, 55)
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        retry_btn.setStyleSheet("""
            QPushButton { background-color: #4ECDC4; color: #fff;
                          border: none; border-radius: 12px; }
            QPushButton:hover { background-color: #45B7B8; }
        """)
        retry_btn.clicked.connect(self._retry)
        btn_row.addWidget(retry_btn)

        back_btn = QPushButton("🏠 돌아가기")
        back_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        back_btn.setFixedSize(180, 55)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton { background-color: #2d3748; color: #e2e8f0;
                          border: 2px solid #4a5568; border-radius: 12px; }
            QPushButton:hover { background-color: #3d4f6f; }
        """)
        back_btn.clicked.connect(self._quit_game)
        btn_row.addWidget(back_btn)

        fail_layout.addLayout(btn_row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fail_overlay.isVisible():
            self._fail_overlay.setGeometry(0, 0, self.width(), self.height())

    # ── VideoThread 관리 ────────────────────────────────

    def _start_thread(self, camera_index: int):
        self._thread = VideoThread(camera_index, self._exercise, self)
        self._thread.frame_ready.connect(self._update_frame)
        self._thread.rep_updated.connect(self._update_rep)
        self._thread.state_changed.connect(self._update_state)
        self._thread.angle_updated.connect(self._update_angle)
        self._thread.start()

    def _stop_thread(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread = None

    def _on_camera_changed(self, combo_index: int):
        if self._thread and not self._finished:
            camera_index = self._cam_combo.itemData(combo_index)
            self._stop_thread()
            self._start_thread(camera_index)

    # ── 시그널 수신 ─────────────────────────────────────

    def _update_frame(self, qt_img: QImage):
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self._video_label.width(),
            self._video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(pixmap)

    def _update_rep(self, count: int):
        self._rep = count
        self._refresh_hud()
        if count >= self.motion_reps:
            self._on_success()

    def _update_state(self, state: str):
        self._state = state
        self._refresh_hud()

    def _update_angle(self, angle: float):
        self._angle = angle
        self._refresh_hud()

    # ── 게임 로직 ────────────────────────────────────────

    def _tick(self):
        if self._finished:
            return
        self._remaining -= 0.2
        self._refresh_hud()
        if self._remaining <= 0:
            self._on_fail()

    def _refresh_hud(self):
        color = ACCENT if self._state == "UP" else "#f97316"
        self._hud_label.setStyleSheet(
            f"background-color: #1e1e2e; color: {color}; padding: 8px; font-weight: bold;"
        )
        name = self._exercise["name"] if self._exercise else ""
        self._hud_label.setText(
            f"{name}  횟수: {self._rep}/{self.motion_reps}   "
            f"상태: {self._state}   각도: {self._angle:.0f}°   "
            f"⏱ {max(self._remaining, 0):.0f}초"
        )

    def _on_success(self):
        if self._finished:
            return
        self._finished = True
        self._countdown_timer.stop()
        self._stop_thread()
        QTimer.singleShot(500, lambda: self.game_success.emit())

    def _on_fail(self):
        if self._finished:
            return
        self._finished = True
        self._countdown_timer.stop()
        self._stop_thread()
        self._fail_overlay.setGeometry(0, 0, self.width(), self.height())
        self._fail_overlay.show()
        self._fail_overlay.raise_()
        self.game_failed.emit()

    def _retry(self):
        self._fail_overlay.hide()
        self.start_game(self.app_name, self.app_path)

    def _quit_game(self):
        self._finished = True
        self._countdown_timer.stop()
        self._stop_thread()
        self._fail_overlay.hide()
        self.game_quit.emit()

    def closeEvent(self, event):
        self._stop_thread()
        super().closeEvent(event)
```

- [ ] **Step 2: syntax 확인**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
python -c "from motion_game import MotionGameWidget; print('OK')"
```

Expected: `OK`

---

## Chunk 4: main_window.py 수정

### Task 6: main_window.py 수정 — 게임 라우터 + 설정 UI 확장

**Files:**
- Modify: `main_window.py`

아래 변경 사항을 순서대로 적용한다.

---

#### Step 1: import 추가 (파일 상단)

- [ ] **Step 1: keyboard_game, motion_game import 추가**

`from bug_game import BugGameWidget` 줄 아래에 추가:

```python
from keyboard_game import KeyboardGameWidget
from motion_game import MotionGameWidget
```

---

#### Step 2: MainWindow.__init__ 수정

- [ ] **Step 2: __init__에 pending 상태 변수 추가 + 새 위젯 스택 등록**

`self._monitoring = False` 줄 아래에 추가:

```python
        self._pending_game_type = ""   # 현재 게임 종류 (motion 폴백 판별용)
        self._pending_app_name = ""
        self._pending_app_path = ""
```

기존 코드:
```python
        # 벌레 게임 위젯 (stack index 2)
        self.bug_widget = BugGameWidget(
            self.config.time_limit_bug, self.config.goal_score
        )
        self.bug_widget.game_success.connect(self._on_game_success)
        self.bug_widget.game_failed.connect(self._on_game_failed)
        self.bug_widget.game_quit.connect(self._on_game_quit)
        self.stack.addWidget(self.bug_widget)
```

위 코드 블록 바로 **아래**에 추가:

```python
        # 타자 게임 위젯 (stack index 3)
        self.keyboard_widget = KeyboardGameWidget(
            self.config.accuracy_threshold, self.config.time_limit_keyboard
        )
        self.keyboard_widget.game_success.connect(self._on_game_success)
        self.keyboard_widget.game_failed.connect(self._on_game_failed)
        self.keyboard_widget.game_quit.connect(self._on_game_quit)
        self.stack.addWidget(self.keyboard_widget)

        # 모션 게임 위젯 (stack index 4)
        self.motion_widget = MotionGameWidget(
            self.config.motion_reps, self.config.time_limit_motion
        )
        self.motion_widget.game_success.connect(self._on_game_success)
        self.motion_widget.game_failed.connect(self._on_game_failed)
        self.motion_widget.game_quit.connect(self._on_motion_game_quit)
        self.stack.addWidget(self.motion_widget)
```

주의: motion_widget의 game_quit은 `_on_motion_game_quit` (폴백 처리)에 연결.

---

#### Step 3: _build_settings_page 수정 — 게임 선택 콤보박스 제거, 새 파라미터 추가

- [ ] **Step 3: 게임 선택 콤보박스 블록 제거**

아래 블록 전체를 찾아서 제거:

```python
        # 게임 선택
        settings_layout.addWidget(QLabel("게임:"))
        self.game_type_combo = QComboBox()
        self.game_type_combo.addItem("🎯 에임 게임", "aim")
        self.game_type_combo.addItem("🪲 벌레 잡기", "bug")
        self.game_type_combo.setCurrentIndex(0 if self.config.game_type == "aim" else 1)
        self.game_type_combo.currentIndexChanged.connect(self._on_game_type_changed)
        settings_layout.addWidget(self.game_type_combo)

        settings_layout.addSpacing(16)
```

- [ ] **Step 4: subtitle 텍스트 변경**

기존:
```python
        subtitle = QLabel("프로그램을 실행하기 전에 에임 트레이닝을 클리어하세요!")
```
변경:
```python
        subtitle = QLabel("프로그램을 실행하면 랜덤 미니게임이 시작됩니다. 클리어하면 앱이 허용됩니다!")
```

- [ ] **Step 5: settings_frame 내부에 타자/모션 파라미터 추가**

기존 `layout.addWidget(settings_frame)` 직전의 `settings_layout.addSpacing(8)` 이후, `layout.addWidget(settings_frame)` 바로 위에 두 번째 settings_frame 줄을 추가하는 대신, 기존 `settings_frame`의 `settings_layout`을 그대로 이어서 사용한다.

`self.bug_time_combo.addItem(...)` 루프가 끝나고 `settings_layout.addWidget(self.bug_time_combo)` 직후에 추가:

```python
        settings_layout.addSpacing(16)

        # ── 타자 설정 ──────────────────────────
        settings_layout.addWidget(QLabel("⌨️ 타자:"))

        self.keyboard_acc_label = QLabel("정확도:")
        settings_layout.addWidget(self.keyboard_acc_label)
        self.keyboard_acc_combo = QComboBox()
        acc_options = [60, 70, 80, 90, 100]
        for a in acc_options:
            self.keyboard_acc_combo.addItem(f"{a}%", a)
        idx_acc = acc_options.index(self.config.accuracy_threshold) if self.config.accuracy_threshold in acc_options else 2
        self.keyboard_acc_combo.setCurrentIndex(idx_acc)
        settings_layout.addWidget(self.keyboard_acc_combo)

        settings_layout.addSpacing(8)

        self.keyboard_time_label = QLabel("제한 시간:")
        settings_layout.addWidget(self.keyboard_time_label)
        self.keyboard_time_combo = QComboBox()
        kb_time_options = [15, 20, 30, 45, 60]
        for t in kb_time_options:
            self.keyboard_time_combo.addItem(f"{t}초", t)
        idx_kt = kb_time_options.index(self.config.time_limit_keyboard) if self.config.time_limit_keyboard in kb_time_options else 2
        self.keyboard_time_combo.setCurrentIndex(idx_kt)
        settings_layout.addWidget(self.keyboard_time_combo)

        settings_layout.addSpacing(16)

        # ── 모션 설정 ──────────────────────────
        settings_layout.addWidget(QLabel("🏋️ 모션:"))

        self.motion_reps_label = QLabel("목표 횟수:")
        settings_layout.addWidget(self.motion_reps_label)
        self.motion_reps_combo = QComboBox()
        reps_options = [3, 5, 7, 10, 15]
        for r in reps_options:
            self.motion_reps_combo.addItem(f"{r}회", r)
        idx_reps = reps_options.index(self.config.motion_reps) if self.config.motion_reps in reps_options else 1
        self.motion_reps_combo.setCurrentIndex(idx_reps)
        settings_layout.addWidget(self.motion_reps_combo)

        settings_layout.addSpacing(8)

        self.motion_time_label = QLabel("제한 시간:")
        settings_layout.addWidget(self.motion_time_label)
        self.motion_time_combo = QComboBox()
        mt_options = [20, 30, 40, 60, 90]
        for t in mt_options:
            self.motion_time_combo.addItem(f"{t}초", t)
        idx_mt = mt_options.index(self.config.time_limit_motion) if self.config.time_limit_motion in mt_options else 2
        self.motion_time_combo.setCurrentIndex(idx_mt)
        settings_layout.addWidget(self.motion_time_combo)
```

---

#### Step 4: _on_process_detected 수정 — 랜덤 게임 선택

- [ ] **Step 6: _on_process_detected 전체 교체**

기존 `_on_process_detected` 메서드 전체를 아래로 교체:

```python
    @Slot(str, str)
    def _on_process_detected(self, app_name: str, app_path: str):
        """잠금 프로그램 감지됨 — 랜덤 게임 실행"""
        import random
        self._pending_app_name = app_name
        self._pending_app_path = app_path
        self._launch_game(random.choice(["aim", "bug", "keyboard", "motion"]), app_name, app_path)

    def _launch_game(self, game_type: str, app_name: str, app_path: str):
        """게임 타입에 따라 위젯 시작 + 스택 전환"""
        self._pending_game_type = game_type

        if game_type == "aim":
            target_count = self.target_combo.currentData()
            time_limit = self.time_combo.currentData()
            self.aim_widget.update_settings(target_count, time_limit)
            self.aim_widget.start_game(app_name, app_path)
            self.stack.setCurrentIndex(1)

        elif game_type == "bug":
            time_limit = self.bug_time_combo.currentData()
            goal_score = self.score_combo.currentData()
            self.bug_widget.update_settings(time_limit, goal_score)
            self.bug_widget.start_game(app_name, app_path)
            self.stack.setCurrentIndex(2)

        elif game_type == "keyboard":
            acc = self.keyboard_acc_combo.currentData()
            time_limit = self.keyboard_time_combo.currentData()
            self.keyboard_widget.update_settings(acc, time_limit)
            self.keyboard_widget.start_game(app_name, app_path)
            self.stack.setCurrentIndex(3)

        elif game_type == "motion":
            reps = self.motion_reps_combo.currentData()
            time_limit = self.motion_time_combo.currentData()
            self.motion_widget.update_settings(reps, time_limit)
            self.motion_widget.start_game(app_name, app_path)
            self.stack.setCurrentIndex(4)

        self.showNormal()
        self.activateWindow()
        self.raise_()
```

---

#### Step 5: _on_game_success 수정 — 4개 위젯 지원

- [ ] **Step 7: _on_game_success 전체 교체**

기존:
```python
        active_widget = self.aim_widget if self.stack.currentIndex() == 1 else self.bug_widget
        app_path = active_widget.app_path
```
교체:
```python
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget}
        active_widget = idx_to_widget.get(self.stack.currentIndex(), self.aim_widget)
        app_path = active_widget.app_path
```

---

#### Step 6: _on_game_quit 수정 + _on_motion_game_quit 추가

- [ ] **Step 8: _on_game_quit 전체 교체 — 4개 위젯 지원**

`_on_game_quit` 메서드 전체를 아래로 교체 (기존 process_name/clear_cooldown 로직 유지):

```python
    @Slot()
    def _on_game_quit(self):
        """게임 포기 — 설정 화면으로 돌아가기"""
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget}
        active_widget = idx_to_widget.get(self.stack.currentIndex(), self.aim_widget)
        process_name = ""
        for app in self.config.apps:
            if app["path"] == active_widget.app_path:
                process_name = app["process_name"]
                break
        if process_name:
            self.monitor.clear_cooldown(process_name)

        self.stack.setCurrentIndex(0)
```

- [ ] **Step 9: _on_motion_game_quit 메서드 추가**

`_on_game_quit` 메서드 바로 아래에 추가:

```python
    @Slot()
    def _on_motion_game_quit(self):
        """모션 게임 포기 — motion 제외 후 재추첨 (폴백 포함)"""
        import random
        # motion이 카메라/MediaPipe 실패로 즉시 quit한 경우 재추첨
        pool = ["aim", "bug", "keyboard"]
        self._launch_game(
            random.choice(pool),
            self._pending_app_name,
            self._pending_app_path,
        )
```

---

#### Step 7: _save_config 수정 — 새 필드 저장

- [ ] **Step 10: _save_config에 새 필드 추가 + game_type 관련 코드 제거**

`_save_config` 메서드 전체를 아래로 교체 (game_type_combo 참조 제거 + 새 필드 추가):

```python
    def _save_config(self):
        """현재 UI 상태를 config에 반영하고 저장"""
        for i, row in enumerate(self.app_rows):
            self.config.apps[i]["locked"] = row.toggle.is_on
        self.config.target_count = self.target_combo.currentData()
        self.config.time_limit = self.time_combo.currentData()
        self.config.time_limit_bug = self.bug_time_combo.currentData()
        self.config.goal_score = self.score_combo.currentData()
        self.config.accuracy_threshold = self.keyboard_acc_combo.currentData()
        self.config.time_limit_keyboard = self.keyboard_time_combo.currentData()
        self.config.motion_reps = self.motion_reps_combo.currentData()
        self.config.time_limit_motion = self.motion_time_combo.currentData()
        self.config.save()
```

주의: `self.config.game_type = self.game_type_combo.currentData()` 줄은 **포함하지 않는다** (game_type_combo가 제거되므로 참조 시 런타임 크래시 발생).

---

#### Step 8: 불필요한 메서드 정리

- [ ] **Step 11: _on_game_type_changed / _update_settings_visibility 메서드 제거**

게임 선택 콤보박스를 제거했으므로 아래 두 메서드를 파일에서 삭제:

```python
    def _on_game_type_changed(self):
        """게임 타입 변경 시 설정 UI 토글"""
        self._update_settings_visibility()

    def _update_settings_visibility(self):
        ...
```

그리고 `_build_settings_page`에서 `self._update_settings_visibility()` 호출도 제거.

---

#### Step 9: 전체 동작 검증

- [ ] **Step 12: 앱 실행 확인**

```bash
cd /Users/wj.cho/dev/poc/king-game/mouse-game
python main.py
```

Expected: AimGuard 설정 창이 뜨고, 에러 없이 실행됨. 설정 화면에서 타자/모션 파라미터 콤보박스가 보임.

- [ ] **Step 13: 각 게임 위젯 import 최종 확인**

```bash
python -c "
from aim_game import AimGameWidget
from bug_game import BugGameWidget
from keyboard_game import KeyboardGameWidget
from motion_game import MotionGameWidget
print('모든 게임 위젯 import OK')
"
```

Expected: `모든 게임 위젯 import OK`
