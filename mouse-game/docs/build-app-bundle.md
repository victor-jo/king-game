# macOS App 번들 빌드 가이드

## 개요

`mouse-game`을 macOS `.app` 번들로 패키징하여 Finder에서 더블클릭으로 실행할 수 있게 합니다.

## 환경

- Python: miniconda3 (3.12)
- 패키저: `py2app`
- 가상환경: `mouse-game/venv/`

## 최초 환경 설정

```bash
cd /Users/hj/king-game/mouse-game
/Users/hj/miniconda3/bin/python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 빌드

```bash
cd /Users/hj/king-game/mouse-game
source venv/bin/activate
python setup.py py2app
```

빌드 결과물: `dist/AimGuard.app`

## 실행

```bash
open /Users/hj/king-game/mouse-game/dist/AimGuard.app
```

## setup.py 핵심 설정

```python
OPTIONS = {
    'no_zip': True,  # python312.zip 압축 비활성화 (sounds 디렉토리 생성 오류 방지)
    'frameworks': ['/Users/hj/miniconda3/lib/libffi.8.dylib'],  # libffi 번들에 포함
}
```

### 옵션 설명

- **`no_zip`**: py2app 기본 동작은 Python 파일을 `python312.zip`으로 압축하는데,
  `sounds.py`가 `__file__` 기준으로 디렉토리를 생성하려 하면 zip 내부 경로를 가리켜 실패함.
  `no_zip: True`로 압축을 비활성화하여 해결.
- **`frameworks`**: `libffi.8.dylib`가 번들에 포함되지 않으면 `_ctypes` 모듈 로드 실패.
  miniconda3에서 가져와 `Frameworks/` 디렉토리에 포함.

## 트러블슈팅

| 에러 | 원인 | 해결 |
|------|------|------|
| `dlopen libffi.8.dylib` | libffi가 번들에 없음 | `frameworks`에 경로 추가 |
| `NotADirectoryError: python312.zip/sounds` | zip 내부에 폴더 생성 시도 | `no_zip: True` 설정 |
