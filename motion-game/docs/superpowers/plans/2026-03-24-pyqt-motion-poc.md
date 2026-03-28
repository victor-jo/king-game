# PyQt5 Motion + Audio PoC Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PyQt5 + MediaPipe + PyAudio를 사용하여 팔굽혀펴기/윗몸일으키기/스쿼트 운동 인식과 오디오 데시벨 측정을 수행하는 4개의 독립 standalone PoC 파일을 작성한다.

**Architecture:** 각 파일은 QThread + pyqtSignal 패턴을 사용한다. VideoThread/AudioThread가 백그라운드에서 데이터를 처리하고 pyqtSignal로 MainWindow에 전달한다. 공통 모듈 없이 각 파일이 완전히 독립 실행 가능하다.

**Tech Stack:** PyQt5, OpenCV, MediaPipe Pose, PyAudio, NumPy

---

## Chunk 1: 프로젝트 초기화

### Task 1: requirements.txt 작성

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: requirements.txt 작성**

```
PyQt5>=5.15
opencv-python>=4.8
mediapipe>=0.10
pyaudio>=0.2.13
numpy>=1.24
```

- [ ] **Step 2: 의존성 설치 확인**

```bash
pip install -r requirements.txt
```

Expected: 모든 패키지 설치 성공

- [ ] **Step 3: 커밋**

```bash
git init
git add requirements.txt
git commit -m "chore: add requirements.txt"
```

---

## Chunk 2: 스쿼트 PoC

### Task 2: squat_poc.py 작성

**Files:**
- Create: `squat_poc.py`

운동 인식 PoC의 기준이 되는 첫 번째 파일. 나머지 운동 파일은 이 구조를 따른다.

- [ ] **Step 1: squat_poc.py 전체 코드 작성**

