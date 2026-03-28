"""AimGuard — Headless 앱 잠금 프로그램"""

import os
import sys
import signal
import time
import atexit
import logging

PID_FILE = os.path.expanduser("~/.aimguard.pid")


def write_pid(pid_file: str = PID_FILE):
    """현재 PID를 파일에 기록. 실패해도 경고만 출력하고 계속 실행."""
    try:
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
    except OSError as e:
        print(f"[AimGuard] 경고: PID 파일 쓰기 실패 ({pid_file}): {e}", file=sys.stderr)


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
        time.sleep(0.8)  # 종료 대기 (best-effort, 보장 안 됨)
    except (ProcessLookupError, PermissionError):
        pass  # 이미 종료됨
    except ValueError:
        pass  # pid 파일 손상


def _setup_signal_handlers(app):
    """SIGTERM/SIGINT/SIGHUP 수신 시 Qt 이벤트 루프를 정상 종료한다.

    Qt 이벤트 루프가 돌아가는 동안에는 Python signal handler가 즉시 실행되지
    않는다. 100 ms QTimer로 Python 인터프리터에 제어를 넘겨 시그널을 전달받는다.
    """
    from PySide6.QtCore import QTimer

    def _quit_app(signum, frame):
        sig_name = signal.Signals(signum).name
        logging.info("[AimGuard] 시그널 수신 (%s) → 종료", sig_name)
        app.quit()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _quit_app)

    # SIGHUP: macOS에서 터미널 세션 종료 시 전송
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _quit_app)

    # Qt 이벤트 루프 내에서 Python 시그널이 처리되도록 주기적으로 깨운다
    _wakeup_timer = QTimer()
    _wakeup_timer.setInterval(100)
    _wakeup_timer.timeout.connect(lambda: None)  # no-op; Python GIL 반환용
    _wakeup_timer.start()
    # 타이머가 GC되지 않도록 app에 붙여둔다
    app._signal_wakeup_timer = _wakeup_timer


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

    # 4. OS 시그널 핸들러 등록 (SIGTERM / SIGINT / SIGHUP)
    _setup_signal_handlers(app)

    window = MainWindow()
    # show() 호출하지 않음 — headless 시작

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
