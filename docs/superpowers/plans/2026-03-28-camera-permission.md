# macOS 카메라 권한 요청 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** macOS 15 Sequoia에서 번들 앱(AimGuard.app) 실행 시 카메라 권한 다이얼로그를 올바르게 표시해 모션 게임이 정상 작동하도록 한다.

**Architecture:** `camera_permission.py` 신규 유틸리티 모듈을 생성해 ctypes + Objective-C 런타임으로 `[AVCaptureDevice requestAccessForMediaType:completionHandler:]`를 호출. `motion_game.py`의 `start_game()` 첫 줄에서 `ensure_camera_permission()`을 호출하여 권한 확인 → 거부 시 `game_quit` emit, 승인 시 기존 카메라 probe 진행.

**Tech Stack:** Python 3.13, ctypes, AVFoundation (macOS system framework), PySide6 QEventLoop, py2app

**알려진 제약:**
- `_get_available_cameras()`(motion_game.py:100)는 `from AVFoundation import ...`(pyobjc) 임포트를 시도하지만 번들에 pyobjc가 없으므로 항상 `except` 분기(cv2 probe 폴백)로 실행됨. 카메라 이름 표시가 소스 환경(pyobjc 설치 시)과 번들 환경에서 다를 수 있으나 게임 동작에는 무관.
- `_request_access._refs`를 이용한 GC 보호는 단일 동시 호출만 안전함 (게임 시작 시 1회 호출 패턴에서는 문제 없음).

---

## Chunk 1: camera_permission.py 구현 (TDD)

### Task 1: 테스트 파일 먼저 작성

**Files:**
- Create: `mouse-game/tests/test_camera_permission.py`

- [ ] **Step 1: 테스트 파일 작성**

```python
# mouse-game/tests/test_camera_permission.py
"""camera_permission 유틸리티 단위 테스트."""
import sys
import unittest
from unittest.mock import patch, MagicMock


class TestGetStatus(unittest.TestCase):
    def test_non_macos_returns_authorized(self):
        """비-macOS 플랫폼에서는 AUTHORIZED(3) 반환."""
        with patch.object(sys, 'platform', 'win32'):
            import importlib, camera_permission
            importlib.reload(camera_permission)
            self.assertEqual(camera_permission.get_status(), 3)

    def test_ctypes_failure_returns_authorized(self):
        """ctypes 로드 실패 시 AUTHORIZED(3) 반환 (폴백)."""
        with patch('camera_permission._load_objc', return_value=None):
            import camera_permission
            self.assertEqual(camera_permission.get_status(), 3)


class TestEnsureCameraPermission(unittest.TestCase):
    def test_non_macos_returns_true(self):
        """비-macOS에서는 True 반환."""
        with patch.object(sys, 'platform', 'win32'):
            import importlib, camera_permission
            importlib.reload(camera_permission)
            self.assertTrue(camera_permission.ensure_camera_permission())

    def test_authorized_returns_true_without_request(self):
        """이미 authorized(3)이면 request_access 호출 없이 True 반환."""
        with patch('camera_permission.get_status', return_value=3), \
             patch('camera_permission.request_access') as mock_req:
            import camera_permission
            result = camera_permission.ensure_camera_permission()
            self.assertTrue(result)
            mock_req.assert_not_called()

    def test_denied_returns_false_without_request(self):
        """denied(2)이면 request_access 호출 없이 False 반환."""
        with patch('camera_permission.get_status', return_value=2), \
             patch('camera_permission.request_access') as mock_req:
            import camera_permission
            result = camera_permission.ensure_camera_permission()
            self.assertFalse(result)
            mock_req.assert_not_called()

    def test_restricted_returns_false_without_request(self):
        """restricted(1)이면 False 반환."""
        with patch('camera_permission.get_status', return_value=1):
            import camera_permission
            self.assertFalse(camera_permission.ensure_camera_permission())

    def test_ctypes_failure_in_ensure_returns_true(self):
        """ensure_camera_permission 내부 ctypes 실패 시 True 반환 (폴백)."""
        with patch('camera_permission.get_status', side_effect=Exception("ctypes fail")):
            import camera_permission
            result = camera_permission.ensure_camera_permission()
            self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인 (camera_permission 미존재)**

```bash
cd mouse-game
python3 -m pytest tests/test_camera_permission.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'camera_permission'`

---

### Task 2: `camera_permission.py` 구현

**Files:**
- Create: `mouse-game/camera_permission.py`

- [ ] **Step 1: `camera_permission.py` 작성**

```python
# mouse-game/camera_permission.py
"""macOS AVFoundation 카메라 권한 요청 유틸리티.

번들 앱(py2app)에서 macOS 15 Sequoia 이상의 TCC 정책에 맞게
카메라 권한 다이얼로그를 명시적으로 표시한다.
비-macOS 플랫폼 또는 ctypes 실패 시 True를 반환한다 (폴백).

단일 동시 호출 가정: ensure_camera_permission()은 게임 시작 시
1회만 호출된다. 동시에 여러 번 호출하면 _request_access._refs가
덮어씌워져 이전 콜백이 GC 수집될 수 있다.
"""

