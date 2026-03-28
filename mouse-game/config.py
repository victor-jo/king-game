"""AimGuard 설정 관리 모듈"""

import json
import os
from dataclasses import dataclass, field, asdict

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# 감지 대상 프로그램 기본 목록
DEFAULT_APPS = [
    {"name": "KakaoTalk", "process_name": "KakaoTalk", "path": "/Applications/KakaoTalk.app", "locked": False},
    {"name": "Discord", "process_name": "Discord", "path": "/Applications/Discord.app", "locked": False},
    {"name": "Slack", "process_name": "Slack", "path": "/Applications/Slack.app", "locked": False},
    {"name": "Telegram", "process_name": "Telegram", "path": "/Applications/Telegram.app", "locked": False},
    {"name": "Steam", "process_name": "steam_osx", "path": "/Applications/Steam.app", "locked": False},
    {"name": "Google Chrome", "process_name": "Google Chrome", "path": "/Applications/Google Chrome.app", "locked": False},
    {"name": "Mattermost", "process_name": "Mattermost", "path": "/Applications/Mattermost.app", "locked": False},
]


@dataclass
class AppConfig:
    """앱 설정 데이터"""

    apps: list = field(default_factory=lambda: [app.copy() for app in DEFAULT_APPS])
    game_type: str = "aim"  # "aim" | "bug"
    target_count: int = 5  # 에임 게임: 타겟 수
    time_limit: int = 10  # 에임 게임: 제한 시간 (초)
    time_limit_bug: int = 30  # 벌레 게임: 제한 시간 (초)
    goal_score: int = 200  # 벌레 게임: 목표 점수

    # Keyboard game
    accuracy_threshold: int = 80    # % 정확도 기준 (0-100)
    time_limit_keyboard: int = 30   # 초

    # Motion game
    motion_reps: int = 5            # 목표 반복 횟수
    time_limit_motion: int = 40     # 초

    def save(self):
        """설정을 JSON 파일로 저장"""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls) -> "AppConfig":
        """JSON 파일에서 설정 불러오기"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config = cls()
                config.apps = data.get("apps", config.apps)
                config.game_type = data.get("game_type", "aim")
                config.target_count = data.get("target_count", 5)
                config.time_limit = data.get("time_limit", 10)
                config.time_limit_bug = data.get("time_limit_bug", 30)
                config.goal_score = data.get("goal_score", 200)
                config.accuracy_threshold = data.get("accuracy_threshold", 80)
                config.time_limit_keyboard = data.get("time_limit_keyboard", 30)
                config.motion_reps = data.get("motion_reps", 5)
                config.time_limit_motion = data.get("time_limit_motion", 40)
                return config
            except (json.JSONDecodeError, KeyError):
                pass
        return cls()

    def get_locked_apps(self) -> list:
        """잠금 설정된 앱 목록 반환"""
        return [app for app in self.apps if app.get("locked", False)]

    def get_locked_process_names(self) -> set:
        """잠금 설정된 프로세스명 set 반환"""
        return {app["process_name"] for app in self.apps if app.get("locked", False)}
