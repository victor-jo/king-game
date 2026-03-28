---
name: PySide6 개발 가이드
description: PySide6 앱 개발 시 참고할 핵심 패턴과 컨벤션
---

# PySide6 개발 가이드

## 프로젝트 구조

```
pyqt-poc/
├── .agent/
│   ├── skills/          # 스킬 (개발 가이드, 패턴)
│   └── workflows/       # 워크플로우 (실행, 빌드 등)
├── docs/
│   └── spec.md          # 프로그램 명세서
├── venv/                # 가상환경 (git 제외)
├── main.py              # 앱 진입점
└── requirements.txt     # 의존성 목록
```

## 핵심 개념

### 1. 앱 구조
```python
import sys
from PySide6.QtWidgets import QApplication, QMainWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("앱 이름")
        # UI 구성...

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

### 2. 시그널-슬롯 (이벤트 처리)
```python
# 버튼 클릭 → 함수 연결
button.clicked.connect(self.on_button_click)

# 커스텀 시그널
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    my_signal = Signal(str)  # str 타입 데이터를 전달하는 시그널

    def emit_signal(self):
        self.my_signal.emit("hello")
```

### 3. 레이아웃
```python
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QGridLayout

# 세로 배치
layout = QVBoxLayout()
layout.addWidget(widget1)
layout.addWidget(widget2)

# 가로 배치
layout = QHBoxLayout()

# 그리드 배치
layout = QGridLayout()
layout.addWidget(widget, row, col)
```

### 4. 스타일링 (CSS 유사)
```python
widget.setStyleSheet("""
    QWidget {
        background-color: #FAFAFA;
        color: #333;
        font-size: 14px;
        border-radius: 8px;
    }
    QPushButton:hover {
        background-color: #1976D2;
    }
""")
```

### 5. 주요 위젯

| 위젯 | 용도 |
|------|------|
| `QLabel` | 텍스트/이미지 표시 |
| `QPushButton` | 클릭 버튼 |
| `QLineEdit` | 한 줄 텍스트 입력 |
| `QTextEdit` | 여러 줄 텍스트 입력 |
| `QComboBox` | 드롭다운 선택 |
| `QCheckBox` | 체크박스 |
| `QRadioButton` | 라디오 버튼 |
| `QSlider` | 슬라이더 |
| `QProgressBar` | 진행 바 |
| `QTableWidget` | 테이블 |
| `QListWidget` | 리스트 |
| `QTreeWidget` | 트리 구조 |
| `QTabWidget` | 탭 |
| `QMenuBar` | 메뉴바 |
| `QToolBar` | 툴바 |
| `QStatusBar` | 상태바 |
| `QDialog` | 대화상자 |
| `QFileDialog` | 파일 선택 대화상자 |
| `QMessageBox` | 메시지 박스 |

## 개발 환경

- **Python**: 3.14+
- **PySide6**: 6.10+
- **가상환경**: `venv/`
- **실행**: `source venv/bin/activate && python main.py`