import sys
import ctypes
import ctypes.util
from typing import Callable


# ── AVAuthorizationStatus 상수 ────────────────────────────────────
NOT_DETERMINED = 0
RESTRICTED     = 1
DENIED         = 2
AUTHORIZED     = 3


# ── ObjC Block ABI 구조체 ─────────────────────────────────────────
class _BlockDescriptor(ctypes.Structure):
    _fields_ = [
        ("reserved", ctypes.c_ulong),
        ("size",     ctypes.c_ulong),
    ]


class _BlockLiteral(ctypes.Structure):
    _fields_ = [
        ("isa",        ctypes.c_void_p),
        ("flags",      ctypes.c_int),
        ("reserved",   ctypes.c_int),
        ("invoke",     ctypes.c_void_p),
        ("descriptor", ctypes.POINTER(_BlockDescriptor)),
    ]


_BLOCK_HAS_DESCRIPTOR = 1 << 25

# CFUNCTYPE: void (^)(id _block_self, BOOL granted)
_CompletionFuncType = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_bool)


def _load_objc():
    """libobjc + AVFoundation 로드. 실패 시 None 반환."""
    try:
        libobjc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/AVFoundation.framework/AVFoundation"
        )
        libobjc.objc_getClass.restype       = ctypes.c_void_p
        libobjc.objc_getClass.argtypes      = [ctypes.c_char_p]
        libobjc.sel_registerName.restype    = ctypes.c_void_p
        libobjc.sel_registerName.argtypes   = [ctypes.c_char_p]
        return libobjc
    except Exception:
        return None


def _make_media_type_string(libobjc) -> ctypes.c_void_p:
    """NSString "vide" (AVMediaTypeVideo) 반환.

    objc_msgSend argtypes를 이 함수 내에서 재설정하므로
    호출 후 반드시 argtypes를 재설정해야 한다.
    """
    NSString = libobjc.objc_getClass(b"NSString")
    sel = libobjc.sel_registerName(b"stringWithUTF8String:")

    libobjc.objc_msgSend.restype  = ctypes.c_void_p
    libobjc.objc_msgSend.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p
    ]
    return libobjc.objc_msgSend(NSString, sel, b"vide")


def get_status() -> int:
    """현재 카메라 권한 상태 반환.

    Returns:
        0 = notDetermined, 1 = restricted, 2 = denied, 3 = authorized
        ctypes 실패 시 AUTHORIZED(3) 반환 (폴백)
    """
    if sys.platform != "darwin":
        return AUTHORIZED

    libobjc = _load_objc()
    if libobjc is None:
        return AUTHORIZED

    try:
        AVCaptureDevice = libobjc.objc_getClass(b"AVCaptureDevice")
        sel = libobjc.sel_registerName(b"authorizationStatusForMediaType:")
        media_type = _make_media_type_string(libobjc)

        # argtypes 재설정 (authorizationStatusForMediaType: 시그니처)
        libobjc.objc_msgSend.restype  = ctypes.c_long
        libobjc.objc_msgSend.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        return int(libobjc.objc_msgSend(AVCaptureDevice, sel, media_type))
    except Exception:
        return AUTHORIZED


def request_access(callback: Callable[[bool], None]) -> None:
    """[AVCaptureDevice requestAccessForMediaType:completionHandler:] 호출.

    완료 시 callback(granted: bool) 호출.
    ctypes 실패 시 callback(True) 즉시 호출 (폴백).

    단일 동시 호출 안전: _request_access._refs가 이전 호출 참조를 덮어씀.
    """
    libobjc = _load_objc()
    if libobjc is None:
        callback(True)
        return

    try:
        # ObjC Block 구조체 생성
        descriptor = _BlockDescriptor(0, ctypes.sizeof(_BlockLiteral))

        def _invoke(_block_self, granted: bool) -> None:
            callback(bool(granted))

        c_invoke = _CompletionFuncType(_invoke)

        block = _BlockLiteral()
        block.isa        = ctypes.cast(
            libobjc.objc_getClass(b"__NSConcreteGlobalBlock"),
            ctypes.c_void_p,
        )
        block.flags      = _BLOCK_HAS_DESCRIPTOR
        block.reserved   = 0
        block.invoke     = ctypes.cast(c_invoke, ctypes.c_void_p)
        block.descriptor = ctypes.pointer(descriptor)

        AVCaptureDevice = libobjc.objc_getClass(b"AVCaptureDevice")
        sel = libobjc.sel_registerName(b"requestAccessForMediaType:completionHandler:")
        media_type = _make_media_type_string(libobjc)

        # argtypes 재설정: requestAccessForMediaType:completionHandler: 시그니처
        libobjc.objc_msgSend.restype  = None
        libobjc.objc_msgSend.argtypes = [
            ctypes.c_void_p,  # self (AVCaptureDevice)
            ctypes.c_void_p,  # sel
            ctypes.c_void_p,  # mediaType (NSString)
            ctypes.c_void_p,  # completionHandler (Block pointer)
        ]

        # Block은 포인터(id)로 전달 — ctypes.cast로 명시적 변환
        libobjc.objc_msgSend(
            AVCaptureDevice, sel,
            media_type,
            ctypes.cast(ctypes.byref(block), ctypes.c_void_p),
        )

        # block, c_invoke, descriptor를 콜백 호출 전까지 GC에서 보호
        request_access._refs = (block, c_invoke, descriptor)

    except Exception:
        callback(True)


