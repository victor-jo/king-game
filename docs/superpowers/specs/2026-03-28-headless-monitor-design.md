# AimGuard Headless 모니터링 개선 — 설계 문서

**날짜:** 2026-03-28
**상태:** 승인됨
**베이스:** mouse-game (AimGuard) 개선

---

## 개요

현재 AimGuard는 `python3 main.py` 실행 후 설정 창에서 "감시 시작" 버튼을 눌러야 모니터링이 시작된다. 이를 다음과 같이 개선한다:

1. 실행 즉시 headless(창 없음)로 시작, 자동으로 모니터링 시작
2. `/Applications/` 전체 스캔으로 설치된 모든 앱 감시
3. 화이트리스트로 시스템 앱 제외
4. 중복 실행 시 기존 프로세스 kill 후 새로 시작
5. 설정은 트레이 아이콘 우클릭 → "설정 열기"로 접근

---

## 아키텍처 변경 개요

| 항목 | 기존 | 신규 |
|---|---|---|
| 시작 방식 | 창 표시 → 버튼 클릭 | 창 숨김 + 즉시 모니터링 시작 |
| 감시 앱 목록 | config.json 하드코딩 7개 | `/Applications/` 전체 스캔 + 화이트리스트 |
| 중복 실행 | 미처리 | PID 파일로 기존 프로세스 kill 후 재시작 |
| 설정 접근 | 메인 창 | 트레이 우클릭 → "설정 열기" |
| AppRow 토글 | 잠금 ON/OFF | 화이트리스트(감시 제외) ON/OFF |

### 파일별 변경 범위

- **`main.py`** — PID 파일 체크/kill 로직 추가, 창 숨김으로 시작
- **`config.py`** — `apps` 하드코딩 제거, `/Applications/` 스캔 + 화이트리스트 필드
- **`main_window.py`** — 시작 시 자동 모니터링, AppRow 의미 반전
- **`process_monitor.py`** — 변경 없음

---

## 앱 자동 발견 + 화이트리스트

### `/Applications/` 스캔

```python
def scan_installed_apps() -> list[dict]:
    app_dirs = ["/Applications", os.path.expanduser("~/Applications")]
    apps = []
    for d in app_dirs:
        for name in os.listdir(d):
            if name.endswith(".app"):
                app_name = name[:-4]
                path = os.path.join(d, name)
                process_name = get_process_name(path) or app_name
                apps.append({"name": app_name, "process_name": process_name, "path": path})
    return apps
```

`get_process_name(path)`: 앱 번들의 `Contents/Info.plist`에서 `CFBundleExecutable` 키 추출.

### 기본 화이트리스트 (감시 제외)

```python
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
}
```

### config.json 구조

```json
{
  "whitelist": ["Finder", "Safari", ...],
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

앱 목록은 config.json에 저장하지 않고 매 실행 시 재스캔. 화이트리스트만 저장.

### 설정 창 UI

`AppRow` 토글 의미 반전:
- **ON (초록)** = 화이트리스트 (감시 제외)
- **OFF (회색)** = 감시 대상

---

## 단일 인스턴스 + Headless 시작

### PID 파일 방식

```python
PID_FILE = os.path.expanduser("~/.aimguard.pid")

def ensure_single_instance():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(0.5)
        except (ProcessLookupError, ValueError):
            pass
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
```

### 시작 흐름

```
python3 main.py 실행
    ↓
ensure_single_instance()        # 기존 인스턴스 kill
    ↓
QApplication 생성
    ↓
MainWindow 생성 (show() 호출 안 함)
    ↓
scan_installed_apps() → 화이트리스트 필터링 → 모니터링 즉시 시작
    ↓
트레이 아이콘 표시 ("AimGuard 실행 중 🎯" 알림)
    ↓
[대기] 앱 감지 시에만 게임 창 popup
```

### 트레이 메뉴

```
[AimGuard 🎯]
├── 설정 열기    → MainWindow.show()
├── ────────────
└── 종료         → cleanup_pid() + QApplication.quit()
```

---

## 데이터 흐름

```
시작
    → scan_installed_apps()
    → 화이트리스트 필터링
    → ProcessMonitor.set_locked_apps(filtered_apps)
    → ProcessMonitor.start()

앱 감지
    → process_detected 시그널
    → 랜덤 게임 선택
    → MainWindow.showNormal() + 게임 위젯 표시

게임 성공
    → 앱 실행 허용
    → MainWindow.hide()

게임 실패/포기
    → MainWindow.hide()
```
