# Headless Monitor 개선 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AimGuard를 실행 즉시 headless로 자동 모니터링 시작하도록 개선하고, `/Applications/` 전체 스캔으로 모든 설치 앱을 감시 대상으로 만든다.

**Architecture:** 단일 프로세스 + PID 파일 방식. main.py에서 기존 인스턴스를 kill하고 재시작. PySide6 앱은 창을 숨긴 채 트레이 아이콘으로만 상주하며, 앱 감지 시에만 게임 창이 팝업된다.

**Tech Stack:** Python 3, PySide6, psutil, plistlib (표준 라이브러리)

**Spec:** `docs/superpowers/specs/2026-03-28-headless-monitor-design.md`

---

## 파일 구조

| 파일 | 변경 | 역할 |
|---|---|---|
| `mouse-game/main.py` | 수정 | PID 처리 + headless 시작 |
| `mouse-game/config.py` | 수정 | 앱 스캔 + 화이트리스트 |
| `mouse-game/main_window.py` | 수정 | 자동 모니터링 + UI 의미 반전 |
| `mouse-game/process_monitor.py` | 변경 없음 | — |
| `tests/test_config.py` | 신규 | config 로직 단위 테스트 |
| `tests/test_main_pid.py` | 신규 | PID 파일 단위 테스트 |

---

## Chunk 1: config.py — 앱 스캔 + 화이트리스트

### Task 1: 앱 스캔 + 화이트리스트 로직 (TDD)

**Files:**
- Modify: `mouse-game/config.py`
- Create: `mouse-game/tests/test_config.py`

- [ ] **Step 1: 테스트 파일 생성**

`mouse-game/tests/__init__.py` (빈 파일) 생성 후 `mouse-game/tests/test_config.py` 작성:

```python
"""config.py 단위 테스트"""
import os
import sys
import tempfile
import plistlib
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config as cfg


def make_app_bundle(tmpdir, app_name, executable=None):
    """테스트용 .app 번들 구조 생성"""
    app_dir = os.path.join(tmpdir, f"{app_name}.app", "Contents")
    os.makedirs(app_dir, exist_ok=True)
    plist = {"CFBundleExecutable": executable or app_name}
    with open(os.path.join(app_dir, "Info.plist"), "wb") as f:
        plistlib.dump(plist, f)
    return os.path.join(tmpdir, f"{app_name}.app")


# ── get_process_name ──────────────────────────────────────────────────


def test_get_process_name_reads_plist(tmp_path):
    make_app_bundle(str(tmp_path), "MyApp", executable="MyApp-bin")
    result = cfg.get_process_name(str(tmp_path / "MyApp.app"))
    assert result == "MyApp-bin"


def test_get_process_name_missing_plist_returns_none(tmp_path):
    app_dir = tmp_path / "NoInfo.app"
    app_dir.mkdir()
    assert cfg.get_process_name(str(app_dir)) is None


# ── scan_installed_apps ───────────────────────────────────────────────


def test_scan_installed_apps_finds_apps(tmp_path):
    make_app_bundle(str(tmp_path), "FooApp", executable="foo")
    make_app_bundle(str(tmp_path), "BarApp")
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    names = {a["name"] for a in results}
    assert "FooApp" in names
    assert "BarApp" in names


def test_scan_installed_apps_ignores_non_app(tmp_path):
    (tmp_path / "notanapp.txt").write_text("x")
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    assert results == []


def test_scan_installed_apps_uses_plist_process_name(tmp_path):
    make_app_bundle(str(tmp_path), "Chrome", executable="Google Chrome")
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    assert results[0]["process_name"] == "Google Chrome"


def test_scan_installed_apps_fallback_to_app_name(tmp_path):
    # plist 없으면 앱 이름을 프로세스명으로
    (tmp_path / "NoPlist.app").mkdir()
    results = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    assert results[0]["process_name"] == "NoPlist"


# ── AppConfig 화이트리스트 ────────────────────────────────────────────


def test_appconfig_default_whitelist_contains_finder():
    assert "Finder" in cfg.DEFAULT_WHITELIST


def test_appconfig_save_load_whitelist(tmp_path):
    config_path = str(tmp_path / "config.json")
    c = cfg.AppConfig(config_file=config_path)
    c.whitelist = {"Finder", "Safari", "MyApp"}
    c.save()
    c2 = cfg.AppConfig.load(config_file=config_path)
    assert "MyApp" in c2.whitelist
    assert "Finder" in c2.whitelist


def test_appconfig_get_monitored_apps_excludes_whitelist(tmp_path):
    make_app_bundle(str(tmp_path), "KakaoTalk")
    make_app_bundle(str(tmp_path), "Finder")
    all_apps = cfg.scan_installed_apps(app_dirs=[str(tmp_path)])
    c = cfg.AppConfig()
    c.whitelist = {"Finder"}
    monitored = c.get_monitored_apps(all_apps)
    names = {a["name"] for a in monitored}
    assert "KakaoTalk" in names
    assert "Finder" not in names
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd mouse-game && python -m pytest tests/test_config.py -v 2>&1 | head -40
```

