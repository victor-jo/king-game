"""벌레 잡기 게임 위젯 모듈 — 바탕화면 벌레 퇴치 게임

리치 이펙트 + 사운드 버전
"""

import math
import random
from dataclasses import dataclass, field

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF, QLineF, QUrl
from PySide6.QtGui import (
    QPainter, QColor, QFont, QBrush, QPen, QRadialGradient, QLinearGradient,
)
from PySide6.QtMultimedia import QSoundEffect

from sounds import get_sound_path, generate_all_sounds


# ─── 무기 정의 ───────────────────────────────────────

WEAPONS = [
    {"name": "망치",       "emoji": "🔨", "type": "smash",  "damage": 3, "cooldown": 1.0,  "radius": 40,  "sound": "smash"},
    {"name": "전기톱",     "emoji": "🪚", "type": "drag",   "damage": 2, "cooldown": 0.0,  "radius": 25,  "sound": "chainsaw"},
    {"name": "기관총",     "emoji": "🔫", "type": "rapid",  "damage": 1, "cooldown": 0.1,  "radius": 15,  "sound": "gunshot"},
    {"name": "화염방사기", "emoji": "🔥", "type": "flame",  "damage": 1, "cooldown": 0.0,  "radius": 35,  "sound": "flame"},
    {"name": "수압기",     "emoji": "💧", "type": "aoe",    "damage": 2, "cooldown": 1.5,  "radius": 80,  "sound": "water"},
    {"name": "레이저",     "emoji": "⚡", "type": "laser",  "damage": 5, "cooldown": 2.0,  "radius": 10,  "sound": "laser"},
]

# ─── 벌레 정의 ───────────────────────────────────────

BUG_TYPES = [
    {"name": "애벌레",   "emoji": "🐛", "speed": 1.0, "hp": 1, "score": 10, "move": "linear"},
    {"name": "바퀴벌레", "emoji": "🪳", "speed": 3.0, "hp": 1, "score": 30, "move": "erratic"},
    {"name": "개미",     "emoji": "🐜", "speed": 1.5, "hp": 1, "score": 20, "move": "group"},
    {"name": "거미",     "emoji": "🕷️", "speed": 2.0, "hp": 2, "score": 50, "move": "diagonal"},
]

# ─── 사망 이펙트 색상 ────────────────────────────────

SPLAT_COLORS = {
    "🐛": ["#7CFC00", "#32CD32", "#228B22"],       # 초록 (애벌레)
    "🪳": ["#8B4513", "#A0522D", "#D2691E"],       # 갈색 (바퀴벌레)
    "🐜": ["#2F4F4F", "#696969", "#808080"],       # 회색 (개미)
    "🕷️": ["#800080", "#9932CC", "#BA55D3"],       # 보라 (거미)
}


@dataclass
class Bug:
    """벌레 객체"""
    x: float
    y: float
    bug_type: dict
    hp: int = 0
    vx: float = 0.0
    vy: float = 0.0
    alive: bool = True
    hit_flash: float = 0.0
    scale: float = 1.0       # 피격 시 크기 변화
    rotation: float = 0.0    # 회전

    def __post_init__(self):
        if self.hp == 0:
            self.hp = self.bug_type["hp"]
        speed = self.bug_type["speed"]
        move = self.bug_type["move"]

        if move == "linear":
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * speed
            self.vy = math.sin(angle) * speed
        elif move == "erratic":
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle) * speed
            self.vy = math.sin(angle) * speed
        elif move == "diagonal":
            diag = random.choice([(1, 1), (1, -1), (-1, 1), (-1, -1)])
            self.vx = diag[0] * speed
            self.vy = diag[1] * speed
        elif move == "group":
            self.vx = speed
            self.vy = 0

        self.rotation = random.uniform(0, 360)

    def update(self, w: int, h: int, top: int = 80, bottom: int = 60):
        if not self.alive:
            return

        self.hit_flash = max(0, self.hit_flash - 0.06)
        self.scale = 1.0 + self.hit_flash * 0.3  # 피격 시 약간 커짐

        if self.bug_type["move"] == "erratic" and random.random() < 0.05:
            angle = random.uniform(0, 2 * math.pi)
            speed = self.bug_type["speed"]
            self.vx = math.cos(angle) * speed
            self.vy = math.sin(angle) * speed

        self.x += self.vx
        self.y += self.vy

        # 이동 방향으로 회전
        if abs(self.vx) > 0.01 or abs(self.vy) > 0.01:
            target_rot = math.degrees(math.atan2(self.vy, self.vx))
            self.rotation = target_rot

        if self.x < 20 or self.x > w - 20:
            self.vx = -self.vx
            self.x = max(20, min(w - 20, self.x))
        if self.y < top + 10 or self.y > h - bottom - 10:
            self.vy = -self.vy
            self.y = max(top + 10, min(h - bottom - 10, self.y))

    def take_damage(self, damage: int):
        self.hp -= damage
        self.hit_flash = 1.0
        if self.hp <= 0:
            self.alive = False


