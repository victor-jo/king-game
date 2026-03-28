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