Expected: ImportError 또는 AttributeError (함수 미구현)

- [ ] **Step 3: config.py 수정**

`mouse-game/config.py` 전체를 아래로 교체:

```python
"""AimGuard 설정 관리 모듈"""

import json
import os
import plistlib
from dataclasses import dataclass, field

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# ── 기본 화이트리스트 (감시 제외 시스템 앱) ────────────────────────────
DEFAULT_WHITELIST = {
    "Finder", "Safari", "System Preferences", "System Settings",
    "Activity Monitor", "Terminal", "Xcode", "TextEdit",
    "App Store", "Calculator", "Calendar", "Clock",
    "FaceTime", "Mail", "Maps", "Messages", "Music",
    "News", "Notes", "Photos", "Podcasts", "Preview",
    "QuickTime Player", "Reminders", "Shortcuts", "Stocks",
    "TV", "Voice Memos", "Automator", "Font Book",
    "Grapher", "Image Capture", "Migration Assistant",
    "Screenshot", "Stickies", "VoiceOver Utility",
    "AimGuard",  # 자기 자신 제외
}

DEFAULT_APP_DIRS = ["/Applications", os.path.expanduser("~/Applications")]


def get_process_name(app_path: str) -> str | None:
    """앱 번들의 Info.plist에서 CFBundleExecutable 추출"""
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    if not os.path.exists(plist_path):
        return None
    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
        return data.get("CFBundleExecutable")
    except Exception:
        return None


def scan_installed_apps(app_dirs: list[str] | None = None) -> list[dict]:
    """/Applications/ 등에서 설치된 앱 목록 반환"""
    if app_dirs is None:
        app_dirs = DEFAULT_APP_DIRS

    apps = []
    for d in app_dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".app"):
                continue
            app_name = name[:-4]
            path = os.path.join(d, name)
            process_name = get_process_name(path) or app_name
            apps.append({
                "name": app_name,
                "process_name": process_name,
                "path": path,
            })
    return apps


@dataclass
class AppConfig:
    """앱 설정 데이터"""

    whitelist: set = field(default_factory=lambda: set(DEFAULT_WHITELIST))

    # 게임 설정
    target_count: int = 5
    time_limit: int = 10
    time_limit_bug: int = 30
    goal_score: int = 200
    accuracy_threshold: int = 80
    time_limit_keyboard: int = 30
    motion_reps: int = 5
    time_limit_motion: int = 40

    def __init__(self, config_file: str = CONFIG_FILE):
        self._config_file = config_file
        self.whitelist = set(DEFAULT_WHITELIST)
        self.target_count = 5
        self.time_limit = 10
        self.time_limit_bug = 30
        self.goal_score = 200
        self.accuracy_threshold = 80
        self.time_limit_keyboard = 30
        self.motion_reps = 5
        self.time_limit_motion = 40

    def save(self):
        """설정을 JSON 파일로 저장"""
        data = {
            "whitelist": sorted(self.whitelist),
            "target_count": self.target_count,
            "time_limit": self.time_limit,
            "time_limit_bug": self.time_limit_bug,
            "goal_score": self.goal_score,
            "accuracy_threshold": self.accuracy_threshold,
            "time_limit_keyboard": self.time_limit_keyboard,
            "motion_reps": self.motion_reps,
            "time_limit_motion": self.time_limit_motion,
        }
        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, config_file: str = CONFIG_FILE) -> "AppConfig":
        """JSON 파일에서 설정 불러오기"""
        c = cls(config_file=config_file)
        if not os.path.exists(config_file):
            return c
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 화이트리스트: 저장값 + 기본값 합집합
            saved_wl = set(data.get("whitelist", []))
            c.whitelist = saved_wl | DEFAULT_WHITELIST
            c.target_count = data.get("target_count", 5)
            c.time_limit = data.get("time_limit", 10)
            c.time_limit_bug = data.get("time_limit_bug", 30)
            c.goal_score = data.get("goal_score", 200)
            c.accuracy_threshold = data.get("accuracy_threshold", 80)
            c.time_limit_keyboard = data.get("time_limit_keyboard", 30)
            c.motion_reps = data.get("motion_reps", 5)
            c.time_limit_motion = data.get("time_limit_motion", 40)
        except (json.JSONDecodeError, KeyError):
            pass
        return c

    def get_monitored_apps(self, all_apps: list[dict]) -> list[dict]:
        """화이트리스트 제외 후 감시 대상 앱 목록 반환"""
        return [a for a in all_apps if a["name"] not in self.whitelist]
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
cd mouse-game && python -m pytest tests/test_config.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 기존 config.json 마이그레이션**

기존 `config.json`을 새 포맷으로 교체:

```json
{
  "whitelist": [
    "Activity Monitor", "App Store", "Automator", "Calculator",
    "Calendar", "Clock", "FaceTime", "Finder", "Font Book",
    "Grapher", "Image Capture", "Mail", "Maps", "Messages",
    "Migration Assistant", "Music", "News", "Notes", "Photos",
    "Podcasts", "Preview", "QuickTime Player", "Reminders",
    "Safari", "Screenshot", "Shortcuts", "Stickies", "Stocks",
    "System Preferences", "System Settings", "TV", "Terminal",
    "TextEdit", "VoiceOver Utility", "Voice Memos", "Xcode"
  ],
  "target_count": 5,
  "time_limit": 10,
  "time_limit_bug": 30,
  "goal_score": 200,
  "accuracy_threshold": 80,
  "time_limit_keyboard": 30,
  "motion_reps": 5,
  "time_limit_motion": 40
}
```

- [ ] **Step 6: 커밋**

```bash
cd mouse-game && git add config.py config.json tests/ && git commit -m "feat: 앱 자동 스캔 + 화이트리스트 config 구조로 변경"
```

---

## Chunk 2: main.py — PID 파일 + Headless 시작

### Task 2: PID 파일 단일 인스턴스 처리 (TDD)

**Files:**
- Modify: `mouse-game/main.py`
- Create: `mouse-game/tests/test_main_pid.py`

- [ ] **Step 1: PID 테스트 작성**

```python
"""main.py PID 처리 단위 테스트"""
import os
import sys
import signal
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import main as m


