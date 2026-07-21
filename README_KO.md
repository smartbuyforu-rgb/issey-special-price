# ISSEY MIYAKE SPECIAL PRICE Catalog v1.2

> **v1.2 수정:** Python 3.13 free-threaded 빌드(`cp313t`, `3.13t`)에서는 Playwright 의존 패키지인 `greenlet` 설치가 실패할 수 있습니다. 이번 버전은 free-threaded Python을 자동으로 제외하고 **일반 Python 3.12 → 일반 3.13 → 일반 3.11** 순서로 선택합니다. 기존 `.venv`가 free-threaded Python으로 생성돼 있으면 자동 삭제 후 다시 만듭니다.

기존 `7days`와 비슷한 모바일 카탈로그이며, 사용자 PC의 로그인된 브라우저 프로필로 SPECIAL PRICE 상품과 옵션별 재고를 수집한 다음 GitHub Pages에 표시합니다.

## 이번 오류를 해결하는 가장 빠른 순서

1. 새 v1.2 ZIP을 새 폴더에 완전히 압축 해제합니다.
2. `00_INSTALL_PYTHON_312.bat`을 실행합니다.
3. 설치가 끝나면 `01_INSTALL.bat`을 실행합니다.
4. `[OK] Installation completed.`가 나오면 `02_LOGIN.bat`을 실행합니다.
5. 로그인 후 `03_TEST_UPDATE.bat`으로 수집을 확인합니다.

일반 Python 3.12는 현재 설치된 Python 3.13t와 함께 설치할 수 있습니다. 3.13t를 제거할 필요는 없습니다. v1.2 설치기가 `py -3.12`를 명시적으로 사용합니다.

## 오류 원인

로그에 다음 표기가 있으면 free-threaded Python입니다.

```text
build\lib.win-amd64-cpython-313t
```

끝의 `t`가 free-threaded ABI를 뜻합니다. 이 환경에서 `greenlet`의 Windows용 사전 빌드 파일을 찾지 못하면 소스 컴파일을 시도하고, 그 결과 Microsoft Visual C++ 14 이상을 요구합니다. 이 프로젝트 때문에 대용량 C++ Build Tools를 설치할 필요는 없습니다.

## 포함 기능

- 로그인 ID가 없는 사람도 GitHub Pages 링크에서 상품과 옵션별 재고 확인
- 브랜드 필터, 상품 검색, 재고 상품만 보기
- 모바일 3열 / PC 5열
- 설정된 간격으로 자동 수집 및 GitHub push
- 로그인 쿠키와 브라우저 프로필은 `private/`에만 저장
- 수집 실패 시 마지막 정상 페이지 유지

## 처음 설정

### 1. 압축 풀기

ZIP 안에서 직접 실행하지 말고 다음처럼 짧은 경로에 완전히 압축 해제합니다.

```text
D:\issey_special_price_catalog_v1_2
```

### 2. 일반 Python 3.12 설치

`00_INSTALL_PYTHON_312.bat`을 실행합니다.

- `winget`이 있으면 일반 Python 3.12를 자동 설치합니다.
- 자동 설치가 안 되면 Python 공식 Windows 다운로드 페이지를 엽니다.
- 설치 화면에 free-threaded 항목이 있으면 선택하지 않습니다.
- Python Launcher와 Add Python to PATH는 가능하면 활성화합니다.

### 3. 프로그램 설치

`01_INSTALL.bat`을 실행합니다.

정상 예시:

```text
[1/5] Finding a compatible standard Python...
[OK] Python 3.12.x
[2/5] Checking the existing virtual environment...
[3/5] Creating a new virtual environment...
[4/5] Installing Python packages...
[5/5] Installing Playwright Chromium...
[OK] Installation completed.
```

### 4. 로그인 저장

`02_LOGIN.bat`을 실행합니다.

1. 브라우저에서 직접 로그인합니다.
2. SPECIAL PRICE 상품 목록이 실제로 보이는지 확인합니다.
3. 검은 창으로 돌아와 Enter를 누릅니다.

아이디와 비밀번호는 코드와 GitHub에 저장하지 않습니다. 로그인 세션은 `private/browser_profile/`에만 저장됩니다.

### 5. 수집 테스트

`03_TEST_UPDATE.bat`을 실행합니다. 성공하면 `index.html`이 열립니다.

0개 또는 로그인 오류가 나오면 `02_LOGIN.bat`을 다시 실행하고, 계속 실패하면 `07_DIAGNOSE.bat`을 실행합니다.

## GitHub Pages 연결

1. GitHub에서 빈 Public 저장소를 만듭니다.
2. `04_CONNECT_GITHUB.bat`을 실행하고 저장소 HTTPS 주소를 붙여넣습니다.
3. 저장소의 `Settings → Pages`에서 `Deploy from a branch`, `main`, `/(root)`를 선택합니다.
4. 생성된 `https://사용자명.github.io/저장소명/` 주소를 공유합니다.

GitHub Pages는 공개될 수 있으므로 민감한 정보는 게시하지 마세요. `private/` 폴더는 `.gitignore`로 차단되어 있습니다.

## 자동 업데이트

- `05_START_AUTO_UPDATE.bat`: 창을 켜두고 자동 갱신
- `06_UPDATE_AND_PUBLISH_ONCE.bat`: 한 번만 수집하고 게시
- `08_INSTALL_AUTOSTART.bat`: Windows 로그인 시 자동 실행 등록
- `09_REMOVE_AUTOSTART.bat`: 자동 실행 제거

## 설정

`config.json`의 주요 항목:

```json
{
  "refresh_minutes": 5,
  "headless_collect": true,
  "browser_channel": "chrome"
}
```

사이트 부담을 줄이기 위해 확인 간격은 5분 이상을 권장합니다.

## GitHub에 올리면 안 되는 파일

```text
private/browser_profile/
private/debug_collection.html
private/debug_collection.png
private/debug_info.json
```

이 항목들은 `.gitignore`로 제외돼 있습니다.
