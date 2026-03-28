# Keyboard Game — Quote Card 복원 설계

**날짜**: 2026-03-28
**범위**: `mouse-game/keyboard_game.py`
**목적**: 타자 게임 UI에서 타겟 문장이 보이지 않는 문제 해결

---

## 배경

`TypingField` 위젯 도입 시 기존 `_quote_label` 카드(타겟 문장을 크고 흰색으로 표시하던 박스)가 제거되었다.
현재 `TypingField`의 ghost text는 정상 동작하지만, 사용자 입장에서 "어떤 문장을 쳐야 하는지" 눈에 띄게 보이지 않는다.

---

## 목표

- 타겟 문장을 **두 곳**에 표시한다.
  1. **타겟 카드** (상단): 흰색 텍스트 + 저자, 큰 폰트, 어두운 배경 카드 — 읽기 전용 참조용
  2. **TypingField** (하단): 회색 ghost text → 타이핑 시 흰색(정확) / 빨간색(오류)

---

## 레이아웃 (위→아래)

```
헤더 레이블
라운드 진행 표시
통계 바 (시간 | 타수 | 정확도)
[_target_card]  타겟 문장 흰색 + — 저자   ← 복원
"아래 문장을 따라 입력하세요:"
[TypingField]  회색 ghost text + 색상 피드백
안내 텍스트
(spacer)
포기 버튼
```

---

## 컴포넌트 변경

### 추가: `_target_card` (QLabel)

| 속성 | 값 |
|---|---|
| 폰트 | Arial 16pt Bold |
| 텍스트 색 | `#e2e8f0` (TEXT_PRIMARY) |
| 배경 | `#1a1a2e` (CARD_BG) |
| 테두리 | `border-radius: 10px; padding: 20px;` |
| 정렬 | 가운데 |
| 내용 | `f"{quote}\n— {author}"` |
| 줄 바꿈 | `setWordWrap(True)` |

### 제거: `_author_label`

저자 정보가 `_target_card`에 통합되므로 별도 레이블 불필요.

### 유지: `TypingField`

변경 없음. `set_target(quote)`만 호출.

---

## 코드 변경 요약

**`_init_ui()`**:
- `_author_label` 생성 및 layout 추가 코드 제거
- `_target_card` QLabel 생성 및 layout 추가 (통계 바 아래)

**`_start_round()`**:
- `self._author_label.setText(...)` → 제거
- `self._target_card.setText(f"{quote}\n— {author}")` 추가

---

## 제약 사항

- `TypingField` 내부 구조 변경 없음
- 게임 로직(타수 계산, 정확도, 라운드 등) 변경 없음
- 스타일 상수(`DARK_BG`, `CARD_BG` 등) 변경 없음

---

## 완료 기준

- 게임 시작 시 타겟 문장이 상단 카드에 흰색으로 표시됨
- 동시에 입력 칸에 동일 문장이 회색 ghost text로 표시됨
- 타이핑 시 입력 칸에서 맞은 글자는 흰색, 틀린 글자는 빨간색으로 변함
- 라운드 전환 시 카드와 입력 칸 모두 새 문장으로 업데이트됨
