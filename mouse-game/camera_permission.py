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

    단일 동시 호출 안전: request_access._refs가 이전 호출 참조를 덮어씀.
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
