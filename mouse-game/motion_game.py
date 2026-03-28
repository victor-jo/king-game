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
        # 무릎 각도: 75° 미만까지 내려가야 DOWN, 168° 이상으로 펴야 UP
        "down_threshold": 75,
        "up_threshold": 168,
        "inverted": False,               # DOWN=꺾임(작은 각도), UP=펼침(큰 각도)
    },
    {
        "name": "푸쉬업", "emoji": "💪",
        "joints": (12, 14, 16),          # RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST
        # 팔꿈치 각도: 75° 미만까지 구부려야 DOWN, 168° 이상으로 펴야 UP
        "down_threshold": 75,
        "up_threshold": 168,
        "inverted": False,
    },
    {
        "name": "싯업", "emoji": "🧘",
        "joints": (12, 24, 26),          # RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE
        # 상체-골반-무릎 각도: 150° 이상으로 눕혀야 DOWN, 45° 미만으로 일어나야 UP
        "down_threshold": 150,
        "up_threshold": 45,
        "inverted": True,                # DOWN=누움(큰 각도), UP=일어남(작은 각도)
    },
]

_MODEL_PATH = os.path.join(
    os.environ.get("RESOURCEPATH", os.path.dirname(os.path.abspath(__file__))),
    "pose_landmarker_lite.task",
)

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


def _probe_camera_silent(index: int):
    """카메라 인덱스 유효성을 stderr 출력 없이 확인. 열리면 True."""
    import cv2
    import os
    import contextlib

    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    os.dup2(devnull_fd, 2)
    try:
        cap = cv2.VideoCapture(index)
        ok = cap.isOpened()
        if ok:
            cap.release()
        return ok
    finally:
        os.dup2(old_stderr, 2)
        os.close(devnull_fd)
        os.close(old_stderr)


def _get_available_cameras(max_test: int = 5):
    """사용 가능한 카메라 목록 반환. (index, name) 튜플 리스트."""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
        av_devices = list(AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo))
        valid_opencv = [i for i in range(max_test) if _probe_camera_silent(i)]
        external = [d for d in av_devices if "iPhone" in (d.modelID() or "")]
        internal = [d for d in av_devices if "iPhone" not in (d.modelID() or "")]
        ordered = external + internal
        cameras = []
        for i, opencv_idx in enumerate(valid_opencv):
            name = ordered[i].localizedName() if i < len(ordered) else f"카메라 {opencv_idx}"
            cameras.append((opencv_idx, name))
        return cameras
    except Exception:
        return [(i, f"카메라 {i}") for i in range(max_test) if _probe_camera_silent(i)]


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

        # 카메라 콤보 업데이트 (이미 조회한 cameras 재사용)
        self._cam_combo.blockSignals(True)
        self._cam_combo.clear()
        for idx, name in cameras:
            self._cam_combo.addItem(name, idx)
        for i in range(self._cam_combo.count()):
            if self._cam_combo.itemData(i) == camera_index:
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
        self._hud_label = QLabel("횟수: 0 / 0   상태: UP   각도: 0°   ⏱ 0초")
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