def test_write_pid_creates_file(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    m.write_pid(pid_file)
    assert os.path.exists(pid_file)
    with open(pid_file) as f:
        assert int(f.read().strip()) == os.getpid()


def test_cleanup_pid_removes_file(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    pid_file_path = str(pid_file)
    with open(pid_file_path, "w") as f:
        f.write("12345")
    m.cleanup_pid(pid_file_path)
    assert not os.path.exists(pid_file_path)


def test_cleanup_pid_noop_if_missing(tmp_path):
    pid_file = str(tmp_path / "nonexistent.pid")
    m.cleanup_pid(pid_file)  # 예외 없이 통과해야 함


def test_kill_existing_sends_sigterm(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    with open(pid_file, "w") as f:
        f.write("99999")
    with patch("os.kill") as mock_kill:
        mock_kill.side_effect = ProcessLookupError
        m.kill_existing(pid_file)  # 예외 없이 통과
        mock_kill.assert_called_once_with(99999, signal.SIGTERM)


def test_kill_existing_handles_missing_pid_file(tmp_path):
    pid_file = str(tmp_path / "none.pid")
    m.kill_existing(pid_file)  # 예외 없이 통과


def test_kill_existing_handles_invalid_pid(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    with open(pid_file, "w") as f:
        f.write("not-a-number")
    m.kill_existing(pid_file)  # ValueError 처리, 예외 없이 통과
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd mouse-game && python -m pytest tests/test_main_pid.py -v 2>&1 | head -20
```

Expected: ImportError (함수 미구현)

- [ ] **Step 3: main.py 수정**

```python
"""AimGuard — Headless 앱 잠금 프로그램"""

import os
import sys
import signal
import time
import atexit

PID_FILE = os.path.expanduser("~/.aimguard.pid")


def write_pid(pid_file: str = PID_FILE):
    """현재 PID를 파일에 기록"""
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def cleanup_pid(pid_file: str = PID_FILE):
    """PID 파일 삭제"""
    if os.path.exists(pid_file):
        os.remove(pid_file)


def kill_existing(pid_file: str = PID_FILE):
    """기존 인스턴스를 SIGTERM으로 종료"""
    if not os.path.exists(pid_file):
        return
    try:
        with open(pid_file) as f:
            old_pid = int(f.read().strip())
        os.kill(old_pid, signal.SIGTERM)
        time.sleep(0.8)  # 종료 대기
    except (ProcessLookupError, PermissionError):
        pass  # 이미 종료됨
    except ValueError:
        pass  # pid 파일 손상


def main():
    # 1. 기존 인스턴스 종료
    kill_existing()

    # 2. 현재 PID 등록 + 종료 시 자동 삭제
    write_pid()
    atexit.register(cleanup_pid)

    # 3. PySide6 앱 시작 (창 없이)
    from PySide6.QtWidgets import QApplication
    from main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("AimGuard")
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    # show() 호출하지 않음 — headless 시작

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
cd mouse-game && python -m pytest tests/test_main_pid.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
cd mouse-game && git add main.py tests/test_main_pid.py && git commit -m "feat: PID 파일 단일 인스턴스 처리 + headless 시작"
```

---

## Chunk 3: main_window.py — 자동 모니터링 + UI 개선

### Task 3: MainWindow headless 모드 + 자동 모니터링

**Files:**
- Modify: `mouse-game/main_window.py`

> **Note:** main_window.py는 PySide6 GUI 코드로 단위 테스트가 어렵다. 수동 실행으로 검증한다.

- [ ] **Step 1: `__init__` 수정 — `_all_apps` 캐시 필드 + 자동 모니터링 시작**

`MainWindow.__init__` 내 `self._monitoring = False` 라인 뒤에 `self._all_apps: list[dict] = []` 추가:

```python
        self._monitoring = False
        self._all_apps: list[dict] = []   # ← 추가
        self._pending_game_type = ""
```

`MainWindow.__init__` 마지막 부분 (`self._setup_tray()` 다음)에 추가:

```python
        # 자동 모니터링 시작
        self._auto_start_monitoring()
```

새 메서드 추가:

```python
    def _auto_start_monitoring(self):
        """시작 시 자동으로 모니터링 시작"""
        from config import scan_installed_apps
        self._all_apps = scan_installed_apps()
        monitored = self.config.get_monitored_apps(self._all_apps)
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
```

- [ ] **Step 2: `_build_settings_page` 수정 — 감시 시작 버튼 제거 + 앱 목록 동적 생성**

기존 `_build_settings_page` 내 버튼 행과 앱 목록 부분 교체:

버튼 행 (`self.start_btn`, `self.tray_btn`)을 아래로 교체:

```python
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
```

헤더 라벨 텍스트 변경:

```python
        header_label = QLabel("📋 화이트리스트 관리 (ON = 감시 제외)")
```

subtitle 텍스트 변경:

```python
        subtitle = QLabel("설치된 모든 앱을 감시합니다. ON 토글 = 해당 앱 감시 제외(화이트리스트)")
```

상태 라벨 초기값 변경 (시작부터 감시 중):

```python
        self.status_label = QLabel("🟢 감시 중")
        self.status_label.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
```

- [ ] **Step 3: AppRow 수정 — 화이트리스트 의미로 변경 (Step 4보다 먼저 적용)**

기존 `AppRow` 클래스 전체를 아래로 교체 (시그니처 + 토글 초기값 + 아이콘 딕셔너리 유지):

```python
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
```

`ToggleButton._update_style` 내 텍스트 변경:
```python
        if self._is_on:
            self.setText("제외")   # 화이트리스트
        else:
            self.setText("감시")   # 감시 대상
```

- [ ] **Step 4: 앱 목록 동적 빌드 메서드 추가**

`_build_app_rows` 메서드 추가 (새 메서드로, 기존 코드 대체 아님):

```python
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
```

`_build_settings_page` 내 아래 블록을 `self._build_app_rows()` 단일 호출로 교체:

```python
# 교체 대상:
        self.app_rows: list[AppRow] = []
        for app in self.config.apps:
            row = AppRow(app)
            self.app_rows.append(row)
            self.apps_layout.addWidget(row)
        self.apps_layout.addStretch()

# 교체 후 (_build_app_rows 내부에서 addStretch까지 처리):
        self.app_rows: list[AppRow] = []
        self._build_app_rows()
```

- [ ] **Step 5: `_on_game_success` / `_on_game_quit` 수정 — `self.config.apps` 제거**

`AppConfig`에서 `apps` 필드가 사라지므로, 이를 참조하는 두 메서드를 `self._all_apps`로 교체:

```python
    @Slot()
    def _on_game_success(self):
        """게임 성공 — 프로그램 실행"""
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget}
        active_widget = idx_to_widget.get(self.stack.currentIndex(), self.aim_widget)
        app_path = active_widget.app_path
        process_name = ""

        for app in self._all_apps:          # self.config.apps → self._all_apps
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
    def _on_game_quit(self):
        """게임 포기 — 설정 화면으로 돌아가기"""
        idx_to_widget = {1: self.aim_widget, 2: self.bug_widget,
                         3: self.keyboard_widget, 4: self.motion_widget}
        active_widget = idx_to_widget.get(self.stack.currentIndex(), self.aim_widget)
        process_name = ""
        for app in self._all_apps:          # self.config.apps → self._all_apps
            if app["path"] == active_widget.app_path:
                process_name = app["process_name"]
                break
        if process_name:
            self.monitor.clear_cooldown(process_name)
        self.stack.setCurrentIndex(0)
        self.hide()  # 스펙: 포기 시 창 숨김
```

- [ ] **Step 6: `self.config.apps` 잔존 여부 확인**

Step 5의 `_on_game_quit` / `_on_game_success` 수정이 완료됐는지 확인:
```bash
grep -n "self.config.apps" mouse-game/main_window.py
```
Expected: 0개 매칭 (모두 `self._all_apps`로 교체됨)

- [ ] **Step 7: 저장 + 재스캔 메서드 추가**

`main_window.py` 상단 import에 아래 추가 (아직 없는 경우):
```python
from config import DEFAULT_WHITELIST
```

메서드 추가:

```python
    def _save_and_restart_monitoring(self):
        """화이트리스트 저장 후 모니터링 재시작"""
        self._save_config()
        self.monitor.stop()
        self._auto_start_monitoring()
        self.hide()

    def _rescan_apps(self):
        """앱 목록 재스캔 후 UI + _all_apps 갱신"""
        from config import scan_installed_apps
        self._all_apps = scan_installed_apps()
        self._build_app_rows()  # 내부에서 stretch 포함 전체 재구성

    def _save_config(self):
        """현재 UI 토글 상태를 화이트리스트로 저장"""
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
```

- [ ] **Step 8: `_stop_monitoring` 관련 코드 정리**

삭제 전, 아래 메서드들이 `main_window.py` 내에서만 참조되는지 확인:
```bash
grep -n "_toggle_monitoring\|_stop_monitoring\|_start_monitoring" mouse-game/main_window.py
```
Expected: `_toggle_monitoring`은 `self.start_btn.clicked.connect(self._toggle_monitoring)` 에서만 참조됨. `_start_monitoring`, `_stop_monitoring`은 `_toggle_monitoring` 내부에서만 호출됨.

확인 후 다음 메서드 3개 삭제:
- `_toggle_monitoring`
- `_start_monitoring`
- `_stop_monitoring`

`_build_settings_page` 내에서 `self.start_btn = QPushButton("▶  감시 시작")` 부터 시작하는 버튼 행 코드와 `self.tray_btn` 코드 제거 (Step 2에서 새 버튼 행으로 교체됨).

`closeEvent` 수정 — 항상 트레이로 최소화:

```python
    def closeEvent(self, event):
        """창 닫기 시 항상 트레이로 최소화"""
        event.ignore()
        self.hide()
```

- [ ] **Step 9: `_show_settings` 트레이 메뉴 연결 확인**

```bash
grep -n "_show_settings\|show_action" mouse-game/main_window.py
```

Expected 출력 예시:
```
481:        show_action = QAction("설정 열기", self)
482:        show_action.triggered.connect(self._show_settings)
668:    def _show_settings(self):
```

연결이 존재하면 통과. 없으면 `_setup_tray` 내에 아래 추가:
```python
        show_action = QAction("설정 열기", self)
        show_action.triggered.connect(self._show_settings)
        menu.addAction(show_action)
```

- [ ] **Step 10: 수동 실행 테스트**

```bash
cd mouse-game && python main.py
```

확인 사항:
- [ ] 창이 뜨지 않고 트레이 아이콘만 나타남
- [ ] 트레이 알림 "감시 시작! N개 앱 감시 중 🎯" 표시
- [ ] 트레이 우클릭 → "설정 열기" 클릭 시 설정 창 표시
- [ ] 설정 창에 `/Applications/` 앱 목록이 보임
- [ ] 두 번째 실행 시 기존 프로세스 종료 후 재시작

- [ ] **Step 11: 커밋**

```bash
cd mouse-game && git add main_window.py && git commit -m "feat: headless 자동 모니터링 + 화이트리스트 UI로 전환"
```

---

## Chunk 4: 통합 검증

### Task 4: 전체 동작 검증

- [ ] **Step 1: 전체 테스트 실행**

```bash
cd mouse-game && python -m pytest tests/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 2: 중복 실행 검증**

터미널 1에서 실행 후 터미널 2에서 재실행:

```bash
# 터미널 1
cd mouse-game && python main.py &
sleep 2

# 터미널 2
cd mouse-game && python main.py
```

확인: 터미널 1의 프로세스가 종료되고 터미널 2의 프로세스만 남음

- [ ] **Step 3: 앱 감지 검증**

1. 트레이 우클릭 → "설정 열기"
2. 설정 창에서 KakaoTalk 행의 토글이 "감시" 상태인지 확인 (OFF = 감시 중)
3. KakaoTalk이 화이트리스트에 없는지 확인 후 KakaoTalk 실행
4. AimGuard 게임 팝업 창이 나타나는지 확인 (aim/bug/keyboard/motion 중 하나)
5. 게임 창이 뜨면 성공 — 게임 클리어 후 KakaoTalk이 열리는지 확인

KakaoTalk이 설치되어 있지 않은 경우: 대신 Discord 또는 Slack 사용.

- [ ] **Step 4: 최종 커밋**

```bash
cd mouse-game && git add -A && git commit -m "chore: headless 모니터링 개선 완료"
```
