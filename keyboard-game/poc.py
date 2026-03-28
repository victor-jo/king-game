"""PyQt 간단 타자 PoC

- 목표: 해커톤에서 빠르게 시연 가능한 최소 기능 PoC
- 동작: 타겟 문장을 보여주고, 입력량 기반으로 WPM과 정확도를 실시간 갱신
- 주의: IME(한글 입력)는 OS에 의해 처리됩니다. 중간 조합(미확정 자모)을 별도 처리하려면 추가 구현 필요
"""
import sys
import time
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
)
from PyQt6.QtCore import QTimer, Qt


class TypingPoC(QWidget):
    """
    타자 연습용 메인 윈도우 위젯 클래스
    
    화면에 실시간으로 타자 속도(타수), 평균 타수, 정확도를 표시합니다.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyKeyboard PoC - PyQt 타자 연습")
        
        import random
        # 문장과 저자를 분리하여 튜플 형태로 저장 (총 20개 명언 세트)
        self.quotes = [
            ("삶이 있는 한 희망은 있다", "키케로"),
            ("산다는 것 그것은 치열한 전투이다", "로맹 롤랑"),
            ("하루에 3시간을 걸으면 7년 후에 지구를 한 바퀴 돌 수 있다", "새뮤얼 존슨"),
            ("언제나 현재에 집중할 수 있다면 행복할 것이다", "파울로 코엘료"),
            ("피할 수 없으면 즐겨라", "로버트 엘리엇"),
            ("내일은 내일의 태양이 뜬다", "마거릿 미첼"),
            ("행복은 습관이다, 그것을 몸에 지니라", "엘버트 허버드"),
            ("단순하게 살아라. 현대인은 쓸데없는 절차와 일 때문에 얼마나 복잡한 삶을 살아가는가?", "이디스 워튼"),
            ("먼저 자신을 비웃어라. 다른 사람이 당신을 비웃기 전에", "엘사 맥스웰"),
            ("우리를 향해 열린 문을 보지 못하게 된다", "헬렌 켈러"),
            ("자신감 있는 표정을 지으면 자신감이 생긴다", "찰스 다윈"),
            ("실패는 잊어라. 그러나 그것이 준 교훈은 절대 잊지 마라", "허버트 개서"),
            ("1퍼센트의 가능성, 그것이 나의 길이다", "나폴레옹"),
            ("꿈을 계속 간직하고 있으면 반드시 실현할 때가 온다", "괴테"),
            ("고통이 남기고 간 뒤를 보라. 고난이 지나면 반드시 기쁨이 스며든다", "괴테"),
            ("마음만을 가지고 있어서는 안 된다. 반드시 실천하여야 한다", "이소룡"),
            ("가장 큰 실수는 포기해 버리는 것이다", "조 지라드"),
            ("성공의 비결은 단 한 가지, 잘할 수 있는 일에 광적으로 집중하는 것이다", "톰 모나한"),
            ("문제점을 찾지 말고 해결책을 찾으라", "헨리 포드"),
            ("길을 잃는다는 것은 곧 길을 알게 된다는 것이다", "동아프리카 속담")
        ]
        random.shuffle(self.quotes)
        self.current_quote_idx = 0
        
        # 현재 화면에 표시되는 타겟 문장과 저자
        self.target = self.quotes[self.current_quote_idx][0]
        self.author = self.quotes[self.current_quote_idx][1]

        # 타이머 및 속도 측정을 위한 상태 변수
        self.started = False         # 타자 입력 시작 여부 플래그
        self.start_time = None       # 현재 문장 입력 시작 시각(초)
        self.elapsed = 0.0           # 현재 문장 입력에 소요된 시간(초)
        
        # 전체 세션 누적 정보를 위한 변수 (평균 타수 계산용)
        self.total_accumulated_strokes = 0
        self.total_accumulated_time = 0.0

        self.init_ui()
        self.reset_state()

        # GUI 타이머(0.25초마다 UI 패널 상태 갱신)
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(250)
        self.ui_timer.timeout.connect(self.update_stats)
        self.ui_timer.start()

    def init_ui(self):
        layout = QVBoxLayout()

        # 화면에는 문장과 저자를 줄바꿈하여 예쁘게 같이 보여줍니다
        self.label_target = QLabel(f"{self.target}\n- {self.author}")
        self.label_target.setWordWrap(True)
        # 폰트를 약간 키워서 시인성을 높입니다.
        font = self.label_target.font()
        font.setPointSize(12)
        font.setBold(True)
        self.label_target.setFont(font)
        
        layout.addWidget(QLabel("Target:"))
        layout.addWidget(self.label_target)

        layout.addWidget(QLabel("Type here :"))
        
        # 기본 QLineEdit를 사용해 OS IME에 완전히 맡김
        self.input_line = QLineEdit(self)
        self.input_line.textChanged.connect(self.on_text_changed)
        self.input_line.returnPressed.connect(self.on_enter_pressed)
        layout.addWidget(self.input_line)

        stats_layout = QHBoxLayout()
        self.label_time = QLabel("Time: 0.0s")
        self.label_wpm = QLabel("현재 타수: 0타/분")
        self.label_avg_wpm = QLabel("평균 타수: -타/분")
        self.label_acc = QLabel("Accuracy: 100%")
        stats_layout.addWidget(self.label_time)
        stats_layout.addWidget(self.label_wpm)
        stats_layout.addWidget(self.label_avg_wpm)
        stats_layout.addWidget(self.label_acc)
        layout.addLayout(stats_layout)

        # 시작, 리셋 버튼 제거됨 (엔터 입력으로 자동 진행되도록 변경됨)
        
        self.setLayout(layout)

    def reset_state(self):
        """
        현재 문장의 입력 상태를 초기화합니다. 
        문장이 넘어가거나 처음 진입 시 호출됩니다.
        """
        self.started = False
        self.start_time = None
        self.elapsed = 0.0
        self.last_text = ""
        self.correct_chars = 0
        self.total_keystrokes = 0
        self.finished = False
        self.input_line.setText("")
        self.update_stats()

    def start(self):
        """
        사용자가 텍스트 입력을 처음 시작했을 때 호출되어 
        문장 입력 소요 시간(start_time)을 측정하기 시작합니다.
        """
        if not self.started:
            self.started = True
            self.start_time = time.time()

    def go_to_next_quote(self):
        """
        다음 명언(리스트 내)으로 이동하며 
        UI 갱신 후 입력 상태를 초기화합니다.
        """
        self.current_quote_idx = (self.current_quote_idx + 1) % len(self.quotes)
        self.target = self.quotes[self.current_quote_idx][0]
        self.author = self.quotes[self.current_quote_idx][1]
        self.label_target.setText(f"{self.target}\n- {self.author}")
        self.reset_state()
        self.input_line.setFocus()

    def on_text_changed(self, text: str):
        """
        라인에딧 내용 변경 시 타이머를 시작하고 통계를 갱신합니다.
        """
        # 타이머 시작
        if not self.started and text:
            self.start()

        # UI 즉시 갱신 (Enter 전에도 시각적 업데이트만 수행)
        self.update_stats()

    def _calculate_correct_strokes(self, text: str) -> int:
        """
        주어진 입력과 정답(target)을 비교해, 일치하는 글자들의 타수를 누적 산출합니다.
        한글은 조합에 따라 2~3타, 이외 (띄어쓰기/구두점/영문)는 1타로 계산합니다.
        """
        strokes = 0
        for i, c in enumerate(text):
            if i < len(self.target) and c == self.target[i]:
                if 0xAC00 <= ord(c) <= 0xD7A3:  # 한글 완성형 영억 확인
                    # 종성이 있는지 없는지에 따라 타수를 나눔 (초성/중성 2타 + 종성 1타 = 3타)
                    strokes += 3 if (ord(c) - 0xAC00) % 28 > 0 else 2
                else:
                    strokes += 1
        return strokes

    def on_enter_pressed(self):
        """
        라인에딧에서 Enter 입력 시:
        1. 현재까지의 입력된 문장 타수와 시간을 누적 스코어에 반영합니다.
        2. 그 다음 다음 명언으로 넘어가고 화면을 플러시합니다(초기화).
        """
        if self.started:
            current_text = self.input_line.text()
            correct_strokes = self._calculate_correct_strokes(current_text)
            self.total_accumulated_strokes += correct_strokes
            
            # 마지막 업데이트를 위한 시간 계산 (누적 시간에 더함)
            if self.start_time is not None:
                self.elapsed = time.time() - self.start_time
            self.total_accumulated_time += self.elapsed
            
        self.go_to_next_quote()

    def update_stats(self):
        """
        타이머(QTimer)나 입력 이벤트에 의해 호출되며, 매 순간 통계 현황(Time, CPM, Accuracy)을 업데이트합니다.
        평균 타수는 누적분+현재 진행분을 합쳐 계산합니다.
        """
        # 진행 중인 상황의 현재 경과 시간 계산
        if self.started and not self.finished and self.start_time is not None:
            self.elapsed = time.time() - self.start_time

        self.label_time.setText(f"Time: {self.elapsed:.1f}s")

        current_text = self.input_line.text()
        
        # 타수(CPM) 계산
        correct_strokes = self._calculate_correct_strokes(current_text)
        
        # 맞게 친 글자 수 계산 (정확도용 퍼센티지 산정)
        correct_cnt = sum(1 for i, c in enumerate(current_text) if i < len(self.target) and c == self.target[i])

        # 분 단위로 걸린 시간 변환
        minutes = max(self.elapsed / 60.0, 1e-6)
        cpm = correct_strokes / minutes
        self.label_wpm.setText(f"현재 타수: {cpm:.0f}타/분")

        # 평균 타수 갱신 (전체 세션에서 누적된 전체 타수 및 완료 시간 + 현재 진행중인 데이터 포함)
        total_strokes = self.total_accumulated_strokes + correct_strokes
        total_time = self.total_accumulated_time + self.elapsed
        
        if total_time > 0:
            avg_minutes = max(total_time / 60.0, 1e-6)
            avg_cpm = total_strokes / avg_minutes
            self.label_avg_wpm.setText(f"평균 타수: {avg_cpm:.0f}타/분")
        else:
            self.label_avg_wpm.setText("평균 타수: -타/분")

        # 실시간 정확도: 현재 사용자가 입력한 총 길이 대비 정답과 일치하는 글자 수
        acc = 100.0
        if len(current_text) > 0:
            acc = (correct_cnt / len(current_text)) * 100.0
        self.label_acc.setText(f"Accuracy: {acc:.1f}%")

def main():
    app = QApplication(sys.argv)
    w = TypingPoC()
    w.resize(700, 200)
    w.show()
    # PyQt6 uses exec()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
