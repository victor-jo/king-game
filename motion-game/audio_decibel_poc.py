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
from PyQt5.QtGui import QPainter, QColor
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
            # int16 → -1.0 ~ 1.0 정규화 (dBFS 기준을 맞추기 위해 필수)
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

            # RMS 계산 후 dBFS 변환 (1e-9로 log(0) 방지)
            rms = math.sqrt(np.mean(samples ** 2))
            db  = 20 * math.log10(rms + 1e-9)

            # 0~100 정규화 후 시그널 emit
            db_normalized = float(np.clip(
                (db - self.DB_MIN) / self.DB_RANGE * 100, 0, 100
            ))
            self.db_ready.emit(db_normalized)

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