```python
"""
스쿼트 카운터 PoC
- QThread + pyqtSignal 패턴으로 UI 스레드 차단 없이 영상 처리
- MediaPipe Pose로 엉덩이-무릎-발목 각도 계산
- 각도 < 90° → DOWN, 각도 > 160° → UP (카운트 증가)
"""

import sys
import cv2
import mediapipe as mp
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QLabel
)


# ── 각도 계산 유틸 ──────────────────────────────────────────
def calculate_angle(a, b, c):
    """
    세 점으로 이루어진 각도 계산 (b가 꼭짓점).
    a, b, c: [x, y] 좌표 리스트
    반환: 0~180 사이의 각도 (degree)
    """
    a, b, c = np.array(a), np.array(b), np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) \
            - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = abs(np.degrees(radians))
    return 360 - angle if angle > 180 else angle


# ── 영상 처리 스레드 ────────────────────────────────────────
class VideoThread(QThread):
    frame_ready   = pyqtSignal(QImage)   # 변환된 프레임
    rep_updated   = pyqtSignal(int)      # 누적 횟수
    state_changed = pyqtSignal(str)      # "UP" / "DOWN"
    angle_updated = pyqtSignal(float)    # 관절 각도

    # 스쿼트 임계값
    DOWN_THRESHOLD = 90
    UP_THRESHOLD   = 160

    def __init__(self):
        super().__init__()
        self._running = True
        self.count = 0
        self.stage = "UP"

    def run(self):
        mp_pose = mp.solutions.pose
        mp_draw = mp.solutions.drawing_utils

        cap = cv2.VideoCapture(0)

        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as pose:
            while self._running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # BGR → RGB 변환 후 MediaPipe 처리
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb)

                if results.pose_landmarks:
                    lm = results.pose_landmarks.landmark

                    # 스쿼트: 오른쪽 엉덩이-무릎-발목 사용
                    hip   = [lm[mp_pose.PoseLandmark.RIGHT_HIP.value].x,
                             lm[mp_pose.PoseLandmark.RIGHT_HIP.value].y]
                    knee  = [lm[mp_pose.PoseLandmark.RIGHT_KNEE.value].x,
                             lm[mp_pose.PoseLandmark.RIGHT_KNEE.value].y]
                    ankle = [lm[mp_pose.PoseLandmark.RIGHT_ANKLE.value].x,
                             lm[mp_pose.PoseLandmark.RIGHT_ANKLE.value].y]

                    angle = calculate_angle(hip, knee, ankle)
                    self.angle_updated.emit(round(angle, 1))

                    # State machine: UP → DOWN → UP = +1
                    if angle < self.DOWN_THRESHOLD:
                        self.stage = "DOWN"
                        self.state_changed.emit("DOWN")

                    if angle > self.UP_THRESHOLD and self.stage == "DOWN":
                        self.stage = "UP"
                        self.count += 1
                        self.state_changed.emit("UP")
                        self.rep_updated.emit(self.count)

                    # 랜드마크 오버레이
                    mp_draw.draw_landmarks(
                        frame,
                        results.pose_landmarks,
                        mp_pose.POSE_CONNECTIONS
                    )

                # 프레임 → QImage 변환 후 시그널 emit
                h, w, ch = frame.shape
                qt_img = QImage(
                    frame.data, w, h,
                    ch * w, QImage.Format_BGR888
                )
                self.frame_ready.emit(qt_img)

        cap.release()

    def stop(self):
        self._running = False
        self.wait()


# ── 메인 윈도우 ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("스쿼트 카운터 PoC")
        self.resize(800, 620)

        self._rep   = 0
        self._state = "UP"
        self._angle = 0.0

        # ── 레이아웃 B: 상단 HUD + 전체 너비 카메라 ──
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 상단 HUD
        self.hud_label = QLabel("횟수: 0   상태: UP   각도: 0.0°")
        self.hud_label.setAlignment(Qt.AlignCenter)
        self.hud_label.setFixedHeight(50)
        self.hud_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.hud_label.setStyleSheet(
            "background-color: #1e1e2e; color: #f5c542; padding: 8px;"
        )
        layout.addWidget(self.hud_label)

        # 카메라 피드 (전체 너비)
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_label)

        # VideoThread 시작
        self.thread = VideoThread()
        self.thread.frame_ready.connect(self.update_frame)
        self.thread.rep_updated.connect(self.update_rep)
        self.thread.state_changed.connect(self.update_state)
        self.thread.angle_updated.connect(self.update_angle)
        self.thread.start()

    def update_frame(self, qt_img: QImage):
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self.video_label.width(),
            self.video_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

    def update_rep(self, count: int):
        self._rep = count
        self._refresh_hud()

    def update_state(self, state: str):
        self._state = state
        self._refresh_hud()

    def update_angle(self, angle: float):
        self._angle = angle
        self._refresh_hud()

    def _refresh_hud(self):
        color = "#22c55e" if self._state == "UP" else "#f97316"
        self.hud_label.setStyleSheet(
            f"background-color: #1e1e2e; color: {color}; "
            f"padding: 8px; font-size: 16pt; font-weight: bold;"
        )
        self.hud_label.setText(
            f"횟수: {self._rep}   상태: {self._state}   각도: {self._angle}°"
        )

    def closeEvent(self, event):
        self.thread.stop()
        super().closeEvent(event)


# ── 진입점 ──────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행하여 동작 확인**

```bash
python squat_poc.py
```

Expected: 창이 열리고 웹캠 피드 표시, 스쿼트 동작 시 횟수 카운트

- [ ] **Step 3: 커밋**

```bash
git add squat_poc.py
git commit -m "feat: add squat PoC with QThread + MediaPipe Pose"
```

---

## Chunk 3: 팔굽혀펴기 PoC

### Task 3: pushup_poc.py 작성

**Files:**
- Create: `pushup_poc.py`

스쿼트와 동일한 구조. 측정 관절과 임계값만 다름.
- 관절: 오른쪽 어깨(SHOULDER) → 팔꿈치(ELBOW) → 손목(WRIST)
- DOWN: angle < 90°, UP: angle > 160°

- [ ] **Step 1: pushup_poc.py 전체 코드 작성**

```python
"""
팔굽혀펴기 카운터 PoC
- QThread + pyqtSignal 패턴으로 UI 스레드 차단 없이 영상 처리
- MediaPipe Pose로 어깨-팔꿈치-손목 각도 계산
- 각도 < 90° → DOWN, 각도 > 160° → UP (카운트 증가)
"""

import sys
import cv2
import mediapipe as mp
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QLabel
)


