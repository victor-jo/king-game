# PyQt Motion PoC

PyQt5 + MediaPipe + PyAudio를 활용한 실시간 운동 카운터 및 오디오 데시벨 측정 PoC 모음입니다.

## 개요

카메라 영상에서 신체 관절 각도를 분석해 운동 횟수를 자동 카운트하고, 마이크로 주변 소음을 실시간 측정합니다. 4개의 파일은 각각 완전히 독립적으로 동작합니다.

| 파일 | 기능 | 측정 관절 |
|------|------|-----------|
| `squat_poc.py` | 스쿼트 카운터 | 엉덩이 – 무릎 – 발목 |
| `pushup_poc.py` | 팔굽혀펴기 카운터 | 어깨 – 팔꿈치 – 손목 |
| `situp_poc.py` | 윗몸일으키기 카운터 | 어깨 – 골반 – 무릎 |
| `audio_decibel_poc.py` | 오디오 데시벨 측정 | VU 미터 (0–100) |

## 아키텍처

```
MainWindow (UI 스레드)
  ├── VideoThread (QThread)          ← 운동 PoC
  │     ├── cv2.VideoCapture         카메라 프레임 캡처
  │     ├── MediaPipe PoseLandmarker 포즈 추정 (Tasks API)
  │     ├── calculate_angle()        관절 각도 계산
  │     └── pyqtSignal               frame_ready / rep_updated / state_changed / angle_updated
  │
  └── AudioThread (QThread)          ← 오디오 PoC
        ├── PyAudio                  마이크 PCM 입력
        ├── RMS → dBFS 변환          int16 / 32768.0 정규화
        └── pyqtSignal               db_ready
```

**핵심 패턴:** `QThread + pyqtSignal` — 영상·오디오 처리는 별도 스레드에서 수행하고, UI 업데이트는 시그널로 메인 스레드에 전달해 UI 블로킹을 방지합니다.

## 운동 감지 로직

세 관절 좌표로 각도를 계산한 뒤 임계값 기반 상태 머신으로 횟수를 카운트합니다.

```python
def calculate_angle(a, b, c):
    # b가 꼭짓점, arctan2로 0~180° 범위 계산
    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
    angle = abs(np.degrees(radians))
    return 360 - angle if angle > 180 else angle
```

| 운동 | DOWN 조건 | UP 조건 | 초기 상태 |
|------|-----------|---------|-----------|
| 스쿼트 | 각도 < 90° | 각도 > 160° | UP |
| 팔굽혀펴기 | 각도 < 90° | 각도 > 160° | UP |
| 윗몸일으키기 | 각도 > 120° (누운 상태) | 각도 < 60° (일어난 상태) | DOWN |

카운트는 `DOWN → UP` 전환 시점에만 증가하며, 상태 변경 시에만 시그널을 emit합니다 (매 프레임 emit 방지).

## 오디오 측정 로직

```python
# int16 PCM → dBFS 변환
samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
rms = math.sqrt(np.mean(samples ** 2))
db  = 20 * math.log10(rms + 1e-9)          # dBFS (-60 ~ 0)
db_normalized = clip((db + 60) / 60 * 100, 0, 100)  # 0~100 정규화
```

`/ 32768.0` 정규화 없이 int16 raw 값으로 계산하면 조용한 환경에서도 100이 나옵니다. float 정규화 후 dBFS 기준을 적용해야 실제 조용한 환경 ≈ 15–20, 대화 ≈ 50, 큰 소리 ≈ 80+ 이 됩니다.

## 카메라 선택 (macOS)

macOS AVFoundation으로 카메라 이름을 조회하고, Continuity Camera(iPhone)를 포함한 모든 카메라를 HUD 드롭다운에서 선택할 수 있습니다.

```python
# OpenCV는 외부(Continuity) 카메라를 먼저 열거
# AVFoundation modelID로 iPhone vs 내장 카메라를 구분해 순서 정렬
external = [d for d in av_devices if "iPhone" in (d.modelID() or "")]
internal = [d for d in av_devices if "iPhone" not in (d.modelID() or "")]
ordered  = external + internal   # OpenCV 인덱스 순서와 일치
```

기본값은 MacBook 내장 카메라(`MacBook`, `FaceTime`, `Built-in` 키워드 기준)로 자동 설정됩니다.

## 요구사항

- Python 3.13+
- macOS (AVFoundation 카메라 이름 조회, Continuity Camera 지원)
- PortAudio (`brew install portaudio` 선행 필요)
- MediaPipe 모델 파일: `pose_landmarker_lite.task` (프로젝트 루트에 위치)

### 모델 파일 다운로드

```bash
curl -O https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

## 설치 및 실행

```bash
# 1. PortAudio 설치 (PyAudio 의존성)
brew install portaudio

# 2. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 3. 패키지 설치
pip install -r requirements.txt

# 4. 실행 (각 파일 독립 실행)
python squat_poc.py
python pushup_poc.py
python situp_poc.py
python audio_decibel_poc.py
```

## 의존성

```
PyQt5>=5.15
opencv-python>=4.8
mediapipe>=0.10
pyaudio>=0.2.13
numpy>=1.24
pyobjc-framework-AVFoundation>=10.0   # macOS only
```

## 주요 구현 노트

- **QImage 버퍼 경쟁 조건**: `QImage(frame.data, ...)` emit 전 반드시 `.copy()` 호출 — raw 버퍼가 Qt 렌더 전에 해제되는 것을 방지
- **MediaPipe Tasks API**: mediapipe 0.10.x에서 `mp.solutions` 제거됨 → `mp.tasks.vision.PoseLandmarker` + `RunningMode.VIDEO` 사용
- **랜드마크 그리기**: Drawing Utils 제거로 `cv2.line` / `cv2.circle`로 직접 오버레이
- **타임스탬프**: VIDEO 모드에서 프레임당 33ms 증가 (≈ 30fps 기준)
