# PyKeyboard PoC (PyQt 기반 한국어 타자 PoC)

간단한 PoC 프로젝트입니다. 해커톤 회의에서 빠르게 시연할 수 있도록 최소한의 기능을 제공합니다.

주요 기능

- 타겟 문장 표시
- 입력창(IME 사용 가능)
- 실시간 WPM(분당 타수, Correct chars 기준) 및 정확도(정답 대비) 표시
- 시작/리셋 버튼

요구 사항

- Windows
- Python 3.8+
- PowerShell 사용(아래 명령 예시는 PowerShell 기준입니다)

설치

1. 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. 의존성 설치

```powershell
pip install -r requirements.txt
```

참고: `requirements.txt`는 기본적으로 `PyQt6`를 가리킵니다. PyQt6 대신 PyQt5를 쓰고 싶으면 `requirements.txt`를 수정하세요.

실행

```powershell
python poc.py
```

간단 사용법

- 앱을 실행하고 `Start`를 누르거나 입력을 시작하면 측정이 시작됩니다.
- 목표 문장을 입력하면 WPM과 정확도가 실시간으로 갱신됩니다.
- `Reset`으로 상태를 초기화할 수 있습니다.

향후 작업(권장)

- 자모(조합) 엔진 통합: 현재는 OS IME로 입력되는 완성형 한글을 처리합니다. 직접 자모를 수집해 조합하려면 `jamo` 등 라이브러리나 자체 조합 로직을 연결하세요.
- IME 레벨 이벤트 처리: 중간 조합 상태(미확정 자모)를 UI에 표시하도록 개선
- 유닛 테스트 추가: 조합 엔진, 통계 계산 로직 단위 테스트
- 통계 고도화: 히트맵, 오타 분류, 사용자별 학습

라이선스

MIT