def calculate_angle(a, b, c):
    """
    세 점으로 이루어진 각도 계산 (b가 꼭짓점).
    a, b, c: [x, y] 좌표 리스트
    반환: 0~180 사이의 각도 (degree)
    """
    a, b, c = np.array(a), np.array(b), np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) \
            - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = abs(np.degrees(radians))
    return 360 - angle if angle > 180 else angle


class VideoThread(QThread):
    frame_ready   = pyqtSignal(QImage)
    rep_updated   = pyqtSignal(int)
    state_changed = pyqtSignal(str)
    angle_updated = pyqtSignal(float)

    # 팔굽혀펴기 임계값
    DOWN_THRESHOLD = 90
    UP_THRESHOLD   = 160

    def __init__(self):
        super().__init__()
        self._running = True
        self.count = 0
        self.stage = "UP"

    def run(self):
        mp_pose = mp.solutions.pose
        mp_draw = mp.solutions.drawing_utils

        cap = cv2.VideoCapture(0)

        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as pose:
            while self._running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb)

                if results.pose_landmarks:
                    lm = results.pose_landmarks.landmark

                    # 팔굽혀펴기: 오른쪽 어깨-팔꿈치-손목
                    shoulder = [lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x,
                                lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
                    elbow    = [lm[mp_pose.PoseLandmark.RIGHT_ELBOW.value].x,
                                lm[mp_pose.PoseLandmark.RIGHT_ELBOW.value].y]
                    wrist    = [lm[mp_pose.PoseLandmark.RIGHT_WRIST.value].x,
                                lm[mp_pose.PoseLandmark.RIGHT_WRIST.value].y]

                    angle = calculate_angle(shoulder, elbow, wrist)
                    self.angle_updated.emit(round(angle, 1))

                    if angle < self.DOWN_THRESHOLD:
                        self.stage = "DOWN"
                        self.state_changed.emit("DOWN")

                    if angle > self.UP_THRESHOLD and self.stage == "DOWN":
                        self.stage = "UP"
                        self.count += 1
                        self.state_changed.emit("UP")
                        self.rep_updated.emit(self.count)

                    mp_draw.draw_landmarks(
                        frame,
                        results.pose_landmarks,
                        mp_pose.POSE_CONNECTIONS
                    )

                h, w, ch = frame.shape
                qt_img = QImage(
                    frame.data, w, h,
                    ch * w, QImage.Format_BGR888
                )
                self.frame_ready.emit(qt_img)

        cap.release()

    def stop(self):
        self._running = False
        self.wait()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("팔굽혀펴기 카운터 PoC")
        self.resize(800, 620)

        self._rep   = 0
        self._state = "UP"
        self._angle = 0.0

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hud_label = QLabel("횟수: 0   상태: UP   각도: 0.0°")
        self.hud_label.setAlignment(Qt.AlignCenter)
        self.hud_label.setFixedHeight(50)
        self.hud_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.hud_label.setStyleSheet(
            "background-color: #1e1e2e; color: #f5c542; padding: 8px;"
        )
        layout.addWidget(self.hud_label)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_label)

        self.thread = VideoThread()
        self.thread.frame_ready.connect(self.update_frame)
        self.thread.rep_updated.connect(self.update_rep)
        self.thread.state_changed.connect(self.update_state)
        self.thread.angle_updated.connect(self.update_angle)
        self.thread.start()

    def update_frame(self, qt_img: QImage):
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self.video_label.width(),
            self.video_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

    def update_rep(self, count: int):
        self._rep = count
        self._refresh_hud()

    def update_state(self, state: str):
        self._state = state
        self._refresh_hud()

    def update_angle(self, angle: float):
        self._angle = angle
        self._refresh_hud()

    def _refresh_hud(self):
        color = "#22c55e" if self._state == "UP" else "#f97316"
        self.hud_label.setStyleSheet(
            f"background-color: #1e1e2e; color: {color}; "
            f"padding: 8px; font-size: 16pt; font-weight: bold;"
        )
        self.hud_label.setText(
            f"횟수: {self._rep}   상태: {self._state}   각도: {self._angle}°"
        )

    def closeEvent(self, event):
        self.thread.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행하여 동작 확인**

```bash
python pushup_poc.py
```

