"""메인 설정 화면 모듈"""

import random
import subprocess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QScrollArea,
    QFrame, QStackedWidget, QSystemTrayIcon, QMenu,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QAction

from config import AppConfig, DEFAULT_WHITELIST
from process_monitor import ProcessMonitor
from aim_game import AimGameWidget
from bug_game import BugGameWidget
from keyboard_game import KeyboardGameWidget
from motion_game import MotionGameWidget


# ─── 스타일 상수 ────────────────────────────────────

DARK_BG = "#0f0f23"
CARD_BG = "#1a1a2e"
ACCENT = "#4ECDC4"
ACCENT_HOVER = "#45B7B8"
DANGER = "#FF6B6B"
TEXT_PRIMARY = "#e2e8f0"
TEXT_SECONDARY = "#94a3b8"
BORDER = "#2d3748"

GLOBAL_STYLE = f"""
    QMainWindow {{
        background-color: {DARK_BG};
    }}
    QLabel {{
        color: {TEXT_PRIMARY};
    }}
    QComboBox {{
        background-color: {CARD_BG};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 13px;
        min-width: 80px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {CARD_BG};
        color: {TEXT_PRIMARY};
        selection-background-color: {ACCENT};
        border: 1px solid {BORDER};
    }}
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        background-color: {DARK_BG};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BORDER};
        border-radius: 4px;
        min-height: 30px;
    }}
"""


class ToggleButton(QPushButton):
    """커스텀 ON/OFF 토글 버튼"""

    def __init__(self, is_on=False, parent=None):
        super().__init__(parent)
        self._is_on = is_on
        self.setFixedSize(60, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._toggle)
        self._update_style()

    @property
    def is_on(self):
        return self._is_on

    @is_on.setter
    def is_on(self, value):
        self._is_on = value
        self._update_style()

    def _toggle(self):
        self._is_on = not self._is_on
        self._update_style()

    def _update_style(self):
        if self._is_on:
            self.setText("제외")   # 화이트리스트
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ACCENT};
                    color: #ffffff;
                    border: none;
                    border-radius: 15px;
                    font-weight: bold;
                    font-size: 12px;
                }}
            """)
        else:
            self.setText("감시")   # 감시 대상
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BORDER};
                    color: {TEXT_SECONDARY};
                    border: none;
                    border-radius: 15px;
                    font-weight: bold;
                    font-size: 12px;
                }}
            """)


