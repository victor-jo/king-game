"""
팔굽혀펴기 카운터 PoC
- QThread + pyqtSignal 패턴으로 UI 스레드 차단 없이 영상 처리
- MediaPipe Pose로 어깨-팔꿈치-손목 각도 계산
- 각도 < 90° → DOWN, 각도 > 160° → UP (카운트 증가)
"""

import os
import sys
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox
)

# mediapipe Tasks API 랜드마크 인덱스
_RIGHT_SHOULDER, _RIGHT_ELBOW, _RIGHT_WRIST = 12, 14, 16


def get_available_cameras(max_test: int = 5) -> list[tuple[int, str]]:
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
        av_devices = list(AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo))

        # 유효한 OpenCV 인덱스 수집
        valid_opencv = []
        for i in range(max_test):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                valid_opencv.append(i)
                cap.release()

        # OpenCV는 외부(Continuity) 카메라를 먼저, 내장 카메라를 나중에 열거.
        # AVFoundation modelID로 iPhone(외부)과 내장 카메라를 구분해 순서 정렬.
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


def get_default_camera_index(cameras: list[tuple[int, str]]) -> int:
    macbook_keywords = ("MacBook", "FaceTime", "Built-in", "내장", "Apple Camera")
    for idx, name in cameras:
        if any(kw in name for kw in macbook_keywords):
            return idx
    return cameras[0][0] if cameras else 0

_POSE_CONNECTIONS = [
    (11,12),(11,13),(13,15),(12,14),(14,16),
    (11,23),(12,24),(23,24),
    (23,25),(25,27),(24,26),(26,28),
]

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "pose_landmarker_lite.task")


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

    def __init__(self, camera_index: int = 0):
        super().__init__()
        self._running = True
        self.camera_index = camera_index
        self.count = 0
        self.stage = "UP"

    def run(self):
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=mp_vision.RunningMode.VIDEO
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

                    # 팔굽혀펴기: 오른쪽 어깨-팔꿈치-손목
                    shoulder = [lm[_RIGHT_SHOULDER].x, lm[_RIGHT_SHOULDER].y]
                    elbow    = [lm[_RIGHT_ELBOW].x,    lm[_RIGHT_ELBOW].y]
                    wrist    = [lm[_RIGHT_WRIST].x,    lm[_RIGHT_WRIST].y]

                    angle = calculate_angle(shoulder, elbow, wrist)
                    self.angle_updated.emit(round(angle, 1))

                    # State transition guard: 상태 변경 시에만 emit
                    if angle < self.DOWN_THRESHOLD and self.stage != "DOWN":
                        self.stage = "DOWN"
                        self.state_changed.emit("DOWN")

                    if angle > self.UP_THRESHOLD and self.stage == "DOWN":
                        self.stage = "UP"
                        self.count += 1
                        self.state_changed.emit("UP")
                        self.rep_updated.emit(self.count)

                    # 랜드마크 오버레이 (OpenCV로 직접 그리기)
                    pts = [(int(p.x * w), int(p.y * h)) for p in lm]
                    for a_idx, b_idx in _POSE_CONNECTIONS:
                        cv2.line(frame, pts[a_idx], pts[b_idx], (0, 255, 0), 2)
                    for pt in pts:
                        cv2.circle(frame, pt, 4, (0, 0, 255), -1)

                h, w, ch = frame.shape
                qt_img = QImage(frame.data, w, h, ch * w, QImage.Format_BGR888)
                self.frame_ready.emit(qt_img.copy())

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

        hud_widget = QWidget()
        hud_widget.setFixedHeight(50)
        hud_widget.setStyleSheet("background-color: #1e1e2e;")
        hud_layout = QHBoxLayout(hud_widget)
        hud_layout.setContentsMargins(12, 0, 12, 0)

        self.hud_label = QLabel("횟수: 0   상태: UP   각도: 0.0°")
        self.hud_label.setAlignment(Qt.AlignCenter)
        self.hud_label.setStyleSheet("color: #f5c542; font-size: 15pt; font-weight: bold;")
        hud_layout.addWidget(self.hud_label, stretch=1)

        self.cam_combo = QComboBox()
        cameras = get_available_cameras()
        for idx, name in cameras:
            self.cam_combo.addItem(name, idx)
        default_idx = get_default_camera_index(cameras)
        self.cam_combo.setCurrentIndex(
            next((i for i, (idx, _) in enumerate(cameras) if idx == default_idx), 0)
        )
        self.cam_combo.setFixedWidth(200)
        self.cam_combo.setStyleSheet(
            "QComboBox { background: #16213e; color: #e2e8f0; "
            "border: 1px solid #475569; padding: 2px 8px; border-radius: 4px; }"
            "QComboBox::drop-down { border: none; }"
        )
        self.cam_combo.currentIndexChanged.connect(self._on_camera_changed)
        hud_layout.addWidget(self.cam_combo)
        layout.addWidget(hud_widget)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_label)

        self._start_thread(self.cam_combo.currentData())

    def _start_thread(self, camera_index: int):
        self.thread = VideoThread(camera_index)
        self.thread.frame_ready.connect(self.update_frame)
        self.thread.rep_updated.connect(self.update_rep)
        self.thread.state_changed.connect(self.update_state)
        self.thread.angle_updated.connect(self.update_angle)
        self.thread.start()

    def _on_camera_changed(self, combo_index: int):
        camera_index = self.cam_combo.itemData(combo_index)
        self.thread.stop()
        self._start_thread(camera_index)

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
