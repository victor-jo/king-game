"""AimGuard — 에임 게임 기반 앱 잠금 프로그램"""

import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AimGuard")
    app.setQuitOnLastWindowClosed(False)  # 트레이 모드에서도 유지

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