def ensure_camera_permission() -> bool:
    """카메라 권한 확인 및 필요 시 요청 (동기 블로킹).

    QEventLoop으로 비동기 응답 대기. 타임아웃 10초.
    - ctypes 예외 시: True 반환 (폴백 — 비-macOS 또는 로드 실패)
    - 타임아웃 시: False 반환 (스펙: 미응답 = 거부로 처리)

    Returns:
        True  = 권한 있음 (게임 진행 가능)
        False = 권한 없음 또는 거부 (game_quit 처리 필요)
    """
    if sys.platform != "darwin":
        return True

    try:
        status = get_status()
    except Exception:
        return True  # ctypes 완전 실패 시 폴백

    if status == AUTHORIZED:
        return True
    if status in (RESTRICTED, DENIED):
        return False

    # NOT_DETERMINED: 권한 요청
    from PySide6.QtCore import QEventLoop, QTimer

    loop   = QEventLoop()
    result = [False]  # 기본값 False — 타임아웃 포함 미응답 = 거부로 처리

    def _on_result(granted: bool) -> None:
        result[0] = granted
        loop.quit()

    request_access(_on_result)

    # 타임아웃 10초
    guard = QTimer()
    guard.setSingleShot(True)
    guard.setInterval(10_000)
    guard.timeout.connect(loop.quit)
    guard.start()

    loop.exec()
    guard.stop()

    return result[0]
```

- [ ] **Step 2: 테스트 실행 — PASS 확인**

```bash
cd mouse-game
python3 -m pytest tests/test_camera_permission.py -v
```

Expected:
```
PASSED tests/test_camera_permission.py::TestGetStatus::test_non_macos_returns_authorized
PASSED tests/test_camera_permission.py::TestGetStatus::test_ctypes_failure_returns_authorized
PASSED tests/test_camera_permission.py::TestEnsureCameraPermission::test_non_macos_returns_true
PASSED tests/test_camera_permission.py::TestEnsureCameraPermission::test_authorized_returns_true_without_request
PASSED tests/test_camera_permission.py::TestEnsureCameraPermission::test_denied_returns_false_without_request
PASSED tests/test_camera_permission.py::TestEnsureCameraPermission::test_restricted_returns_false_without_request
PASSED tests/test_camera_permission.py::TestEnsureCameraPermission::test_ctypes_failure_in_ensure_returns_true
7 passed
```

- [ ] **Step 3: Commit**

```bash
cd /Users/wj.cho/dev/poc/king-game
git add mouse-game/camera_permission.py mouse-game/tests/test_camera_permission.py
git commit -m "feat(motion): camera_permission.py — ctypes AVFoundation 권한 요청 + 단위 테스트"
```

---

## Chunk 2: motion_game.py 통합 및 setup.py 수정

### Task 3: `motion_game.py` — `start_game()` 앞에 권한 확인 추가

**Files:**
- Modify: `mouse-game/motion_game.py` (start_game 메서드)

- [ ] **Step 1: `start_game()` 상단에 권한 확인 삽입**

`start_game()` 메서드 내 기존 `try:` 블록 앞에 다음을 추가:

```python
    def start_game(self, app_name: str, app_path: str):
        self.app_name = app_name
        self.app_path = app_path

        # macOS 카메라 권한 확인 — macOS 15에서 다이얼로그 미표시 문제 수정
        # ensure_camera_permission()은 notDetermined 시 QEventLoop으로 대기
        try:
            from camera_permission import ensure_camera_permission
            if not ensure_camera_permission():
                QTimer.singleShot(0, lambda: self.game_quit.emit())
                return
        except Exception:
            pass  # 임포트 실패 또는 비-macOS 환경 → 기존 로직으로 진행

        # 의존성/카메라/모델 파일 확인 (lazy)  ← 기존 코드 그대로 유지
        try:
            import cv2  # noqa: F401
            ...
