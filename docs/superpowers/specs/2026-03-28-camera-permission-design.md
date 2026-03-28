# macOS 카메라 권한 요청 설계

**날짜**: 2026-03-28
**상태**: 승인됨
**대상 플랫폼**: macOS 15 Sequoia (하위 버전 호환)

---

## 문제 정의

번들 앱(AimGuard.app)에서 모션 게임이 랜덤 배정에서 완전히 제외됩니다.

**근본 원인**: macOS 15 Sequoia는 `AVCaptureSession.startRunning()`(OpenCV 내부 경로) 단독으로는 TCC 카메라 권한 다이얼로그를 표시하지 않습니다. `[AVCaptureDevice requestAccessForMediaType:completionHandler:]` API를 명시적으로 호출해야만 권한 다이얼로그가 표시됩니다.

**증상 체인**:
1. `start_game()` → `_get_available_cameras()` → `_probe_camera_silent(0)`
2. `cv2.VideoCapture(0)` 호출 시 권한 다이얼로그 미표시
3. `cap.isOpened()` = False → cameras = [] → `game_quit` 즉시 emit
4. 모션 게임이 랜덤 풀에서 항상 탈락

---

## 선택한 접근법

**Approach A: ctypes로 AVFoundation 명시적 권한 요청**

- 의존성 추가 없음 (pyobjc 불필요)
- macOS 10.14~15 전 버전 호환
- ctypes Objective-C 런타임 브리지 사용

---

## 아키텍처

### 파일 구성

| 파일 | 변경 | 내용 |
|------|------|------|
| `mouse-game/camera_permission.py` | 신규 | ctypes AVFoundation 권한 유틸리티 |
| `mouse-game/motion_game.py` | 수정 | `start_game()` 앞에 권한 확인 추가 |
| `mouse-game/setup.py` | 수정 | `camera_permission` includes에 추가 |

### 흐름

```
start_game() 호출
    │
    ▼
ensure_camera_permission()
    │
    ├─ authorized(3) ──────────────────► _get_available_cameras() → VideoThread 시작
    │
    ├─ notDetermined(0) ──► request_access(callback)
    │                           │
    │                       QEventLoop 대기 (사용자 응답)
    │                           │
    │                       granted=True ──► _get_available_cameras() → VideoThread 시작
    │                           │
    │                       granted=False ──► game_quit emit
    │
    └─ restricted/denied(1,2) ─────────► game_quit emit
```

---

## `camera_permission.py` 설계

### 공개 API

```python
def get_status() -> int:
    """현재 카메라 권한 상태 반환.

    Returns:
        0 = notDetermined (미결정)
        1 = restricted    (제한됨)
        2 = denied        (거부됨)
        3 = authorized    (허용됨)
    """

def request_access(callback: Callable[[bool], None]) -> None:
    """[AVCaptureDevice requestAccessForMediaType:completionHandler:] 호출.

    ObjC Block 구조체: __NSConcreteGlobalBlock ISA +
    BLOCK_HAS_DESCRIPTOR 플래그 + ctypes.CFUNCTYPE invoke 포인터.
    완료 시 callback(granted: bool) 호출.
    """

def ensure_camera_permission() -> bool:
    """카메라 권한 확인 및 필요 시 요청. 동기 블로킹 방식.

    QEventLoop으로 비동기 응답 대기.
    ctypes 예외 발생 시 True 반환 (비-macOS 플랫폼 폴백).

    Returns:
        True  = 권한 있음 (게임 진행 가능)
        False = 권한 없음 (game_quit 처리 필요)
    """
```

### ctypes ObjC Block 구현 패턴

```python
import ctypes, ctypes.util

# 프레임워크 로드
_libobjc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
ctypes.cdll.LoadLibrary('/System/Library/Frameworks/AVFoundation.framework/AVFoundation')

# Block 구조체 (ABI 표준)
class _BlockDescriptor(ctypes.Structure):
    _fields_ = [('reserved', ctypes.c_ulong), ('size', ctypes.c_ulong)]

class _BlockLiteral(ctypes.Structure):
    _fields_ = [
        ('isa', ctypes.c_void_p),
        ('flags', ctypes.c_int),
        ('reserved', ctypes.c_int),
        ('invoke', ctypes.c_void_p),
        ('descriptor', ctypes.POINTER(_BlockDescriptor)),
    ]

_BLOCK_HAS_DESCRIPTOR = 1 << 25

# CFUNCTYPE: void(^)(BOOL granted) — void block(id self, BOOL granted)
_CompletionHandler = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_bool)
```

### 에러 처리

- ctypes 로드 실패 → `True` 반환 (비-macOS 환경 폴백)
- QEventLoop 타임아웃 (10초) → `False` 반환 (권한 미응답 처리)
- `restricted/denied` → `False` 반환 즉시

---

## `motion_game.py` 변경

`start_game()` 진입 시 권한 확인:

```python
def start_game(self, app_name: str, app_path: str):
    self.app_name = app_name
    self.app_path = app_path

    # [추가] macOS 카메라 권한 확인
    from camera_permission import ensure_camera_permission
    if not ensure_camera_permission():
        QTimer.singleShot(0, lambda: self.game_quit.emit())
        return

    # 이하 기존 로직 유지 (try/except cv2 import 등)
    try:
        import cv2
        cameras = _get_available_cameras()
        ...
```

---

## `setup.py` 변경

```python
'includes': [
    ...,
    'camera_permission',  # 추가
],
```

---

## 검증 기준

1. 처음 실행 시 카메라 권한 다이얼로그 표시 (macOS 15)
2. 권한 허용 후 모션 게임이 정상 진행 (VideoThread 카메라 피드 표시)
3. 권한 거부 시 `game_quit` → 다른 게임으로 폴백
4. 번들 앱 크기 변화 없음 (pyobjc 추가 없음)