Expected: 창이 열리고 웹캠 피드 표시, 팔굽혀펴기 동작 시 횟수 카운트

- [ ] **Step 3: 커밋**

```bash
git add pushup_poc.py
git commit -m "feat: add push-up PoC with shoulder-elbow-wrist angle"
```

---

## Chunk 4: 윗몸일으키기 PoC

### Task 4: situp_poc.py 작성

**Files:**
- Create: `situp_poc.py`

스쿼트/팔굽혀펴기와 동일한 구조. 측정 관절과 임계값이 다름.
- 관절: 오른쪽 어깨(SHOULDER) → 골반(HIP) → 무릎(KNEE)
- DOWN: angle > 120° (누운 상태), UP: angle < 60° (일어난 상태)
- 초기 stage = "DOWN" (누운 상태에서 시작)

- [ ] **Step 1: situp_poc.py 전체 코드 작성**

```python
"""
윗몸일으키기 카운터 PoC
- QThread + pyqtSignal 패턴으로 UI 스레드 차단 없이 영상 처리
- MediaPipe Pose로 어깨-골반-무릎 각도 계산
- 각도 > 120° → DOWN(누운 상태), 각도 < 60° → UP(일어난 상태, 카운트 증가)
"""

import sys
import cv2
import mediapipe as mp
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QLabel
)


def calculate_angle(a, b, c):
    """
    세 점으로 이루어진 각도 계산 (b가 꼭짓점).
    a, b, c: [x, y] 좌표 리스트
    반환: 0~180 사이의 각도 (degree)
    """
    a, b, c = np.array(a), np.array(b), np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) \
            - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = abs(np.degrees(radians))
    return 360 - angle if angle > 180 else angle


class VideoThread(QThread):
    frame_ready   = pyqtSignal(QImage)
    rep_updated   = pyqtSignal(int)
    state_changed = pyqtSignal(str)
    angle_updated = pyqtSignal(float)

    # 윗몸일으키기 임계값 (스쿼트/팔굽혀펴기와 반대 방향)
    DOWN_THRESHOLD = 120   # 누운 상태 (각도 큼)
    UP_THRESHOLD   = 60    # 일어난 상태 (각도 작음)

    def __init__(self):
        super().__init__()
        self._running = True
        self.count = 0
        self.stage = "DOWN"  # 누운 상태에서 시작

    def run(self):
        mp_pose = mp.solutions.pose
        mp_draw = mp.solutions.drawing_utils

        cap = cv2.VideoCapture(0)

        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as pose:
            while self._running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = pose.process(rgb)

                if results.pose_landmarks:
                    lm = results.pose_landmarks.landmark

                    # 윗몸일으키기: 오른쪽 어깨-골반-무릎
                    shoulder = [lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x,
                                lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
                    hip      = [lm[mp_pose.PoseLandmark.RIGHT_HIP.value].x,
                                lm[mp_pose.PoseLandmark.RIGHT_HIP.value].y]
                    knee     = [lm[mp_pose.PoseLandmark.RIGHT_KNEE.value].x,
                                lm[mp_pose.PoseLandmark.RIGHT_KNEE.value].y]

                    angle = calculate_angle(shoulder, hip, knee)
                    self.angle_updated.emit(round(angle, 1))

                    # 누운 상태 감지 (각도 큼)
                    if angle > self.DOWN_THRESHOLD:
                        self.stage = "DOWN"
                        self.state_changed.emit("DOWN")

                    # 일어난 상태 감지 (각도 작음) + 카운트
                    if angle < self.UP_THRESHOLD and self.stage == "DOWN":
                        self.stage = "UP"
                        self.count += 1
                        self.state_changed.emit("UP")
                        self.rep_updated.emit(self.count)

                    mp_draw.draw_landmarks(
                        frame,
                        results.pose_landmarks,
                        mp_pose.POSE_CONNECTIONS
                    )

                h, w, ch = frame.shape
                qt_img = QImage(
                    frame.data, w, h,
                    ch * w, QImage.Format_BGR888
                )
                self.frame_ready.emit(qt_img)

        cap.release()

    def stop(self):
        self._running = False
        self.wait()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("윗몸일으키기 카운터 PoC")
        self.resize(800, 620)

        self._rep   = 0
        self._state = "DOWN"
        self._angle = 0.0

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hud_label = QLabel("횟수: 0   상태: DOWN   각도: 0.0°")
        self.hud_label.setAlignment(Qt.AlignCenter)
        self.hud_label.setFixedHeight(50)
        self.hud_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.hud_label.setStyleSheet(
            "background-color: #1e1e2e; color: #f5c542; padding: 8px;"
        )
        layout.addWidget(self.hud_label)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_label)

        self.thread = VideoThread()
        self.thread.frame_ready.connect(self.update_frame)
        self.thread.rep_updated.connect(self.update_rep)
        self.thread.state_changed.connect(self.update_state)
        self.thread.angle_updated.connect(self.update_angle)
        self.thread.start()

    def update_frame(self, qt_img: QImage):
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self.video_label.width(),
            self.video_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pixmap)

    def update_rep(self, count: int):
        self._rep = count
        self._refresh_hud()

    def update_state(self, state: str):
        self._state = state
        self._refresh_hud()

    def update_angle(self, angle: float):
        self._angle = angle
        self._refresh_hud()

    def _refresh_hud(self):
        color = "#22c55e" if self._state == "UP" else "#f97316"
        self.hud_label.setStyleSheet(
            f"background-color: #1e1e2e; color: {color}; "
            f"padding: 8px; font-size: 16pt; font-weight: bold;"
        )
        self.hud_label.setText(
            f"횟수: {self._rep}   상태: {self._state}   각도: {self._angle}°"
        )

    def closeEvent(self, event):
        self.thread.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행하여 동작 확인**

```bash
python situp_poc.py
```

Expected: 창이 열리고 웹캠 피드 표시, 윗몸일으키기 동작 시 횟수 카운트

- [ ] **Step 3: 커밋**

```bash
git add situp_poc.py
git commit -m "feat: add sit-up PoC with shoulder-hip-knee angle"
```

---

## Chunk 5: 오디오 데시벨 PoC

### Task 5: audio_decibel_poc.py 작성

**Files:**
- Create: `audio_decibel_poc.py`

카메라 없이 마이크 입력만 사용. VU 미터 스타일 (녹색→노랑→빨강).

- [ ] **Step 1: audio_decibel_poc.py 전체 코드 작성**

```python
"""
오디오 데시벨 측정 PoC
- AudioThread가 PyAudio로 마이크 입력을 실시간 읽음
- RMS → dB 변환 → 0~100 정규화 후 pyqtSignal로 UI 전달
- VUMeterWidget: QPainter로 수직 막대 그리기 (녹색→노랑→빨강)
"""