```

- [ ] **Step 2: import 확인**

```bash
cd mouse-game
python3 -c "from motion_game import MotionGameWidget; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/wj.cho/dev/poc/king-game
git add mouse-game/motion_game.py
git commit -m "fix(motion): start_game()에 ensure_camera_permission() 추가 — macOS 15 TCC 대응"
```

---

### Task 4: `setup.py` — `camera_permission` includes 추가

**Files:**
- Modify: `mouse-game/setup.py`

- [ ] **Step 1: includes에 추가**

```python
    'includes': [
        'main_window', 'config', 'process_monitor',
        'aim_game', 'bug_game', 'keyboard_game', 'motion_game', 'audio_game', 'sounds',
        'sounddevice', '_sounddevice',
        'camera_permission',   # 추가
    ],
```

- [ ] **Step 2: Commit**

```bash
cd /Users/wj.cho/dev/poc/king-game
git add mouse-game/setup.py
git commit -m "feat(bundle): camera_permission 번들 includes 추가"
```

---

## Chunk 3: 번들 빌드 및 검증

### Task 5: 번들 빌드 및 카메라 권한 동작 확인

**Files:**
- `mouse-game/dist/AimGuard.app` (생성)

- [ ] **Step 1: 클린 빌드**

```bash
cd mouse-game
./build_app.sh 2>&1 | grep -E "^===|Done!|[0-9]+[MG].*AimGuard|[Ee]rror:"
```

Expected:
```
=== 1. 이전 빌드 삭제 ===
...
Done!
512M  dist/AimGuard.app
```

- [ ] **Step 2: 번들 내 camera_permission 포함 확인**

```bash
python3 -c "
import zipfile
z = zipfile.ZipFile('dist/AimGuard.app/Contents/Resources/lib/python313.zip')
found = [n for n in z.namelist() if 'camera_permission' in n]
print(found)
"
```

Expected: `['camera_permission.pyc']`

- [ ] **Step 3: 번들 앱 실행 — 카메라 권한 다이얼로그 확인**

```bash
open dist/AimGuard.app
```

Expected:
- 앱 트레이 아이콘 표시
- 모션 게임 선택 시 **"AimGuard가 카메라에 접근하려고 합니다"** 시스템 다이얼로그 표시
- 허용 후 카메라 피드 및 모션 인식 동작

- [ ] **Step 4: ad-hoc 서명 + tar.gz 생성**

```bash
cd dist
xattr -cr AimGuard.app
codesign --force --deep --sign - AimGuard.app
rm -f AimGuard-v1.0.0-macos.tar.gz
tar -czf AimGuard-v1.0.0-macos.tar.gz AimGuard.app
du -sh AimGuard-v1.0.0-macos.tar.gz
```

Expected: ~200M

- [ ] **Step 5: GitHub 릴리즈 업데이트**

```bash
cd /Users/wj.cho/dev/poc/king-game

gh release delete v1.0.0 --repo victor-jo/king-game --yes
git push origin :refs/tags/v1.0.0
git tag -d v1.0.0
git tag v1.0.0
git push origin v1.0.0

gh release create v1.0.0 \
  mouse-game/dist/AimGuard-v1.0.0-macos.tar.gz \
  --repo victor-jo/king-game \
  --title "AimGuard v1.0.0" \
  --notes "$(cat <<'NOTES'
## ⚠️ 중요 주의사항

> **앱을 실행하면 모든 시스템 앱을 제외한 프로세스가 종료됩니다.**

게임 클리어 전까지 실행 중인 앱이 강제 종료되오니, **작업 중인 내용을 반드시 저장한 후** 실행하세요.

---

## AimGuard v1.0.0

### 설치 방법 (curl)

\`\`\`bash
curl -L -o AimGuard-v1.0.0-macos.tar.gz \
  https://github.com/victor-jo/king-game/releases/download/v1.0.0/AimGuard-v1.0.0-macos.tar.gz

tar -xzf AimGuard-v1.0.0-macos.tar.gz
mv AimGuard.app /Applications/
open /Applications/AimGuard.app
\`\`\`

> **브라우저로 다운로드한 경우** "손상된 앱" 오류 시:
> \`\`\`bash
> xattr -rd com.apple.quarantine /Applications/AimGuard.app
> \`\`\`

### 포함 게임
- 🎯 에임 게임 / 🐛 벌레 게임 / ⌨️ 키보드 게임 / 🏋️ 모션 게임 / 🎤 소리 게임

### 시스템 요구사항
- macOS 12 이상 (macOS 15 Sequoia 검증 완료)
- 처음 실행 시 카메라 · 마이크 권한 허용 필요
NOTES
)"
```

- [ ] **Step 6: Push**

```bash
cd /Users/wj.cho/dev/poc/king-game
git push origin main
```