@dataclass
class Effect:
    """시각 이펙트"""
    x: float
    y: float
    effect_type: str
    life: float = 1.0
    max_life: float = 1.0
    vx: float = 0.0
    vy: float = 0.0
    radius: float = 10
    color: str = "#ffffff"
    text: str = ""        # 텍스트 이펙트용
    x2: float = 0.0       # 레이저 끝점
    y2: float = 0.0
    gravity: float = 0.0  # 중력 적용

    def __post_init__(self):
        self.max_life = self.life

    def update(self):
        self.life -= 0.04
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity


class BugGameWidget(QWidget):
    """벌레 잡기 게임 캔버스 위젯 — 리치 이펙트 버전"""

    game_success = Signal()
    game_failed = Signal()
    game_quit = Signal()

    def __init__(self, time_limit: int = 30, goal_score: int = 200, parent=None):
        super().__init__(parent)
        self.time_limit = time_limit
        self.goal_score = goal_score
        self.app_name = ""
        self.app_path = ""

        # 게임 상태
        self.bugs: list[Bug] = []
        self.effects: list[Effect] = []
        self.score = 0
        self.remaining_time = 0.0
        self.is_running = False
        self.is_failed = False
        self.is_success = False

        # 화면 흔들림
        self.shake_x = 0.0
        self.shake_y = 0.0
        self.shake_intensity = 0.0

        # 콤보
        self.combo = 0
        self.combo_timer = 0.0

        # 무기
        self.current_weapon = 0
        self.weapon_cooldowns: list[float] = [0.0] * len(WEAPONS)
        self.mouse_pressed = False
        self.mouse_x = 0.0
        self.mouse_y = 0.0
        self.laser_first_point: QPointF | None = None

        # 드래그 궤적 (전기톱/화염방사기)
        self.drag_trail: list[tuple[float, float, float]] = []  # (x, y, life)

        # 스폰 타이머
        self.spawn_timer = 0.0

        # 게임 루프 타이머 (60fps)
        self.game_timer = QTimer(self)
        self.game_timer.setInterval(16)
        self.game_timer.timeout.connect(self._tick)

        self.setMinimumSize(600, 500)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 사운드 초기화
        generate_all_sounds()
        self._sounds: dict[str, QSoundEffect] = {}
        for name in ["smash", "chainsaw", "gunshot", "flame", "water", "laser", "bug_death", "success", "fail"]:
            se = QSoundEffect(self)
            se.setSource(QUrl.fromLocalFile(get_sound_path(name)))
            se.setVolume(0.5)
            self._sounds[name] = se

        # 실패 오버레이
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

        self.fail_score_label = QLabel("")
        self.fail_score_label.setFont(QFont("Arial", 18))
        self.fail_score_label.setStyleSheet("color: #e2e8f0; background: transparent;")
        self.fail_score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fail_layout.addWidget(self.fail_score_label)

        fail_layout.addSpacing(20)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(20)

        retry_btn = QPushButton("🔄 재도전")
        retry_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        retry_btn.setFixedSize(180, 55)
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        retry_btn.setStyleSheet("""
            QPushButton { background-color: #4ECDC4; color: #fff; border: none; border-radius: 12px; }
            QPushButton:hover { background-color: #45B7B8; }
        """)
        retry_btn.clicked.connect(self._retry_game)
        btn_row.addWidget(retry_btn)

        quit_btn = QPushButton("🏠 돌아가기")
        quit_btn.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        quit_btn.setFixedSize(180, 55)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet("""
            QPushButton { background-color: #2d3748; color: #e2e8f0; border: 2px solid #4a5568; border-radius: 12px; }
            QPushButton:hover { background-color: #3d4f6f; }
        """)
        quit_btn.clicked.connect(self._quit_game)
        btn_row.addWidget(quit_btn)
        fail_layout.addLayout(btn_row)

    def _play_sound(self, name: str):
        """사운드 재생"""
        se = self._sounds.get(name)
        if se:
            if se.isPlaying():
                se.stop()
            se.play()

    def update_settings(self, time_limit: int, goal_score: int):
        self.time_limit = time_limit
        self.goal_score = goal_score

    def start_game(self, app_name: str, app_path: str):
        self.app_name = app_name
        self.app_path = app_path
        self.score = 0
        self.remaining_time = self.time_limit
        self.is_running = True
        self.is_failed = False
        self.is_success = False
        self.bugs.clear()
        self.effects.clear()
        self.drag_trail.clear()
        self.current_weapon = 0
        self.weapon_cooldowns = [0.0] * len(WEAPONS)
        self.spawn_timer = 0.0
        self.mouse_pressed = False
        self.laser_first_point = None
        self.shake_intensity = 0.0
        self.combo = 0
        self.combo_timer = 0.0
        self._fail_overlay.hide()
        self._spawn_wave()
        self.game_timer.start()
        self.update()

    # ─── 게임 루프 ──────────────────────────────────

    def _tick(self):
        dt = 0.016

        if not self.is_running:
            return

        self.remaining_time -= dt
        if self.remaining_time <= 0:
            self.remaining_time = 0
            self._on_fail()
            return

        # 쿨다운
        for i in range(len(self.weapon_cooldowns)):
            self.weapon_cooldowns[i] = max(0, self.weapon_cooldowns[i] - dt)

        # 콤보 타이머
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0

        # 화면 흔들림 감소
        if self.shake_intensity > 0:
            self.shake_intensity *= 0.85
            self.shake_x = random.uniform(-1, 1) * self.shake_intensity
            self.shake_y = random.uniform(-1, 1) * self.shake_intensity
            if self.shake_intensity < 0.5:
                self.shake_intensity = 0
                self.shake_x = 0
                self.shake_y = 0

        # 벌레 업데이트
        for bug in self.bugs:
            bug.update(self.width(), self.height())
        self.bugs = [b for b in self.bugs if b.alive]

        # 이펙트 업데이트
        for effect in self.effects:
            effect.update()
        self.effects = [e for e in self.effects if e.life > 0]

        # 드래그 궤적 업데이트
        self.drag_trail = [(x, y, l - 0.06) for x, y, l in self.drag_trail if l > 0.06]

        # 연속 공격 무기
        if self.mouse_pressed and self.is_running:
            weapon = WEAPONS[self.current_weapon]
            if weapon["type"] in ("drag", "flame"):
                self._attack_area(self.mouse_x, self.mouse_y, weapon)
            elif weapon["type"] == "rapid" and self.weapon_cooldowns[self.current_weapon] <= 0:
                self._attack_area(self.mouse_x, self.mouse_y, weapon)
                self.weapon_cooldowns[self.current_weapon] = weapon["cooldown"]
                self._add_bullet_effect(self.mouse_x, self.mouse_y)
                self._play_sound("gunshot")

        # 스폰
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self._spawn_wave()
            self.spawn_timer = 3.0

        self.update()

    def _spawn_wave(self):
        w, h = self.width(), self.height()
        if w < 100:
            w, h = 600, 500

        num_bugs = random.randint(3, 6)
        for _ in range(num_bugs):
            bug_type = random.choices(BUG_TYPES, weights=[40, 25, 25, 10], k=1)[0]

            if bug_type["move"] == "group":
                base_x = random.randint(50, w - 50)
                base_y = random.randint(120, h - 100)
                for j in range(3):
                    self.bugs.append(Bug(x=base_x + j * 25, y=base_y, bug_type=bug_type))
            else:
                x = random.randint(50, w - 50)
                y = random.randint(120, h - 100)
                self.bugs.append(Bug(x=x, y=y, bug_type=bug_type))

    # ─── 공격 로직 ──────────────────────────────────

    def _attack_area(self, mx: float, my: float, weapon: dict):
        radius = weapon["radius"]
        for bug in self.bugs:
            if not bug.alive:
                continue
            dx = bug.x - mx
            dy = bug.y - my
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < radius + 15:
                bug.take_damage(weapon["damage"])
                if not bug.alive:
                    self._on_bug_killed(bug)

    def _attack_laser(self, x1: float, y1: float, x2: float, y2: float):
        weapon = WEAPONS[self.current_weapon]
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        for bug in self.bugs:
            if not bug.alive:
                continue
            dist = abs(dy * bug.x - dx * bug.y + x2 * y1 - y2 * x1) / length
            if dist < 25:
                bug.take_damage(weapon["damage"])
                if not bug.alive:
                    self._on_bug_killed(bug)

    def _on_bug_killed(self, bug: Bug):
        """벌레 사망 처리 — 이펙트 + 사운드 + 점수"""
        # 콤보
        self.combo += 1
        self.combo_timer = 2.0

        # 점수 (콤보 배율)
        multiplier = min(self.combo, 5)
        score_gain = bug.bug_type["score"] * multiplier
        self.score += score_gain

        # 화면 흔들림
        self.shake_intensity = min(8 + self.combo * 2, 20)

        # 사운드
        self._play_sound("bug_death")

        # ── 사망 이펙트 ──

        bx, by = bug.x, bug.y
        emoji = bug.bug_type["emoji"]
        colors = SPLAT_COLORS.get(emoji, ["#FF6B6B", "#FF4444", "#CC3333"])

        # 1) 피 튀김 파티클 (방사형)
        for i in range(12):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2, 8)
            self.effects.append(Effect(
                x=bx, y=by, effect_type="splat",
                vx=math.cos(angle) * speed, vy=math.sin(angle) * speed,
                radius=random.uniform(3, 8),
                color=random.choice(colors),
                life=random.uniform(0.5, 1.0),
                gravity=0.2,
            ))

        # 2) 충격파 링
        self.effects.append(Effect(
            x=bx, y=by, effect_type="shockwave",
            radius=5, color=colors[0], life=0.5,
        ))

        # 3) 점수 팝업 텍스트
        combo_text = f"+{score_gain}" + (f" x{multiplier}!" if multiplier > 1 else "")
        self.effects.append(Effect(
            x=bx, y=by - 10, effect_type="score_popup",
            vy=-2.5, text=combo_text,
            color="#FFD700" if multiplier > 1 else "#ffffff",
            life=1.0,
        ))

        # 4) 이모지 파편 (죽은 벌레 이모지 스핀)
        for _ in range(3):
            self.effects.append(Effect(
                x=bx + random.randint(-5, 5), y=by + random.randint(-5, 5),
                effect_type="emoji_debris",
                vx=random.uniform(-3, 3), vy=random.uniform(-5, -1),
                text=emoji, life=0.8, gravity=0.3,
            ))

        # 5) 바닥 얼룩 (오래 지속)
        self.effects.append(Effect(
            x=bx + random.randint(-10, 10), y=by + random.randint(-5, 5),
            effect_type="stain",
            radius=random.uniform(15, 25),
            color=random.choice(colors),
            life=3.0,
        ))

        # 성공 체크
        if self.score >= self.goal_score:
            self._on_success()

    # ─── 무기 이펙트 ────────────────────────────────

    def _add_smash_effect(self, x: float, y: float):
        """망치: 충격파 + 균열선"""
        # 충격파 파티클
        for i in range(16):
            angle = i * math.pi / 8 + random.uniform(-0.2, 0.2)
            speed = random.uniform(3, 7)
            self.effects.append(Effect(
                x=x, y=y, effect_type="splat",
                vx=math.cos(angle) * speed, vy=math.sin(angle) * speed,
                radius=random.uniform(4, 8), color="#FFD700", life=0.5,
                gravity=0.1,
            ))
        # 중앙 플래시
        self.effects.append(Effect(
            x=x, y=y, effect_type="flash",
            radius=60, color="#FFFFFF", life=0.3,
        ))
        # 충격파 링
        self.effects.append(Effect(
            x=x, y=y, effect_type="shockwave",
            radius=10, color="#FFD700", life=0.6,
        ))
        self._play_sound("smash")

    def _add_bullet_effect(self, x: float, y: float):
        """기관총: 총구 화염 + 탄착 효과"""
        # 머즐 플래시
        self.effects.append(Effect(
            x=x + random.randint(-3, 3), y=y + random.randint(-3, 3),
            effect_type="flash", radius=12, color="#FFAA00", life=0.15,
        ))
        # 탄착 화염
        for _ in range(3):
            self.effects.append(Effect(
                x=x + random.randint(-8, 8), y=y + random.randint(-8, 8),
                effect_type="splat",
                vx=random.uniform(-2, 2), vy=random.uniform(-2, 2),
                radius=3, color=random.choice(["#FFAA00", "#FF6600", "#FF4400"]),
                life=0.2,
            ))

    def _add_flame_effect(self, x: float, y: float):
        """화염방사기: 불꽃 파티클 + 연기"""
        for _ in range(4):
            self.effects.append(Effect(
                x=x + random.randint(-15, 15), y=y + random.randint(-15, 15),
                effect_type="flame_particle",
                vx=random.uniform(-1.5, 1.5), vy=random.uniform(-3, -0.5),
                radius=random.uniform(6, 16),
                color=random.choice(["#FF4500", "#FF6347", "#FFD700", "#FF8C00"]),
                life=random.uniform(0.3, 0.6),
            ))
        # 연기
        if random.random() < 0.3:
            self.effects.append(Effect(
                x=x + random.randint(-10, 10), y=y - 10,
                effect_type="smoke",
                vy=-1.5, radius=random.uniform(8, 15),
                color="#444444", life=0.8,
            ))
        # 드래그 궤적
        self.drag_trail.append((x, y, 1.0))

    def _add_chainsaw_effect(self, x: float, y: float):
        """전기톱: 스파크 + 궤적"""
        for _ in range(3):
            self.effects.append(Effect(
                x=x + random.randint(-5, 5), y=y + random.randint(-5, 5),
                effect_type="spark",
                vx=random.uniform(-4, 4), vy=random.uniform(-4, 1),
                radius=2, color=random.choice(["#FFD700", "#FFA500", "#FFFFFF"]),
                life=0.3, gravity=0.2,
            ))
        self.drag_trail.append((x, y, 1.0))

    def _add_water_effect(self, x: float, y: float, radius: float):
        """수압기: 물방울 확산 + 물결"""
        for i in range(20):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(3, 8)
            self.effects.append(Effect(
                x=x, y=y, effect_type="water_drop",
                vx=math.cos(angle) * speed, vy=math.sin(angle) * speed,
                radius=random.uniform(3, 7),
                color=random.choice(["#4FC3F7", "#29B6F6", "#03A9F4", "#81D4FA"]),
                life=random.uniform(0.4, 0.8),
                gravity=0.15,
            ))
        # 중앙 물결 링
        self.effects.append(Effect(
            x=x, y=y, effect_type="shockwave",
            radius=10, color="#4FC3F7", life=0.7,
        ))
        # 플래시
        self.effects.append(Effect(
            x=x, y=y, effect_type="flash",
            radius=radius * 0.8, color="#81D4FA", life=0.2,
        ))
        self._play_sound("water")

    def _add_laser_effect(self, x1: float, y1: float, x2: float, y2: float):
        """레이저: 빔 + 잔광 + 히트 스파크"""
        # 메인 빔
        self.effects.append(Effect(
            x=x1, y=y1, effect_type="laser_beam",
            x2=x2, y2=y2, color="#00FFFF", life=0.5, radius=6,
        ))
        # 잔광
        self.effects.append(Effect(
            x=x1, y=y1, effect_type="laser_beam",
            x2=x2, y2=y2, color="#FFFFFF", life=0.25, radius=2,
        ))
        # 양쪽 끝 히트 스파크
        for px, py in [(x1, y1), (x2, y2)]:
            for _ in range(6):
                self.effects.append(Effect(
                    x=px, y=py, effect_type="spark",
                    vx=random.uniform(-5, 5), vy=random.uniform(-5, 5),
                    radius=2, color="#00FFFF", life=0.3,
                ))
        self._play_sound("laser")

    # ─── 성공/실패 ──────────────────────────────────

    def _on_success(self):
        self.game_timer.stop()
        self.is_running = False
        self.is_success = True
        self._play_sound("success")
        self.update()
        QTimer.singleShot(800, lambda: self.game_success.emit())

    def _on_fail(self):
        self.game_timer.stop()
        self.is_running = False
        self.is_failed = True
        self.fail_score_label.setText(f"점수: {self.score}/{self.goal_score}")
        self._play_sound("fail")
        self.update()
        self._fail_overlay.setGeometry(0, 0, self.width(), self.height())
        self._fail_overlay.show()
        self._fail_overlay.raise_()
        self.game_failed.emit()

    def _retry_game(self):
        self._fail_overlay.hide()
        self.start_game(self.app_name, self.app_path)

    def _quit_game(self):
        self._fail_overlay.hide()
        self.game_quit.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fail_overlay.isVisible():
            self._fail_overlay.setGeometry(0, 0, self.width(), self.height())

    # ─── 입력 이벤트 ────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_6:
            idx = key - Qt.Key.Key_1
            if idx < len(WEAPONS):
                self.current_weapon = idx
                self.laser_first_point = None
                self.update()

    def mousePressEvent(self, event):
        if not self.is_running:
            return

        mx, my = event.position().x(), event.position().y()
        self.mouse_x, self.mouse_y = mx, my

        if self._check_weapon_bar_click(mx, my):
            return

        self.mouse_pressed = True
        weapon = WEAPONS[self.current_weapon]

        if weapon["type"] == "smash" and self.weapon_cooldowns[self.current_weapon] <= 0:
            self._attack_area(mx, my, weapon)
            self.weapon_cooldowns[self.current_weapon] = weapon["cooldown"]
            self._add_smash_effect(mx, my)

        elif weapon["type"] == "aoe" and self.weapon_cooldowns[self.current_weapon] <= 0:
            self._attack_area(mx, my, weapon)
            self.weapon_cooldowns[self.current_weapon] = weapon["cooldown"]
            self._add_water_effect(mx, my, weapon["radius"])

        elif weapon["type"] == "laser":
            if self.laser_first_point is None:
                self.laser_first_point = QPointF(mx, my)
            else:
                if self.weapon_cooldowns[self.current_weapon] <= 0:
                    p1 = self.laser_first_point
                    self._attack_laser(p1.x(), p1.y(), mx, my)
                    self._add_laser_effect(p1.x(), p1.y(), mx, my)
                    self.weapon_cooldowns[self.current_weapon] = weapon["cooldown"]
                self.laser_first_point = None

        self.update()

    def mouseMoveEvent(self, event):
        self.mouse_x = event.position().x()
        self.mouse_y = event.position().y()
        if self.mouse_pressed and self.is_running:
            weapon = WEAPONS[self.current_weapon]
            if weapon["type"] == "flame":
                self._add_flame_effect(self.mouse_x, self.mouse_y)
                if random.random() < 0.15:
                    self._play_sound("flame")
            elif weapon["type"] == "drag":
                self._add_chainsaw_effect(self.mouse_x, self.mouse_y)
                if random.random() < 0.2:
                    self._play_sound("chainsaw")

    def mouseReleaseEvent(self, event):
        self.mouse_pressed = False

    def _check_weapon_bar_click(self, mx: float, my: float) -> bool:
        bar_y = self.height() - 55
        if my < bar_y:
            return False
        bar_w = len(WEAPONS) * 65
        start_x = (self.width() - bar_w) / 2
        for i in range(len(WEAPONS)):
            x = start_x + i * 65
            if x <= mx <= x + 55:
                self.current_weapon = i
                self.laser_first_point = None
                self.update()
                return True
        return False

    # ─── 렌더링 ─────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 화면 흔들림 적용
        if self.shake_intensity > 0:
            painter.translate(self.shake_x, self.shake_y)

        # 배경
        painter.fillRect(-5, -5, w + 10, h + 10, QColor("#1a1a2e"))

        # 헤더
        self._draw_header(painter, w)

        # 바닥 얼룩 (가장 아래)
        for e in self.effects:
            if e.effect_type == "stain":
                self._draw_stain(painter, e)

        # 드래그 궤적
        for tx, ty, tl in self.drag_trail:
            weapon = WEAPONS[self.current_weapon]
            if weapon["type"] == "flame":
                c = QColor("#FF4500")
                c.setAlpha(int(tl * 100))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(c))
                painter.drawEllipse(QPointF(tx, ty), 10 * tl, 10 * tl)
            elif weapon["type"] == "drag":
                c = QColor("#CCCCCC")
                c.setAlpha(int(tl * 80))
                painter.setPen(QPen(c, 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(tx, ty), 8 * tl, 8 * tl)

        # 이펙트 (벌레 뒤 레이어)
        for e in self.effects:
            if e.effect_type in ("flash", "shockwave", "smoke"):
                self._draw_effect(painter, e)

        # 벌레
        for bug in self.bugs:
            if bug.alive:
                self._draw_bug(painter, bug)

        # 이펙트 (벌레 앞 레이어)
        for e in self.effects:
            if e.effect_type not in ("flash", "shockwave", "smoke", "stain"):
                self._draw_effect(painter, e)

        # 레이저 조준선
        if self.laser_first_point and self.is_running:
            painter.setPen(QPen(QColor(0, 255, 255, 128), 2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(self.laser_first_point), QPointF(self.mouse_x, self.mouse_y))
            painter.setBrush(QBrush(QColor("#00FFFF")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.laser_first_point, 5, 5)

        # 콤보 표시
        if self.combo > 1 and self.combo_timer > 0:
            self._draw_combo(painter, w)

        # 무기바
        if self.shake_intensity > 0:
            painter.translate(-self.shake_x, -self.shake_y)
        self._draw_weapon_bar(painter, w, h)

        # 성공 오버레이
        if self.is_success:
            self._draw_success_overlay(painter, w, h)

        painter.end()

    def _draw_header(self, painter: QPainter, width: int):
        painter.fillRect(0, 0, width, 70, QColor("#16213e"))

        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        painter.drawText(20, 28, f"🪲 {self.app_name} — 벌레를 잡아라!")

        time_color = "#4ECDC4" if self.remaining_time > 5 else "#FF6B6B"
        painter.setPen(QColor(time_color))
        painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        painter.drawText(20, 55, f"⏱️ {self.remaining_time:.1f}초")

        score_ratio = min(self.score / max(self.goal_score, 1), 1.0)
        score_color = "#4ECDC4" if score_ratio >= 1 else "#FFEAA7"
        painter.setPen(QColor(score_color))
        painter.drawText(width - 200, 55, f"🏆 {self.score}/{self.goal_score}")

        bar_y = 65
        bar_w = width - 40
        painter.fillRect(20, bar_y, bar_w, 4, QColor("#2d3748"))
        painter.fillRect(20, bar_y, int(bar_w * score_ratio), 4, QColor(score_color))

    def _draw_bug(self, painter: QPainter, bug: Bug):
        painter.save()
        painter.translate(bug.x, bug.y)

        # 그림자
        shadow = QColor(0, 0, 0, 60)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QPointF(2, 4), 12, 6)

        # 피격 플래시 글로우
        if bug.hit_flash > 0:
            glow = QRadialGradient(0, 0, 25 * bug.scale)
            gc = QColor(255, 80, 80, int(bug.hit_flash * 200))
            glow.setColorAt(0, gc)
            glow.setColorAt(1, QColor(255, 80, 80, 0))
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(0, 0), 25 * bug.scale, 25 * bug.scale)

        # 벌레 이모지 (스케일 + 회전)
        painter.rotate(bug.rotation)
        painter.scale(bug.scale, bug.scale)
        painter.setFont(QFont("Arial", 22))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRectF(-15, -15, 30, 30),
            Qt.AlignmentFlag.AlignCenter,
            bug.bug_type["emoji"],
        )
        painter.restore()

    def _draw_effect(self, painter: QPainter, effect: Effect):
        alpha = max(0, min(255, int((effect.life / effect.max_life) * 255)))

        if effect.effect_type == "laser_beam":
            # 빔 글로우
            for width, a_mult in [(effect.radius * 4, 0.15), (effect.radius * 2, 0.4), (effect.radius, 1.0)]:
                c = QColor(effect.color)
                c.setAlpha(int(alpha * a_mult))
                painter.setPen(QPen(c, width))
                painter.drawLine(QPointF(effect.x, effect.y), QPointF(effect.x2, effect.y2))

        elif effect.effect_type == "shockwave":
            # 확장하는 링
            progress = 1.0 - (effect.life / effect.max_life)
            r = effect.radius + progress * 60
            c = QColor(effect.color)
            c.setAlpha(alpha)
            painter.setPen(QPen(c, max(1, 3 - progress * 3)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(effect.x, effect.y), r, r)

        elif effect.effect_type == "flash":
            # 원형 플래시
            c = QColor(effect.color)
            c.setAlpha(alpha // 2)
            grad = QRadialGradient(effect.x, effect.y, effect.radius * (effect.life / effect.max_life))
            grad.setColorAt(0, c)
            _c2 = QColor(effect.color); _c2.setAlpha(0)
            grad.setColorAt(1, _c2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            r = effect.radius * (effect.life / effect.max_life)
            painter.drawEllipse(QPointF(effect.x, effect.y), r, r)

        elif effect.effect_type == "score_popup":
            c = QColor(effect.color)
            c.setAlpha(alpha)
            painter.setPen(c)
            size = 14 + (1.0 - effect.life / effect.max_life) * 4
            painter.setFont(QFont("Arial", int(size), QFont.Weight.Bold))
            painter.drawText(
                QRectF(effect.x - 50, effect.y - 10, 100, 30),
                Qt.AlignmentFlag.AlignCenter,
                effect.text,
            )

        elif effect.effect_type == "emoji_debris":
            c = QColor(255, 255, 255, alpha)
            painter.setPen(c)
            size = max(8, int(16 * (effect.life / effect.max_life)))
            painter.setFont(QFont("Arial", size))
            painter.drawText(
                QRectF(effect.x - 10, effect.y - 10, 20, 20),
                Qt.AlignmentFlag.AlignCenter,
                effect.text,
            )

        elif effect.effect_type == "smoke":
            c = QColor(effect.color)
            r = effect.radius * (2.0 - effect.life / effect.max_life)
            c.setAlpha(int(alpha * 0.3))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(effect.x, effect.y), r, r)

        elif effect.effect_type == "flame_particle":
            c = QColor(effect.color)
            c.setAlpha(alpha)
            r = effect.radius * (effect.life / effect.max_life)
            grad = QRadialGradient(effect.x, effect.y, r)
            grad.setColorAt(0, c)
            c2 = QColor(effect.color)
            c2.setAlpha(0)
            grad.setColorAt(1, c2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPointF(effect.x, effect.y), r, r)

        else:
            # 기본 파티클 (splat, spark, water_drop, bullet)
            c = QColor(effect.color)
            c.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            r = effect.radius * (effect.life / effect.max_life)
            painter.drawEllipse(QPointF(effect.x, effect.y), max(1, r), max(1, r))

    def _draw_stain(self, painter: QPainter, effect: Effect):
        """바닥 얼룩"""
        alpha = min(80, int((effect.life / effect.max_life) * 80))
        c = QColor(effect.color)
        c.setAlpha(alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c))
        painter.drawEllipse(QPointF(effect.x, effect.y), effect.radius, effect.radius * 0.6)

    def _draw_combo(self, painter: QPainter, w: int):
        """콤보 표시"""
        alpha = int(min(255, self.combo_timer * 200))
        c = QColor("#FFD700")
        c.setAlpha(alpha)
        painter.setPen(c)
        painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        painter.drawText(QRectF(w - 200, 75, 180, 40), Qt.AlignmentFlag.AlignRight, f"🔥 x{self.combo} COMBO")

    def _draw_weapon_bar(self, painter: QPainter, w: int, h: int):
        bar_h = 55
        bar_y = h - bar_h
        painter.fillRect(0, bar_y, w, bar_h, QColor("#16213e"))

        total_w = len(WEAPONS) * 65
        start_x = (w - total_w) / 2

        for i, weapon in enumerate(WEAPONS):
            x = start_x + i * 65
            is_selected = i == self.current_weapon
            on_cooldown = self.weapon_cooldowns[i] > 0

            # 배경
            if is_selected:
                # 선택된 무기 글로우
                glow = QColor("#4ECDC4")
                glow.setAlpha(40)
                painter.fillRect(int(x) - 2, bar_y, 59, bar_h, glow)
                painter.fillRect(int(x), bar_y + 3, 55, bar_h - 6, QColor("#4ECDC4"))
            elif on_cooldown:
                painter.fillRect(int(x), bar_y + 3, 55, bar_h - 6, QColor("#1a1a2e"))
            else:
                painter.fillRect(int(x), bar_y + 3, 55, bar_h - 6, QColor("#2d3748"))

            # 이모지
            painter.setFont(QFont("Arial", 22))
            painter.setPen(QColor("#ffffff") if not on_cooldown else QColor("#666666"))
            painter.drawText(
                QRectF(x, bar_y, 55, bar_h - 12),
                Qt.AlignmentFlag.AlignCenter,
                weapon["emoji"],
            )

            # 단축키
            painter.setFont(QFont("Arial", 10))
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(
                QRectF(x, bar_y + bar_h - 16, 55, 14),
                Qt.AlignmentFlag.AlignCenter,
                str(i + 1),
            )

            # 쿨다운 오버레이
            if on_cooldown:
                cd = self.weapon_cooldowns[i]
                max_cd = weapon["cooldown"]
                ratio = cd / max_cd if max_cd > 0 else 0
                overlay_h = int((bar_h - 6) * ratio)
                cd_color = QColor(0, 0, 0, 120)
                painter.fillRect(int(x), bar_y + 3 + (bar_h - 6 - overlay_h), 55, overlay_h, cd_color)

    def _draw_success_overlay(self, painter: QPainter, w: int, h: int):
        overlay = QColor(0, 0, 0, 180)
        painter.fillRect(-5, -5, w + 10, h + 10, overlay)

        painter.setPen(QColor("#4ECDC4"))
        painter.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, w, h - 60), Qt.AlignmentFlag.AlignCenter, "🎉 성공!")

        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Arial", 20))
        painter.drawText(QRectF(0, 30, w, h), Qt.AlignmentFlag.AlignCenter, f"점수: {self.score}")

        painter.setFont(QFont("Arial", 16))
        painter.drawText(QRectF(0, 70, w, h), Qt.AlignmentFlag.AlignCenter, "프로그램을 실행합니다...")
