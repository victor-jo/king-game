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
