"""에임 게임 위젯 모듈 — 순차 클릭 에임 트레이너"""

import random
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QBrush, QPen, QRadialGradient


# 색상 팔레트
COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
]


class Target:
    """클릭 타겟 하나를 나타내는 클래스"""

    def __init__(self, number: int, x: float, y: float, radius: float = 30):
        self.number = number
        self.x = x
        self.y = y
        self.radius = radius
        self.clicked = False
        self.color = COLORS[(number - 1) % len(COLORS)]

    def contains(self, px: float, py: float) -> bool:
        """주어진 좌표가 타겟 안에 있는지 확인"""
        dx = px - self.x
        dy = py - self.y
        return (dx * dx + dy * dy) <= (self.radius * self.radius)


class AimGameWidget(QWidget):
    """에임 게임 캔버스 위젯

    번호가 적힌 원형 타겟을 랜덤 위치에 배치하고,
    1번부터 순서대로 클릭해야 하는 게임.
    """

    game_success = Signal()  # 게임 성공 시그널
    game_failed = Signal()   # 게임 실패 시그널
    game_quit = Signal()     # 게임 포기 (설정으로 돌아가기) 시그널

    def __init__(self, target_count: int = 5, time_limit: int = 10, parent=None):
        super().__init__(parent)
        self.target_count = target_count
        self.time_limit = time_limit
        self.app_name = ""
        self.app_path = ""

        # 게임 상태
        self.targets: list[Target] = []
        self.current_target = 1  # 다음으로 클릭할 번호
        self.remaining_time = 0.0
        self.is_running = False
        self.is_failed = False
        self.is_success = False

        # 타이머
        self.game_timer = QTimer(self)
        self.game_timer.setInterval(50)  # 50ms 간격 업데이트
        self.game_timer.timeout.connect(self._tick)

        self.setMinimumSize(600, 500)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 실패 시 버튼 오버레이
        self._fail_overlay = QWidget(self)
        self._fail_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self._fail_overlay.hide()

        fail_layout = QVBoxLayout(self._fail_overlay)
        fail_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.setSpacing(16)

        fail_title = QLabel("💥 실패!")
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
            QPushButton {
                background-color: #4ECDC4;
                color: #ffffff;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #45B7B8;
            }
        """)
        retry_btn.clicked.connect(self._retry_game)
        btn_row.addWidget(retry_btn)

        quit_btn = QPushButton("🏠 돌아가기")
        quit_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        quit_btn.setFixedSize(180, 55)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d3748;
                color: #e2e8f0;
                border: 2px solid #4a5568;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #3d4f6f;
            }
        """)
        quit_btn.clicked.connect(self._quit_game)
        btn_row.addWidget(quit_btn)

        fail_layout.addLayout(btn_row)

    def start_game(self, app_name: str, app_path: str):
        """게임 시작"""
        self.app_name = app_name
        self.app_path = app_path
        self.current_target = 1
        self.remaining_time = self.time_limit
        self.is_running = True
        self.is_failed = False
        self.is_success = False
        self._fail_overlay.hide()
        self._generate_targets()
        self.game_timer.start()
        self.update()

    def update_settings(self, target_count: int, time_limit: int):
        """게임 설정 업데이트"""
        self.target_count = target_count
        self.time_limit = time_limit

    def _generate_targets(self):
        """랜덤 위치에 타겟 배치 (겹침 방지)"""
        self.targets = []
        margin = 50
        radius = 30

        w = max(self.width() - margin * 2, 200)
        h = max(self.height() - margin * 2 - 80, 200)  # 상단 UI 영역 제외

        for i in range(1, self.target_count + 1):
            attempts = 0
            while attempts < 100:
                x = random.randint(margin + radius, margin + w - radius)
                y = random.randint(margin + radius + 80, margin + h + 80 - radius)

                # 기존 타겟과 겹치지 않는지 확인
                overlap = False
                for t in self.targets:
                    dx = x - t.x
                    dy = y - t.y
                    if (dx * dx + dy * dy) < (radius * 3) ** 2:
                        overlap = True
                        break

                if not overlap:
                    self.targets.append(Target(i, x, y, radius))
                    break
                attempts += 1
            else:
                # 배치 실패 시 아무 곳에나
                x = random.randint(margin + radius, margin + w - radius)
                y = random.randint(margin + radius + 80, margin + h + 80 - radius)
                self.targets.append(Target(i, x, y, radius))

    def _tick(self):
        """타이머 틱"""
        self.remaining_time -= 0.05
        if self.remaining_time <= 0:
            self.remaining_time = 0
            self._on_fail()
        self.update()

    def _on_fail(self):
        """게임 실패"""
        self.game_timer.stop()
        self.is_running = False
        self.is_failed = True
        self.update()
        # 실패 오버레이 표시
        self._fail_overlay.setGeometry(0, 0, self.width(), self.height())
        self._fail_overlay.show()
        self._fail_overlay.raise_()
        self.game_failed.emit()

    def _retry_game(self):
        """재도전"""
        self._fail_overlay.hide()
        self.start_game(self.app_name, self.app_path)

    def _quit_game(self):
        """설정 화면으로 돌아가기"""
        self._fail_overlay.hide()
        self.game_quit.emit()

    def resizeEvent(self, event):
        """오버레이 크기 동기화"""
        super().resizeEvent(event)
        if self._fail_overlay.isVisible():
            self._fail_overlay.setGeometry(0, 0, self.width(), self.height())

    def _on_success(self):
        """게임 성공"""
        self.game_timer.stop()
        self.is_running = False
        self.is_success = True
        self.update()
        QTimer.singleShot(800, lambda: self.game_success.emit())

    def mousePressEvent(self, event):
        """마우스 클릭 이벤트"""
        if not self.is_running:
            return

        mx = event.position().x()
        my = event.position().y()

        for target in self.targets:
            if target.clicked:
                continue
            if target.contains(mx, my):
                if target.number == self.current_target:
                    # 정답!
                    target.clicked = True
                    self.current_target += 1
                    if self.current_target > self.target_count:
                        self._on_success()
                else:
                    # 오답! 실패
                    self._on_fail()
                self.update()
                return

    def paintEvent(self, event):
        """게임 화면 그리기"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 배경
        painter.fillRect(0, 0, w, h, QColor("#1a1a2e"))

        # 상단 정보 바
        self._draw_header(painter, w)

        # 타겟 그리기
        for target in self.targets:
            self._draw_target(painter, target)

        # 성공/실패 오버레이
        if self.is_success:
            self._draw_overlay(painter, w, h, "🎉 성공!", "#4ECDC4")
        elif self.is_failed:
            self._draw_overlay(painter, w, h, "💥 실패!", "#FF6B6B")

        painter.end()

    def _draw_header(self, painter: QPainter, width: int):
        """상단 정보 바"""
        # 배경
        painter.fillRect(0, 0, width, 70, QColor("#16213e"))

        # 앱 이름
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        painter.drawText(20, 28, f"🎯 {self.app_name}을(를) 실행하려면 클리어!")

        # 남은 시간
        time_color = "#4ECDC4" if self.remaining_time > 3 else "#FF6B6B"
        painter.setPen(QColor(time_color))
        painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        painter.drawText(20, 55, f"⏱️ {self.remaining_time:.1f}초")

        # 진행도
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Arial", 14))
        done = min(self.current_target - 1, self.target_count)
        painter.drawText(width - 150, 55, f"진행: {done}/{self.target_count}")

        # 타임바
        bar_y = 65
        bar_w = width - 40
        ratio = max(self.remaining_time / self.time_limit, 0)
        painter.fillRect(20, bar_y, bar_w, 4, QColor("#2d3748"))
        bar_color = QColor(time_color)
        painter.fillRect(20, bar_y, int(bar_w * ratio), 4, bar_color)

    def _draw_target(self, painter: QPainter, target: Target):
        """타겟 하나 그리기"""
        if target.clicked:
            # 클릭된 타겟: 반투명 체크
            painter.setPen(QPen(QColor("#4ECDC4"), 2))
            painter.setBrush(QBrush(QColor(78, 205, 196, 60)))
            painter.drawEllipse(
                QPointF(target.x, target.y), target.radius, target.radius
            )
            painter.setPen(QColor("#4ECDC4"))
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.drawText(
                QRectF(
                    target.x - target.radius,
                    target.y - target.radius,
                    target.radius * 2,
                    target.radius * 2,
                ),
                Qt.AlignmentFlag.AlignCenter,
                "✓",
            )
            return

        # 다음 클릭할 타겟 강조
        is_next = target.number == self.current_target

        # 그림자
        gradient = QRadialGradient(target.x, target.y, target.radius * 1.5)
        base_color = QColor(target.color)
        if is_next:
            # 글로우 효과
            glow_color = QColor(base_color)
            glow_color.setAlpha(80)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(
                QPointF(target.x, target.y), target.radius * 1.6, target.radius * 1.6
            )

        # 원형 타겟
        gradient.setColorAt(0, base_color.lighter(130))
        gradient.setColorAt(1, base_color)
        painter.setBrush(QBrush(gradient))
        pen_color = QColor("#ffffff") if is_next else QColor(base_color.darker(120))
        painter.setPen(QPen(pen_color, 3 if is_next else 2))
        painter.drawEllipse(
            QPointF(target.x, target.y), target.radius, target.radius
        )

        # 번호 텍스트
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", 16 if is_next else 14, QFont.Weight.Bold))
        painter.drawText(
            QRectF(
                target.x - target.radius,
                target.y - target.radius,
                target.radius * 2,
                target.radius * 2,
            ),
            Qt.AlignmentFlag.AlignCenter,
            str(target.number),
        )

    def _draw_overlay(self, painter: QPainter, w: int, h: int, text: str, color: str):
        """성공 오버레이 (실패는 위젯 오버레이 사용)"""
        # 반투명 배경
        overlay = QColor(0, 0, 0, 180)
        painter.fillRect(0, 0, w, h, overlay)

        # 텍스트
        painter.setPen(QColor(color))
        painter.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        painter.drawText(
            QRectF(0, 0, w, h - 40),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

        # 안내 텍스트
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Arial", 16))
        painter.drawText(
            QRectF(0, 50, w, h),
            Qt.AlignmentFlag.AlignCenter,
            "프로그램을 실행합니다...",
        )