class AppRow(QFrame):
    """프로그램 한 줄 행 — 토글 ON = 화이트리스트(감시 제외)"""

    def __init__(self, app_data: dict, whitelisted: bool = False, parent=None):
        super().__init__(parent)
        self.app_data = app_data

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border-radius: 8px;
                padding: 4px;
            }}
            QFrame:hover {{
                background-color: #1e2a4a;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)

        icons = {
            "KakaoTalk": "🟡", "Discord": "🟣", "Slack": "🟢",
            "Telegram": "🔵", "Steam": "⚫", "Google Chrome": "🔴",
            "Mattermost": "🔵",
        }
        icon = icons.get(app_data["name"], "⚪")
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Arial", 18))
        icon_label.setFixedWidth(30)
        layout.addWidget(icon_label)

        name_label = QLabel(app_data["name"])
        name_label.setFont(QFont("Arial", 14))
        name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(name_label, 1)

        # 토글 버튼 — ON(초록)=감시 제외, OFF(회색)=감시 대상
        self.toggle = ToggleButton(whitelisted)
        layout.addWidget(self.toggle)


class MainWindow(QMainWindow):
    """메인 윈도우 — 설정 화면 + 게임 화면을 스택으로 관리"""

    def __init__(self):
        super().__init__()
        self.config = AppConfig.load()

        self.setWindowTitle("🎯 AimGuard")
        self.setMinimumSize(650, 550)
        self.setStyleSheet(GLOBAL_STYLE)

        # 프로세스 모니터
        self.monitor = self._create_monitor()

        self._monitoring = False
        # 앱 목록 초기 스캔 (settings_page 빌드 전에 필요)
        from config import scan_installed_apps as _scan
        self._all_apps: list[dict] = _scan()
        self._pending_game_type = ""
        self._pending_app_name = ""
        self._pending_app_path = ""

        # 스택 위젯: 0=설정, 1=게임
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # 설정 화면
        self.settings_page = self._build_settings_page()
        self.stack.addWidget(self.settings_page)

        # 에임 게임 위젯 (stack index 1)
        self.aim_widget = AimGameWidget(
            self.config.target_count, self.config.time_limit
        )
        self.aim_widget.game_success.connect(self._on_game_success)
        self.aim_widget.game_failed.connect(self._on_game_failed)
        self.aim_widget.game_quit.connect(self._on_game_quit)
        self.stack.addWidget(self.aim_widget)

        # 벌레 게임 위젯 (stack index 2)
        self.bug_widget = BugGameWidget(
            self.config.time_limit_bug, self.config.goal_score
        )
        self.bug_widget.game_success.connect(self._on_game_success)
        self.bug_widget.game_failed.connect(self._on_game_failed)
        self.bug_widget.game_quit.connect(self._on_game_quit)
        self.stack.addWidget(self.bug_widget)

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

        # 시스템 트레이
        self._setup_tray()

        # 자동 모니터링 시작 (앱 목록 재스캔 + 모니터 시작)
        self._auto_start_monitoring()

    def _create_monitor(self) -> ProcessMonitor:
        """새 ProcessMonitor 인스턴스 생성 및 시그널 연결"""
        monitor = ProcessMonitor(self)
        monitor.process_detected.connect(self._on_process_detected)
        return monitor

    def _auto_start_monitoring(self):
        """시작 시 자동으로 모니터링 시작 (매번 새 인스턴스로 QThread 재시작 문제 방지)"""
        from config import scan_installed_apps
        self._all_apps = scan_installed_apps()
        self._build_app_rows()  # UI 갱신
        monitored = self.config.get_monitored_apps(self._all_apps)
        self.monitor = self._create_monitor()
        self.monitor.set_locked_apps(monitored)
        self.monitor.start()
        self._monitoring = True
        self.tray.show()
        self.tray.showMessage(
            "AimGuard",
            f"감시 시작! {len(monitored)}개 앱 감시 중 🎯",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ─── 설정 화면 빌드 ─────────────────────────────

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 제목
        title = QLabel("🎯 AimGuard")
        title.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT};")

        # 감시 상태 표시 라벨
        self.status_label = QLabel("🟢 감시 중")
        self.status_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.status_label.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")

        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.status_label)
        layout.addLayout(title_row)

        subtitle = QLabel("설치된 모든 앱을 감시합니다. ON 토글 = 해당 앱 감시 제외(화이트리스트)")
        subtitle.setFont(QFont("Arial", 13))
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(line)

        # 프로그램 목록 헤더
        header_layout = QHBoxLayout()
        header_label = QLabel("📋 화이트리스트 관리 (ON = 감시 제외)")
        header_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 프로그램 목록 (스크롤)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: transparent;")
        self.apps_layout = QVBoxLayout(scroll_widget)
        self.apps_layout.setSpacing(6)

        self.app_rows: list[AppRow] = []
        self._build_app_rows()

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # 게임 설정 영역
        settings_frame = QFrame()
        settings_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD_BG};
                border-radius: 10px;
                padding: 8px;
            }}
        """)
        settings_layout = QHBoxLayout(settings_frame)
        settings_layout.setContentsMargins(16, 12, 16, 12)

        settings_title = QLabel("⚙️ 게임 설정 (랜덤 선택)")
        settings_title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        settings_layout.addWidget(settings_title)
        settings_layout.addStretch()

        # 에임 설정: 타겟 수
        self.aim_target_label = QLabel("타겟 수:")
        settings_layout.addWidget(self.aim_target_label)
        self.target_combo = QComboBox()
        for n in range(3, 11):
            self.target_combo.addItem(f"{n}개", n)
        self.target_combo.setCurrentIndex(self.config.target_count - 3)
        settings_layout.addWidget(self.target_combo)

        settings_layout.addSpacing(8)

        # 에임 설정: 제한 시간
        self.aim_time_label = QLabel("제한 시간:")
        settings_layout.addWidget(self.aim_time_label)
        self.time_combo = QComboBox()
        time_options = [5, 8, 10, 15, 20, 30]
        for t in time_options:
            self.time_combo.addItem(f"{t}초", t)
        idx = time_options.index(self.config.time_limit) if self.config.time_limit in time_options else 2
        self.time_combo.setCurrentIndex(idx)
        settings_layout.addWidget(self.time_combo)

        # 벌레 설정: 목표 점수
        self.bug_score_label = QLabel("목표 점수:")
        settings_layout.addWidget(self.bug_score_label)
        self.score_combo = QComboBox()
        score_options = [100, 150, 200, 300, 500]
        for s in score_options:
            self.score_combo.addItem(f"{s}점", s)
        idx_s = score_options.index(self.config.goal_score) if self.config.goal_score in score_options else 2
        self.score_combo.setCurrentIndex(idx_s)
        settings_layout.addWidget(self.score_combo)

        settings_layout.addSpacing(8)

        # 벌레 설정: 제한 시간
        self.bug_time_label = QLabel("제한 시간:")
        settings_layout.addWidget(self.bug_time_label)
        self.bug_time_combo = QComboBox()
        bug_time_options = [15, 20, 30, 45, 60]
        for t in bug_time_options:
            self.bug_time_combo.addItem(f"{t}초", t)
        idx_bt = bug_time_options.index(self.config.time_limit_bug) if self.config.time_limit_bug in bug_time_options else 2
        self.bug_time_combo.setCurrentIndex(idx_bt)
        settings_layout.addWidget(self.bug_time_combo)

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

        layout.addWidget(settings_frame)

        # 버튼 행: 설정 저장 + 재스캔
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.save_btn = QPushButton("💾  화이트리스트 저장")
        self.save_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.save_btn.setFixedHeight(44)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}
        """)
        self.save_btn.clicked.connect(self._save_and_restart_monitoring)
        btn_layout.addWidget(self.save_btn, 1)

        self.rescan_btn = QPushButton("🔄  앱 재스캔")
        self.rescan_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.rescan_btn.setFixedHeight(44)
        self.rescan_btn.setFixedWidth(140)
        self.rescan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rescan_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BORDER};
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; background-color: #3d4f6f; }}
        """)
        self.rescan_btn.clicked.connect(self._rescan_apps)
        btn_layout.addWidget(self.rescan_btn)

        layout.addLayout(btn_layout)

        return page

    def _build_app_rows(self):
        """현재 스캔된 앱 목록으로 앱 행 재생성 (stretch 포함 전체 제거 후 재구성)"""
        # 레이아웃 아이템 전체 제거 (AppRow + stretch spacer 포함)
        while self.apps_layout.count():
            item = self.apps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.app_rows.clear()

        for app in self._all_apps:  # __init__에서 캐시된 목록 사용
            is_whitelisted = app["name"] in self.config.whitelist
            row = AppRow(app, whitelisted=is_whitelisted)
            self.app_rows.append(row)
            self.apps_layout.addWidget(row)
        self.apps_layout.addStretch()  # 항상 마지막에 stretch 추가

    # ─── 시스템 트레이 ──────────────────────────────

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("AimGuard")

        # 기본 아이콘 설정 (앱 아이콘 사용)
        app_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(app_icon)
        self.setWindowIcon(app_icon)

        menu = QMenu()
        show_action = QAction("설정 열기", self)
        show_action.triggered.connect(self._show_settings)
        menu.addAction(show_action)

        quit_action = QAction("종료", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    # ─── 이벤트 핸들러 ──────────────────────────────

    @Slot(str, str)
    def _on_process_detected(self, app_name: str, app_path: str):
        """잠금 프로그램 감지됨 — 랜덤 게임 실행"""
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

    @Slot()
    def _on_game_success(self):
        """게임 성공 — 프로그램 실행"""
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget}
        active_widget = idx_to_widget.get(self.stack.currentIndex(), self.aim_widget)
        app_path = active_widget.app_path
        process_name = ""

        for app in self._all_apps:
            if app["path"] == app_path:
                process_name = app["process_name"]
                break

        try:
            subprocess.Popen(["open", app_path])
        except Exception:
            pass

        if process_name:
            self.monitor.mark_allowed(process_name)

        self.stack.setCurrentIndex(0)
        self.hide()

    @Slot()
    def _on_game_failed(self):
        """게임 실패 — 버튼 선택 대기 (aim_game 위젯에서 처리)"""
        pass

    @Slot()
    def _on_game_quit(self):
        """게임 포기 — 설정 화면으로 돌아가기"""
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget}
        active_widget = idx_to_widget.get(self.stack.currentIndex(), self.aim_widget)
        process_name = ""
        for app in self._all_apps:
            if app["path"] == active_widget.app_path:
                process_name = app["process_name"]
                break
        if process_name:
            self.monitor.clear_cooldown(process_name)
        self.stack.setCurrentIndex(0)
        self.hide()

    @Slot()
    def _on_motion_game_quit(self):
        """모션 게임 포기 — motion 제외 후 재추첨 (폴백 포함)"""
        pool = ["aim", "bug", "keyboard"]
        self._launch_game(
            random.choice(pool),
            self._pending_app_name,
            self._pending_app_path,
        )

    def _show_settings(self):
        """설정 화면 표시"""
        self.stack.setCurrentIndex(0)
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        """트레이 아이콘 클릭 시 설정 화면 표시 (macOS 호환)"""
        # macOS에서는 DoubleClick이 안 먹을 수 있어서 Trigger도 처리
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_settings()

    def _quit_app(self):
        """앱 종료"""
        self._monitoring = False
        self.monitor.stop()
        self.tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _save_and_restart_monitoring(self):
        """화이트리스트 저장 후 모니터링 재시작"""
        self._save_config()
        self.monitor.stop()  # NOTE: Qt 메인 스레드를 최대 3초 블로킹 (wait(3000))
        self._auto_start_monitoring()
        self.hide()

    def _rescan_apps(self):
        """앱 목록 재스캔 후 UI + _all_apps 갱신"""
        from config import scan_installed_apps
        self._all_apps = scan_installed_apps()
        self._build_app_rows()

    def _save_config(self):
        """현재 UI 토글 상태를 화이트리스트로 저장

        NOTE: 현재 _all_apps 스캔에서 누락된 앱은 화이트리스트에서 제거됨.
        """
        self.config.whitelist = set(DEFAULT_WHITELIST)
        for row in self.app_rows:
            if row.toggle.is_on:
                self.config.whitelist.add(row.app_data["name"])
        self.config.target_count = self.target_combo.currentData()
        self.config.time_limit = self.time_combo.currentData()
        self.config.time_limit_bug = self.bug_time_combo.currentData()
        self.config.goal_score = self.score_combo.currentData()
        self.config.accuracy_threshold = self.keyboard_acc_combo.currentData()
        self.config.time_limit_keyboard = self.keyboard_time_combo.currentData()
        self.config.motion_reps = self.motion_reps_combo.currentData()
        self.config.time_limit_motion = self.motion_time_combo.currentData()
        self.config.save()

    def closeEvent(self, event):
        """창 닫기 시 트레이로 최소화. 게임 진행 중이면 포기 처리 (cooldown 해제)."""
        event.ignore()
        current = self.stack.currentIndex()
        if current in (1, 2, 3, 4):
            # 모션 게임 카메라 스레드 명시적 중단 (game_quit 시그널 우회)
            if current == 4:
                self.motion_widget._stop_thread()
            self._on_game_quit()
        else:
            self.hide()
