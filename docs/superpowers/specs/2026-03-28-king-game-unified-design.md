# KingGame 통합 앱 잠금 프로그램 — 설계 문서

**날짜:** 2026-03-28
**상태:** 승인됨
**베이스:** mouse-game (AimGuard) 확장

---

## 개요

mouse-game(AimGuard), keyboard-game(타자 연습), motion-game(스쿼트/푸쉬업/싯업)을 하나의 PySide6 앱으로 통합한다. 감시 대상 앱 실행 감지 시 4종류 미니게임(에임, 벌레, 타자, 모션) 중 랜덤으로 하나를 실행하며, 클리어 시에만 앱 실행이 허용된다.

---

## 프레임워크 통일

- **통일 프레임워크:** PySide6
- mouse-game: 기존 PySide6 → 그대로 재사용
- keyboard-game: PyQt6 → PySide6 마이그레이션
- motion-game: PyQt5 → PySide6 마이그레이션

---

## 프로젝트 구조

```
king-game/
├── main.py                  # 진입점 (앱 이름: KingGame)
├── main_window.py           # 메인 윈도우 + 게임 라우터 (기존 확장)
├── config.py                # 설정 (keyboard/motion 파라미터 필드 추가)
├── process_monitor.py       # 변경 없음
├── aim_game.py              # 변경 없음
├── bug_game.py              # 변경 없음
├── keyboard_game.py         # 새 파일 (keyboard-game/poc.py → PySide6 포팅)
├── motion_game.py           # 새 파일 (3종목 통합, PyQt5→PySide6 마이그레이션)
├── sounds.py                # 변경 없음
├── config.json              # 설정 파일
└── requirements.txt         # pyside6, psutil, opencv-python, mediapipe, numpy
```

---

## 게임별 완료 조건

모든 게임 위젯은 동일한 3개의 PySide6 시그널을 노출한다:

```python
game_success = Signal()   # 클리어 → 앱 허용
game_failed  = Signal()   # 실패 → 재도전/포기 선택
game_quit    = Signal()   # 포기 → 설정 화면 복귀
```

| 게임 | 클리어 조건 | 실패 조건 | 설정 파라미터 |
|---|---|---|---|
| **Aim** | N개 타겟 순서대로 클릭 | 제한 시간 초과 / 오순서 클릭 | target_count, time_limit |
| **Bug** | 제한 시간 내 목표 점수 달성 | 시간 초과 | goal_score, time_limit_bug |
| **Keyboard** | 1문장 정확도 ≥ N% 달성 | 제한 시간 초과 | accuracy_threshold, time_limit_keyboard |
| **Motion** | 제한 시간 내 N회 반복 | 시간 초과 | motion_reps, time_limit_motion |

---

## 게임 선택 로직

```python
GAME_POOL = ["aim", "bug", "keyboard", "motion"]

def _on_process_detected(self, app_name, app_path):
    game_type = random.choice(GAME_POOL)
    # motion 선택 시 폴백 처리 포함
```

---

## Motion Game 상세 설계

### 종목 정의

```python
EXERCISES = [
    {"name": "스쿼트",  "emoji": "🏋️",
     "joints": (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE),
     "down_threshold": 90, "up_threshold": 160},
    {"name": "푸쉬업",  "emoji": "💪",
     "joints": (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST),
     "down_threshold": 90, "up_threshold": 160},
    {"name": "싯업",    "emoji": "🧘",
     "joints": (RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE),
     "down_threshold": 60, "up_threshold": 120},
]
```

- `start_game()` 호출 시 `random.choice(EXERCISES)` 로 종목 결정
- VideoThread(QThread) + PoseLandmarker로 카메라 프레임 처리
- 목표 횟수(motion_reps) 달성 시 `game_success` emit
- 제한 시간(time_limit_motion) 초과 시 `game_failed` emit

### 폴백 처리

```python
# MotionGameWidget.start_game() 내부
try:
    import cv2
    import mediapipe as mp
    # 카메라 열기 시도
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError("카메라 없음")
    cap.release()
except Exception:
    self.game_quit.emit()   # 즉시 포기 시그널 → main_window 재추첨

# main_window._on_game_quit() 에서 재추첨
def _on_game_quit_with_fallback(self, excluded="motion"):
    pool = [g for g in GAME_POOL if g != excluded]
    game_type = random.choice(pool)
    self._launch_game(game_type, self._pending_app_name, self._pending_app_path)
```

---

## Keyboard Game 상세 설계

- poc.py의 명언 리스트(20개) 유지
- 게임 시작 시 랜덤 문장 1개 제시
- 사용자가 문장 입력 후 Enter → 정확도 계산
- 정확도 ≥ `accuracy_threshold`% → `game_success`
- 정확도 미달 → `game_failed` (재도전 가능)
- `time_limit_keyboard` 초 초과 → `game_failed`
- 헤더에 실시간 WPM, 정확도, 남은 시간 표시

---

## 설정 UI 변경

기존 게임 선택 콤보박스 제거 (완전 랜덤). 각 게임별 난이도 파라미터 섹션 추가:

```
⚙️ 게임 설정
├── [에임]  타겟 수: [5개 ▼]    제한 시간: [10초 ▼]
├── [벌레]  목표 점수: [200점 ▼]  제한 시간: [30초 ▼]
├── [타자]  정확도 기준: [80% ▼]  제한 시간: [30초 ▼]
└── [모션]  목표 횟수: [5회 ▼]   제한 시간: [40초 ▼]
```

---

## config.py 추가 필드

```python
@dataclass
class AppConfig:
    # ... 기존 필드 유지 ...

    # Keyboard game
    accuracy_threshold: int = 80    # % 정확도 기준
    time_limit_keyboard: int = 30   # 초

    # Motion game
    motion_reps: int = 5            # 목표 횟수
    time_limit_motion: int = 40     # 초
```

---

## 전체 데이터 흐름

```
앱 실행 감지 (ProcessMonitor)
    ↓
process_detected 시그널 emit(app_name, app_path)
    ↓
main_window._on_process_detected()
    → random.choice(["aim", "bug", "keyboard", "motion"]) → game_type 결정
    → _pending_app_name, _pending_app_path 저장
    ↓
game_type별 위젯 .start_game(app_name, app_path) 호출
    → stack.setCurrentIndex(N)
    ↓
[성공] game_success emit
    → subprocess.Popen(["open", app_path])
    → monitor.mark_allowed(process_name)
    → stack.setCurrentIndex(0)

[실패] game_failed emit
    → 실패 오버레이 표시 (재도전 / 포기 버튼)

[포기] game_quit emit
    → motion 폴백인 경우: 제외 후 재추첨 → 새 게임 시작
    → 일반 포기: monitor.clear_cooldown() → stack.setCurrentIndex(0)
```

---

## 마이그레이션 메모

| 원본 | 변경 사항 |
|---|---|
| `from PyQt6.QtWidgets import ...` | `from PySide6.QtWidgets import ...` |
| `from PyQt5.QtCore import pyqtSignal` | `from PySide6.QtCore import Signal` |
| `QImage.Format_BGR888` | 동일 (PySide6도 지원) |
| `app.exec_()` | `app.exec()` |
| `pyqtSignal` | `Signal` |
| `Qt.AlignCenter` | `Qt.AlignmentFlag.AlignCenter` (이미 mouse-game 방식 사용) |
