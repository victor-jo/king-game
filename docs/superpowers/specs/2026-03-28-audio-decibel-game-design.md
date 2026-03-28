# Audio Decibel Game — 설계 문서

**날짜**: 2026-03-28
**프로젝트**: AimGuard (king-game / mouse-game)
**상태**: 승인됨

---

## 1. 개요

마이크 입력 데시벨이 100 dB 이상을 **5초 연속 유지**하면 잠금 앱 실행이 허용되는 미니게임.
기존 4종(aim / bug / keyboard / motion) 랜덤 풀에 `"audio"` 타입으로 추가된다.

---

## 2. 아키텍처 & 파일 구조

```
mouse-game/
├── audio_game.py          ← 신규: AudioGameWidget + AudioThread
├── main_window.py         ← stack index 5 추가, 랜덤 풀에 "audio" 추가
├── config.py              ← 필드 2개 추가 (db_threshold, time_limit_audio)
└── requirements.txt       ← sounddevice 추가
```

### 스택 인덱스

| index | 위젯 |
|-------|------|
| 0 | 설정 화면 |
| 1 | aim_widget |
| 2 | bug_widget |
| 3 | keyboard_widget |
| 4 | motion_widget |
| **5** | **audio_widget** |

---

## 3. AudioThread (오디오 처리)

`QThread` 서브클래스. `sounddevice.InputStream` 콜백 방식으로 오디오 청크를 받아 RMS → dBFS → 표시 dB로 변환 후 Qt Signal 발행.

```python
class AudioThread(QThread):
    level_updated = Signal(float)   # 표시 dB 값 (0 ~ 110+)

    def _callback(self, indata, frames, time, status):
        rms = np.sqrt(np.mean(indata ** 2))
        dbfs = 20.0 * np.log10(max(rms, 1e-10))
        display_db = (dbfs + 60.0) * (110.0 / 60.0)
        self.level_updated.emit(max(display_db, 0.0))

    def run(self):
        with sd.InputStream(channels=1, samplerate=44100,
                            blocksize=2048, callback=self._callback):
            while self._running:
                self.msleep(50)
```

### dBFS → 표시 dB 매핑

공식: `display_db = (dbfs + 60) × (110 / 60)`

| 마이크 원시 dBFS | 표시 dB | 상황 |
|---|---|---|
| -60 dBFS | 0 dB | 완전 조용 |
| -40 dBFS | 33 dB | 주변 소음 |
| -20 dBFS | 66 dB | 일반 대화 |
| -10 dBFS | 83 dB | 큰 목소리 |
| **-2 dBFS** | **100 dB** | **클리핑 직전 최대 → 통과** |
| 0 dBFS | 110 dB | 클리핑 |

**민감도**: 일반 대화(-20 dBFS ≈ 66 dB)는 통과 불가. 실제로 크게 소리를 질러야 통과 가능.

---

## 4. 게임 로직

- `AudioThread.level_updated` Signal → `AudioGameWidget._on_level_updated(db: float)` 슬롯
- 현재 `db >= db_threshold(100)` → `hold_timer += 0.05`
- 현재 `db < db_threshold` → `hold_timer = 0.0` (**연속 유지 필요, 단절 시 리셋**)
- `hold_timer >= 5.0` → `game_success` Signal
- 전체 타이머(`time_limit_audio`, 기본 30초) 소진 → `game_failed` Signal
- 포기 버튼 클릭 → `game_quit` Signal

---

## 5. UI 레이아웃

```
┌─────────────────────────────────┐
│  🎤  소리질러!                    │
│  [앱 이름] 실행을 위해 5초 유지!   │
│                                  │
│       ████████░░  82 dB          │
│       ──────────  100 dB ← 목표   │
│                                  │
│  유지: [█████░░░░░]  2.3 / 5.0 s  │
│  남은 시간: 18s                   │
│                                  │
│           [포기]                  │
└─────────────────────────────────┘
```

**UI 컴포넌트**:
- `dB_bar` (QProgressBar): 현재 dB 레벨 (0~120 범위, 실시간 갱신)
- `target_line` (QLabel 또는 QFrame): 100 dB 목표선 (빨간색)
- `hold_bar` (QProgressBar): 유지 시간 (0~5초)
- `countdown_label` (QLabel): 남은 시간 초
- `quit_btn` (QPushButton): 포기

dB 레벨이 100 이상이면 `dB_bar` 색이 빨간색 → 초록색으로 변경 (통과 조건 달성 시각 피드백).

---

## 6. 설정 항목

### config.py 추가 필드

```python
db_threshold: int = 100        # 통과 dB 기준 (80 / 90 / 100)
time_limit_audio: int = 30     # 게임 제한시간 (20 / 30 / 45초)
```

### 설정 화면 콤보박스 추가

- **dB 기준**: 80 dB / 90 dB / 100 dB (기본 100)
- **제한시간**: 20초 / 30초 / 45초 (기본 30)

---

## 7. 마이크 폴백

```python
def start_game(self, app_name, app_path):
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        # 기본 입력 장치 확인
        sd.check_input_settings()
    except Exception:
        QTimer.singleShot(0, lambda: self.game_quit.emit())
        return
    # ... 게임 시작
```

`game_quit` → `main_window._on_audio_game_quit` → `random.choice(["aim","bug","keyboard","motion"])` 재추첨

---

## 8. main_window.py 변경 요약

1. `from audio_game import AudioGameWidget` import 추가
2. `audio_widget` 생성 (stack index 5), `game_quit` → `_on_audio_game_quit` 연결
3. `_on_process_detected`: `random.choice(["aim","bug","keyboard","motion","audio"])`
4. `_launch_game`: `elif game_type == "audio"` 분기 추가
5. `_on_game_success` dict: `5: self.audio_widget` 추가
6. `_on_game_quit` dict: `5: self.audio_widget` 추가
7. `_on_audio_game_quit`: pool = `["aim","bug","keyboard","motion"]`
8. 설정 화면: dB 기준 콤보 + 제한시간 콤보 추가
9. `_save_config`: `db_threshold`, `time_limit_audio` 저장
