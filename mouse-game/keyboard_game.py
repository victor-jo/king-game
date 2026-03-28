"""타자 게임 위젯 모듈 — 명언 타이핑으로 앱 잠금 해제"""

import random
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton,
)


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

TOTAL_ROUNDS = 3
KPM_GOAL = 500
ACCURACY_GOAL = 90

# 타이핑 필드 글자 색상
_COL_UNTYPED = "#3d4f6f"   # 아직 안 친 글자: 연한 회색
_COL_CORRECT = "#e2e8f0"   # 맞게 친 글자: 흰색
_COL_WRONG   = "#FF6B6B"   # 틀리게 친 글자: 빨간색


def _html_escape(ch: str) -> str:
    return (ch.replace("&", "&amp;")
              .replace("<", "&lt;")
              .replace(">", "&gt;")
              .replace(" ", "&nbsp;"))


# ── 컬러 타이핑 입력 위젯 ────────────────────────────────────────────
class TypingField(QWidget):
    """타겟 문장을 ghost text로 보여주며 실시간 색상 피드백을 제공하는 입력 위젯.

    - 아직 안 친 글자: 연한 회색(_COL_UNTYPED)
    - 맞게 친 글자: 흰색(_COL_CORRECT)
    - 틀리게 친 글자: 빨간색(_COL_WRONG)

    QLabel(HTML 컬러 디스플레이)을 앞에, QLineEdit(투명 텍스트)를 뒤에 겹쳐서
    한국어 IME 입력을 그대로 지원합니다.
    """

    textChanged = Signal(str)
    returnPressed = Signal()
    keyPressed = Signal(int)   # 타수/백스페이스 카운팅용 (key code 전달)

    _PAD_H = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = ""

        # ── 컬러 디스플레이 레이블 ──────────────────────────
        self._lbl = QLabel(self)
        self._lbl.setTextFormat(Qt.TextFormat.RichText)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._lbl.setStyleSheet("background: transparent; border: none;")

        # ── 실제 입력 필드 (텍스트를 배경색과 동일하게 숨김) ──
        self._edit = QLineEdit(self)
        self._edit.setStyleSheet(
            f"background: transparent; border: none; color: {CARD_BG}; padding: 0;"
        )
        # ghost text 레이블과 x/y 위치 정확히 일치시키기 위해 텍스트 마진 설정
        self._edit.setTextMargins(self._PAD_H, 0, self._PAD_H, 0)
        self._edit.textChanged.connect(self._on_edit_changed)
        self._edit.returnPressed.connect(self.returnPressed)
        self._edit.installEventFilter(self)

        font = QFont("Arial", 15)
        self._lbl.setFont(font)
        self._edit.setFont(font)

        self.setMinimumHeight(52)
        self._set_border(focused=False)

    # ── 외부 API ────────────────────────────────────────────

    def set_target(self, text: str):
        self._target = text
        self._edit.clear()
        self._refresh("")

    def clear(self):
        self._edit.clear()

    def text(self) -> str:
        return self._edit.text()

    def setFocus(self):
        self._edit.setFocus()

    # ── 레이아웃 ─────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._edit.setGeometry(0, 0, self.width(), self.height())
        self._sync_label_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_label_geometry()

    def _sync_label_geometry(self):
        """QLineEdit의 실제 텍스트 y 위치를 읽어 레이블을 픽셀 단위로 정렬."""
        cr = self._edit.cursorRect()   # QLineEdit이 텍스트를 그리는 정확한 y, height
        self._lbl.setGeometry(
            self._PAD_H,
            cr.y(),
            self.width() - 2 * self._PAD_H,
            cr.height(),
        )

    # ── 포커스 → 테두리 색 ────────────────────────────────────

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._set_border(focused=True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._set_border(focused=False)

    def _set_border(self, focused: bool):
        color = ACCENT if focused else BORDER
        self.setStyleSheet(f"""
            TypingField {{
                background-color: {CARD_BG};
                border: 2px solid {color};
                border-radius: 8px;
            }}
        """)

    # ── 내부 로직 ─────────────────────────────────────────────

    def _on_edit_changed(self, text: str):
        self._refresh(text)
        self.textChanged.emit(text)

    def _refresh(self, typed: str):
        parts = []
        for i, ch in enumerate(self._target):
            esc = _html_escape(ch)
            if i < len(typed):
                color = _COL_CORRECT if typed[i] == ch else _COL_WRONG
            else:
                color = _COL_UNTYPED
            parts.append(f'<span style="color:{color};">{esc}</span>')
        self._lbl.setText("".join(parts))

    # ── 이벤트 필터 (키 이벤트 → 상위로 전달) ─────────────────

    def eventFilter(self, obj, event):
        if obj is self._edit and isinstance(event, QKeyEvent):
            if event.type() == QKeyEvent.Type.KeyPress:
                key = event.key()
                if key not in (
                    Qt.Key.Key_Return, Qt.Key.Key_Enter,
                    Qt.Key.Key_Shift, Qt.Key.Key_Control,
                    Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                    Qt.Key.Key_CapsLock, Qt.Key.Key_Tab,
                    Qt.Key.Key_Left, Qt.Key.Key_Right,
                    Qt.Key.Key_Up, Qt.Key.Key_Down,
                    Qt.Key.Key_Home, Qt.Key.Key_End,
                ):
                    self._set_border(focused=True)
                    self.keyPressed.emit(key)
        return super().eventFilter(obj, event)


# ── 메인 게임 위젯 ────────────────────────────────────────────────────
class KeyboardGameWidget(QWidget):
    """타자 게임 위젯

    랜덤 명언 3문장을 순서대로 입력.
    3문장의 평균 타수(타/분) ≥ KPM_GOAL, 각 문장 정확도 ≥ ACCURACY_GOAL 시 game_success.
    조건 미달 또는 시간 초과 시 game_failed.
    """

    game_success = Signal()
    game_failed = Signal()
    game_quit = Signal()

    def __init__(self, accuracy_threshold: int = ACCURACY_GOAL, time_limit: int = 30, parent=None):
        super().__init__(parent)
        self.accuracy_threshold = accuracy_threshold
        self.time_limit = time_limit
        self.app_name = ""
        self.app_path = ""

        self._finished = False
        self._current_round = 0
        self._round_stats: list[dict] = []

        self._started = False
        self._start_time = 0.0
        self._backspace_count = 0

        self._quotes: list[tuple[str, str]] = []
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
        self._prepare_quotes()
        self._reset_game()
        self._fail_overlay.hide()
        self._start_round()
        self._ui_timer.start()
        self._typing_field.setFocus()

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

        # 라운드 진행 표시
        self._round_label = QLabel()
        self._round_label.setFont(QFont("Arial", 12))
        self._round_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(self._round_label)

        # 통계 바 (시간 / 타수 / 정확도)
        stats_row = QHBoxLayout()
        self._time_label = QLabel()
        self._time_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self._time_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        self._kpm_label = QLabel()
        self._kpm_label.setFont(QFont("Arial", 13))
        self._kpm_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._acc_label = QLabel()
        self._acc_label.setFont(QFont("Arial", 13))
        self._acc_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        stats_row.addWidget(self._time_label)
        stats_row.addStretch()
        stats_row.addWidget(self._kpm_label)
        stats_row.addSpacing(16)
        stats_row.addWidget(self._acc_label)
        layout.addLayout(stats_row)

        # 타겟 문장 카드 (읽기 전용 참조)
        self._target_card = QLabel()
        self._target_card.setWordWrap(True)
        self._target_card.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self._target_card.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background-color: {CARD_BG};"
            f"border-radius: 10px; padding: 20px;"
        )
        self._target_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._target_card)

        # 타이핑 입력 필드 (ghost text + 실시간 컬러 피드백)
        input_hint = QLabel("다음 문장을 그대로 따라 입력하세요:")
        input_hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(input_hint)

        self._typing_field = TypingField(self)
        self._typing_field.textChanged.connect(self._on_text_changed)
        self._typing_field.returnPressed.connect(self._on_enter)
        self._typing_field.keyPressed.connect(self._on_key_pressed)
        layout.addWidget(self._typing_field)

        # 안내 텍스트
        hint = QLabel(
            f"Enter로 제출 — 3문장 평균 {KPM_GOAL}타/분 이상 + 정확도 {ACCURACY_GOAL}% 이상이면 클리어!"
        )
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

    def _prepare_quotes(self):
        pool = QUOTES[:]
        random.shuffle(pool)
        self._quotes = pool[:TOTAL_ROUNDS]

    def _reset_game(self):
        self._finished = False
        self._current_round = 0
        self._round_stats = []

    def _start_round(self):
        quote, author = self._quotes[self._current_round]
        self._target = quote
        self._author = author

        self._started = False
        self._start_time = 0.0
        self._backspace_count = 0

        self._typing_field.set_target(quote)
        self._target_card.setText(f"{quote}\n— {author}")

        round_num = self._current_round + 1
        self._header_label.setText(
            f"⌨️ {self.app_name}을(를) 실행하려면 타자를 클리어하세요!"
        )
        self._round_label.setText(
            f"문장 {round_num} / {TOTAL_ROUNDS}  |  "
            f"목표: {KPM_GOAL}타/분 이상, 정확도 {self.accuracy_threshold}% 이상"
        )
        self._update_stats_labels("", 0.0)

    def _update_stats_labels(self, current_text: str, elapsed: float):
        remaining = max(self.time_limit - elapsed, 0.0)
        color = ACCENT if remaining > 5 else DANGER
        self._time_label.setText(f"⏱ {remaining:.1f}초")
        self._time_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")

        kpm = self._calc_kpm(elapsed, current_text)
        kpm_color = ACCENT if kpm >= KPM_GOAL else DANGER
        self._kpm_label.setText(f"타수: {kpm:.0f}타/분 (목표 {KPM_GOAL})")
        self._kpm_label.setStyleSheet(f"color: {kpm_color}; font-size: 13px;")

        acc = self._calc_accuracy(current_text)
        acc_color = ACCENT if acc >= self.accuracy_threshold else DANGER
        self._acc_label.setText(f"정확도: {acc:.0f}% (목표 {self.accuracy_threshold}%)")
        self._acc_label.setStyleSheet(f"color: {acc_color}; font-size: 13px;")

    # ── 계산 ────────────────────────────────────────────

    def _calc_accuracy(self, text: str) -> float:
        if not text:
            return 100.0
        correct = sum(
            1 for i, c in enumerate(text)
            if i < len(self._target) and c == self._target[i]
        )
        return (correct / len(text)) * 100.0

    @staticmethod
    def _count_jamo(text: str) -> int:
        """두벌식 기준 타수 계산 (완성형 한글: 종성 없으면 2타, 종성 있으면 3타 / 나머지 1타)"""
        count = 0
        for ch in text:
            code = ord(ch)
            if 0xAC00 <= code <= 0xD7A3:
                jongseong = (code - 0xAC00) % 28
                count += 3 if jongseong > 0 else 2
            else:
                count += 1
        return count

    def _calc_kpm(self, elapsed: float, current_text: str = "") -> float:
        if elapsed < 0.1:
            return 0.0
        total = self._count_jamo(current_text) + self._backspace_count
        return (total / elapsed) * 60.0

    # ── 이벤트 핸들러 ────────────────────────────────────

    def _on_key_pressed(self, key: int):
        if not self._started:
            self._started = True
            self._start_time = time.time()
        if key == Qt.Key.Key_Backspace:
            self._backspace_count += 1

    def _on_text_changed(self, text: str):
        elapsed = time.time() - self._start_time if self._started else 0.0
        self._update_stats_labels(text, elapsed)

    def _tick(self):
        if not self._started or self._finished:
            return
        elapsed = time.time() - self._start_time
        self._update_stats_labels(self._typing_field.text(), elapsed)
        if elapsed >= self.time_limit:
            self._on_fail(f"문장 {self._current_round + 1} 시간 초과!")

    def _on_enter(self):
        if self._finished:
            return
        text = self._typing_field.text()
        elapsed = time.time() - self._start_time if self._started else 0.0
        acc = self._calc_accuracy(text)
        kpm = self._calc_kpm(elapsed, text)

        if acc < self.accuracy_threshold:
            self._on_fail(
                f"문장 {self._current_round + 1} 정확도 {acc:.0f}% — "
                f"목표 {self.accuracy_threshold}% 미달"
            )
            return

        self._round_stats.append({"kpm": kpm, "accuracy": acc})
        self._current_round += 1

        if self._current_round < TOTAL_ROUNDS:
            self._start_round()
            self._typing_field.setFocus()
        else:
            avg_kpm = sum(s["kpm"] for s in self._round_stats) / TOTAL_ROUNDS
            if avg_kpm >= KPM_GOAL:
                self._on_success()
            else:
                self._on_fail(
                    f"평균 타수 {avg_kpm:.0f}타/분 — 목표 {KPM_GOAL}타/분 미달"
                )

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
        self._prepare_quotes()
        self._reset_game()
        self._start_round()
        self._ui_timer.start()
        self._typing_field.setFocus()

    def _quit_game(self):
        self._finished = True
        self._ui_timer.stop()
        self._fail_overlay.hide()
        self.game_quit.emit()
