# PyQt5 Motion + Audio PoC — Design Spec
Date: 2026-03-24

## Overview

PyQt5 기반 실시간 운동 인식(MediaPipe Pose) 및 오디오 데시벨 측정 PoC.
4개의 완전 독립 standalone 파일로 구성.

---

## File Structure

```
pyqt-motion/
├── requirements.txt
├── pushup_poc.py         # 팔굽혀펴기
├── situp_poc.py          # 윗몸일으키기
├── squat_poc.py          # 스쿼트
└── audio_decibel_poc.py  # 오디오 데시벨 VU 미터
```

각 파일은 `pip install -r requirements.txt` 후 `python <파일명>.py` 로 단독 실행 가능.

---

## Architecture Decision

- **Approach**: QThread + pyqtSignal
- **이유**: thread-safe, UI freeze 없음, Qt 이디엄에 맞음. 향후 컴포넌트 분리 시 경계가 명확.
- **파일 독립성**: 공통 모듈 없음. 코드 중복 허용 (PoC 목적).

---

## Exercise PoC — 공통 내부 구조

팔굽혀펴기 / 윗몸일으키기 / 스쿼트 3개 파일 동일 패턴.

### Classes

```
calculate_angle(a, b, c) → float
VideoThread(QThread)
  signals: frame_ready(QImage), rep_updated(int), state_changed(str), angle_updated(float)
  run(): OpenCV cap → MediaPipe Pose → 각도 계산 → state machine → emit
MainWindow(QMainWindow)
  widgets: 상단 HUD QLabel, 카메라 QLabel (전체 너비)
  slots: update_frame, update_rep, update_state, update_angle
main()
```

### UI Layout (B — 상단 HUD 바)

```
┌────────────────────────────────────────┐
│  횟수: 42   상태: DOWN   각도: 87°      │  ← 상단 HUD QLabel
├────────────────────────────────────────┤
│                                        │
│         웹캠 피드 (전체 너비)           │  ← QLabel (카메라)
│      MediaPipe 랜드마크 오버레이        │
│                                        │
└────────────────────────────────────────┘
```

---

## Exercise Detection Logic

### 각도 계산

```python
def calculate_angle(a, b, c):
    # b = 꼭짓점(측정 관절), a/c = 양 끝 관절
    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) \
            - np.arctan2(a[1]-b[1], a[0]-b[0])
    return abs(np.degrees(radians))
```

### 운동별 설정

| 운동 | 측정 관절 | DOWN 조건 | UP 조건 | 랜드마크 |
|------|-----------|-----------|---------|----------|
| 스쿼트 | 엉덩이-무릎-발목 | angle < 90° | angle > 160° | HIP→KNEE→ANKLE |
| 팔굽혀펴기 | 어깨-팔꿈치-손목 | angle < 90° | angle > 160° | SHOULDER→ELBOW→WRIST |
| 윗몸일으키기 | 어깨-골반-무릎 | angle < 60° | angle > 120° | SHOULDER→HIP→KNEE |

### State Machine

```
초기: stage = "UP"

if angle < DOWN_THRESHOLD:
    stage = "DOWN"

if angle > UP_THRESHOLD and stage == "DOWN":
    stage = "UP"
    count += 1
```

---

## Audio PoC — audio_decibel_poc.py

### Classes

```
AudioThread(QThread)
  signal: db_ready(float)  # 0.0 ~ 100.0
  run(): PyAudio → RMS → 20*log10 → normalize → emit

VUMeterWidget(QWidget)
  paintEvent(): QPainter로 수직 막대 그리기
  색상 구간: 0~60 녹색 / 60~80 노란색 / 80~100 빨간색

MainWindow(QMainWindow)
  widgets: QLCDNumber (dB 수치), VUMeterWidget
  slot: update_db
```

### 데시벨 계산

```python
rms = np.sqrt(np.mean(np.frombuffer(data, np.int16).astype(np.float32)**2))
db = 20 * np.log10(rms + 1e-9)
db_normalized = np.clip((db + 60) / 60 * 100, 0, 100)
```

### VU 미터 색상 구간

```
0 ────────── 60   60 ──── 80   80 ────────── 100
   녹색(안전)       노란색(주의)    빨간색(큰소리)
```

---

## Dependencies (requirements.txt)

```
PyQt5>=5.15
opencv-python>=4.8
mediapipe>=0.10
pyaudio>=0.2.13
numpy>=1.24
```