import sys
import math
import numpy as np
import pyaudio
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QPainter, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLCDNumber
)


# ── 오디오 처리 스레드 ──────────────────────────────────────
class AudioThread(QThread):
    db_ready = pyqtSignal(float)   # 0.0 ~ 100.0 정규화된 dB

    CHUNK      = 1024
    FORMAT     = pyaudio.paInt16
    CHANNELS   = 1
    RATE       = 44100
    # 정규화 기준: -60dB ~ 0dB → 0 ~ 100
    DB_MIN     = -60.0
    DB_RANGE   = 60.0

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK
        )

        while self._running:
            data = stream.read(self.CHUNK, exception_on_overflow=False)
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)

            # RMS 계산 후 dB 변환 (1e-9로 log(0) 방지)
            rms = math.sqrt(np.mean(samples ** 2))
            db  = 20 * math.log10(rms + 1e-9)

            # 0~100 정규화 후 시그널 emit
            db_normalized = np.clip(
                (db - self.DB_MIN) / self.DB_RANGE * 100, 0, 100
            )
            self.db_ready.emit(float(db_normalized))

        stream.stop_stream()
        stream.close()
        pa.terminate()

    def stop(self):
        self._running = False
        self.wait()


# ── VU 미터 위젯 ────────────────────────────────────────────
class VUMeterWidget(QWidget):
    """
    수직 VU 미터 (0~100 값 기반)
    색상 구간:
      0  ~ 60  : 녹색  (안전)
      60 ~ 80  : 노란색 (주의)
      80 ~ 100 : 빨간색 (큰 소리)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.setMinimumSize(80, 300)

    def set_value(self, value: float):
        self._value = max(0.0, min(100.0, value))
        self.update()   # repaint 트리거

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        bar_w = w * 0.6
        bar_x = (w - bar_w) / 2

        # 배경
        painter.fillRect(0, 0, w, h, QColor("#1e1e2e"))

        # 채워진 높이 계산 (아래에서 위로)
        fill_ratio = self._value / 100.0
        fill_h = h * fill_ratio
        fill_y = h - fill_h

        # 색상 결정 (값에 따라)
        if self._value < 60:
            color = QColor("#22c55e")   # 녹색
        elif self._value < 80:
            color = QColor("#eab308")   # 노란색
        else:
            color = QColor("#ef4444")   # 빨간색

        # 막대 그리기
        painter.fillRect(
            int(bar_x), int(fill_y),
            int(bar_w), int(fill_h),
            color
        )

        # 눈금 라벨 (0, 25, 50, 75, 100)
        painter.setPen(QColor("#94a3b8"))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        for mark in [0, 25, 50, 75, 100]:
            y = int(h - (mark / 100.0) * h)
            painter.drawLine(int(bar_x + bar_w), y, int(bar_x + bar_w + 6), y)
            painter.drawText(int(bar_x + bar_w + 8), y + 4, f"{mark}")

        painter.end()


# ── 메인 윈도우 ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("오디오 데시벨 측정 PoC")
        self.resize(300, 450)
        self.setStyleSheet("background-color: #1e1e2e;")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignCenter)

        # 제목
        title = QLabel("데시벨 측정")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #f5c542; font-size: 18pt; font-weight: bold;")
        layout.addWidget(title)

        # VU 미터 + LCD 수평 배치
        meter_row = QHBoxLayout()
        meter_row.setAlignment(Qt.AlignCenter)

        self.vu_meter = VUMeterWidget()
        meter_row.addWidget(self.vu_meter)

        # LCD 숫자 (0~100 정규화 값)
        self.lcd = QLCDNumber(3)
        self.lcd.setSegmentStyle(QLCDNumber.Flat)
        self.lcd.setFixedSize(120, 80)
        self.lcd.setStyleSheet(
            "QLCDNumber { color: #22c55e; background-color: #0f172a; border: none; }"
        )
        self.lcd.display(0)

        lcd_col = QVBoxLayout()
        lcd_col.setAlignment(Qt.AlignCenter)
        lcd_col.addWidget(self.lcd)
        db_unit = QLabel("dB (0–100)")
        db_unit.setAlignment(Qt.AlignCenter)
        db_unit.setStyleSheet("color: #64748b; font-size: 10pt;")
        lcd_col.addWidget(db_unit)
        meter_row.addLayout(lcd_col)

        layout.addLayout(meter_row)

        # AudioThread 시작
        self.thread = AudioThread()
        self.thread.db_ready.connect(self.update_db)
        self.thread.start()

    def update_db(self, value: float):
        self.vu_meter.set_value(value)
        self.lcd.display(int(value))

        # LCD 색상 동적 변경
        if value < 60:
            color = "#22c55e"
        elif value < 80:
            color = "#eab308"
        else:
            color = "#ef4444"
        self.lcd.setStyleSheet(
            f"QLCDNumber {{ color: {color}; background-color: #0f172a; border: none; }}"
        )

    def closeEvent(self, event):
        self.thread.stop()
        super().closeEvent(event)


# ── 진입점 ──────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행하여 동작 확인**

```bash
python audio_decibel_poc.py
```

Expected: VU 미터 창이 열리고 마이크 소리에 따라 막대 및 LCD 수치 실시간 변화

- [ ] **Step 3: 커밋**

```bash
git add audio_decibel_poc.py
git commit -m "feat: add audio decibel PoC with VU meter widget"
```

---

## 최종 검증

- [ ] **4개 파일 각각 독립 실행 확인**

```bash
python squat_poc.py
python pushup_poc.py
python situp_poc.py
python audio_decibel_poc.py
```

- [ ] **최종 커밋**

```bash
git add .
git commit -m "chore: finalize PyQt5 motion + audio PoC"
```
