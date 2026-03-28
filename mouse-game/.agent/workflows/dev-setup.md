---
description: 개발 환경 초기 세팅 방법 (가상환경 + 의존성 설치)
---

# 개발 환경 세팅

// turbo-all

1. 가상환경 생성
```bash
cd /Users/sj/workspace/playground/king-game/mouse-game && python3 -m venv .venv
```

2. 가상환경 활성화
```bash
source /Users/sj/workspace/playground/king-game/mouse-game/.venv/bin/activate
```

3. 의존성 설치
```bash
pip install -r /Users/sj/workspace/playground/king-game/mouse-game/requirements.txt
```

4. 설치 확인
```bash
python -c "from PySide6.QtWidgets import QApplication; import PySide6; print(f'PySide6 {PySide6.__version__} 설치 완료!')"
```
