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
    InputStream 오픈 실패(권한 거부 등) 시 stream_error Signal을 발행한다.
    """

    level_updated = Signal(float, float)  # (표시 dB, 청크 경과 시간(초))
    stream_error = Signal()               # InputStream 오픈 실패 시

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

        try:
            with sd.InputStream(
                channels=1,
                samplerate=_SAMPLERATE,
                blocksize=_BLOCKSIZE,
                callback=_callback,
            ):
                while self._running:
                    self.msleep(50)
        except Exception:
            # InputStream 오픈 실패(권한 거부, 디바이스 없음 등) → 위젯에 알림
            self.stream_error.emit()

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
        self._title_label.setText("🎤  소리질러!")
        self._subtitle_label.setText(
            f"[{app_name}] 실행을 위해 {HOLD_SECONDS:.0f}초 유지!"
        )
        self._update_db_bar(0.0)
        self._update_hold_bar(0.0)
        self._update_countdown(self._time_limit)
        self._result_label.setText("")
        # 버튼 상태 리셋 (재도전 후 재시작 시 포기 버튼 복원)
        self._quit_btn.show()
        self._retry_btn.hide()
        self._back_btn.hide()

        self._audio_thread = AudioThread(self)
        self._audio_thread.level_updated.connect(self._on_level_updated)
        self._audio_thread.stream_error.connect(self._on_stream_error)
        self._audio_thread.start()
        self._countdown_timer.start()
        self._active = True

    def _reset_state(self):
        self._hold_timer = 0.0
        self._remaining = self._time_limit
        self._active = False

    # ─── UI 빌드 ─────────────────────────────────────────

    def _build_ui(self):
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
        self._target_label = QLabel(f"── 목표: {self._db_threshold} dB ──────────────────────────")
        self._target_label.setFont(QFont("Arial", 11))
        self._target_label.setStyleSheet("color: #FF6B6B;")
        card_layout.addWidget(self._target_label)

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

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        # 포기 버튼 (게임 진행 중)
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
        btn_layout.addWidget(self._quit_btn)

        # 재도전 버튼 (실패 후 표시)
        self._retry_btn = QPushButton("🔄 재도전")
        self._retry_btn.setFont(QFont("Arial", 14))
        self._retry_btn.setFixedHeight(44)
        self._retry_btn.setFixedWidth(160)
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: #45B7B8; }}
        """)
        self._retry_btn.clicked.connect(self._on_retry)
        self._retry_btn.hide()
        btn_layout.addWidget(self._retry_btn)

        # 돌아가기 버튼 (실패 후 표시)
        self._back_btn = QPushButton("↩ 돌아가기")
        self._back_btn.setFont(QFont("Arial", 14))
        self._back_btn.setFixedHeight(44)
        self._back_btn.setFixedWidth(160)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #4a5568;
                color: #ffffff;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: #5a6578; }}
        """)
        self._back_btn.clicked.connect(self._on_back)
        self._back_btn.hide()
        btn_layout.addWidget(self._back_btn)

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
        # 실패 오버레이: 재도전 / 돌아가기 버튼 표시
        self._result_label.setText("❌ 시간 초과! 다시 도전하세요.")
        self._result_label.setStyleSheet("color: #FF6B6B;")
        self._quit_btn.hide()
        self._retry_btn.show()
        self._back_btn.show()

    @Slot()
    def _on_retry(self):
        """재도전: 상태 리셋 후 게임 재시작"""
        self._retry_btn.hide()
        self._back_btn.hide()
        self._quit_btn.show()
        self.start_game(self.app_name, self.app_path)

    @Slot()
    def _on_back(self):
        """돌아가기: 포기와 동일 처리"""
        self._retry_btn.hide()
        self._back_btn.hide()
        self._quit_btn.show()
        self._on_quit()

    @Slot()
    def _on_stream_error(self):
        """InputStream 오픈 실패 시 즉시 game_quit (폴백)"""
        self._active = False
        self._stop_audio()
        self.game_quit.emit()

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
