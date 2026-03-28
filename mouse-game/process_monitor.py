"""프로세스 감시 스레드 모듈"""

import psutil
from PySide6.QtCore import QThread, Signal


class ProcessMonitor(QThread):
    """백그라운드에서 프로세스를 감시하는 스레드

    감시 시작 시 이미 실행 중인 프로세스를 기록(스냅샷)하고,
    이후 새로 실행된 프로세스만 감지한다.
    게임 성공 후 실행된 프로세스는 종료될 때까지 쿨다운 유지.
    """

    # 감지 시그널: (프로그램 이름, 프로그램 경로)
    process_detected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._locked_apps = []
        self._cooldown = set()       # 감지 후 게임 진행 중인 프로세스
        self._allowed = set()        # 게임 성공으로 실행 허용된 프로세스 (종료 전까지 재감지 안 함)
        self._existing_processes = set()  # 감시 시작 시 이미 실행 중이던 프로세스

    def set_locked_apps(self, apps: list):
        """감시할 잠금 앱 목록 설정 + 현재 실행 중인 프로세스 스냅샷"""
        self._locked_apps = apps
        self._cooldown.clear()
        self._allowed.clear()

        # 현재 실행 중인 프로세스 스냅샷
        locked_names = {app["process_name"] for app in apps}
        self._existing_processes = set()
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name in locked_names:
                    self._existing_processes.add(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def mark_allowed(self, process_name: str):
        """게임 성공 후 프로세스를 허용 목록에 추가 (종료될 때까지 재감지 안 함)"""
        self._cooldown.discard(process_name)
        self._allowed.add(process_name)

    def clear_cooldown(self, process_name: str):
        """특정 프로세스의 쿨다운 해제 (게임 포기 시)"""
        self._cooldown.discard(process_name)
        self._existing_processes.discard(process_name)

    def run(self):
        """스레드 메인 루프"""
        self._running = True

        while self._running:
            if self._locked_apps:
                self._check_allowed_exits()
                self._check_processes()
            self.msleep(1000)

    def stop(self):
        """감시 중지"""
        self._running = False
        if self.isRunning():
            self.wait(3000)

    def _check_allowed_exits(self):
        """허용된 프로세스가 종료되었는지 확인 → 종료됐으면 다시 감지 대상"""
        if not self._allowed:
            return

        running_names = set()
        for proc in psutil.process_iter(["name"]):
            try:
                running_names.add(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # 허용 목록 중 더 이상 실행되지 않는 프로세스 → 제거 (다시 감지 가능)
        exited = self._allowed - running_names
        self._allowed -= exited

    def _check_processes(self):
        """새로 실행된 프로세스만 확인"""
        locked_names = {app["process_name"] for app in self._locked_apps}

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc_name = proc.info["name"]
                if proc_name not in locked_names:
                    continue
                if proc_name in self._existing_processes:
                    continue
                if proc_name in self._allowed:
                    continue

                if proc_name in self._cooldown:
                    # 게임 진행 중 재실행 시도 → 새 게임 없이 강제 종료만
                    self._kill_process(proc_name)
                    continue

                # 새로 실행된 프로세스 감지!
                self._cooldown.add(proc_name)

                app_info = next(
                    (a for a in self._locked_apps if a["process_name"] == proc_name),
                    None,
                )
                if app_info:
                    self._kill_process(proc_name)
                    self.process_detected.emit(app_info["name"], app_info["path"])
                break

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _kill_process(self, process_name: str):
        """특정 이름의 프로세스를 모두 종료"""
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["name"] == process_name:
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

