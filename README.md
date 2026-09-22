# Project Repo Cloner

[![Tests](https://github.com/park-gwimong/repo-cloner/actions/workflows/tests.yml/badge.svg)](https://github.com/park-gwimong/repo-cloner/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

GitHub 조직, Bitbucket 프로젝트, 직접 지정한 Git URL의 저장소를 일괄 clone하고 안전하게 갱신하는 터미널 도구입니다.
**기본 실행은 TUI**입니다. 저장 경로와 조회할 서비스를 화면에서 설정한 뒤 프로젝트·저장소를 선택합니다.
Python 3.10 이상과 Git이 필요하며 런타임 외부 라이브러리는 없습니다.

[시작하기](#빠른-시작) · [Batch 가이드](docs/BATCH.md) · [설정 레퍼런스](docs/CONFIGURATION.md) · [문제 해결](docs/TROUBLESHOOTING.md) · [기여](CONTRIBUTING.md)

## 목차

- [주요 기능](#주요-기능)
- [요구 사항과 설치](#요구-사항과-설치)
- [빠른 시작](#빠른-시작)
- [실행 모드 비교](#실행-모드-비교)
- [TUI 실행 흐름](#tui-실행-흐름)
- [Batch 모드](#batch-모드)
- [인증](#인증)
- [실행 옵션](#실행-옵션)
- [안전한 갱신과 결과](#안전한-갱신과-결과)
- [문서 안내](#문서-안내)
- [프로젝트 구조](#프로젝트-구조)
- [개발과 기여](#개발과-기여)
- [라이선스](#라이선스)

## 주요 기능

- GitHub Organization, Bitbucket Cloud, Bitbucket Server / Data Center 및 직접 Git URL 지원
- 키보드 TUI의 workspace → 프로젝트 → 저장소 선택과 저장 경로 편집
- 여러 source·프로젝트를 처리하는 batch 및 include/exclude 이름 필터
- 실행 대상과 경로 미리 보기, 저장소 단위 진행률 및 결과 집계
- 기존 작업 트리를 검사하고 현재 upstream만 fast-forward하는 갱신 정책
- Python 표준 라이브러리 기반 구현, Windows/macOS/Linux CI 구성

복제 단위는 Git 저장소의 일반 작업 트리입니다. 전체 refs를 보관하는 mirror 백업,
로컬 미커밋 변경 백업, 서브모듈 자동 초기화, 여러 저장소의 병렬 clone은 지원하지 않습니다.

## 요구 사항과 설치

| 항목 | 요구 사항 |
| --- | --- |
| Python | 3.10 이상 |
| Git | 실제 clone/update 시 PATH에 설치 필요 |
| TUI 터미널 | ANSI 지원, 최소 61열 × 12행, 직접 연결된 표준 입력·출력 |
| 네트워크 | API 조회용 HTTPS와 저장소 URL에 맞는 SSH/HTTPS 연결 |

```bash
git clone https://github.com/park-gwimong/repo-cloner.git
cd repo-cloner
python --version
git --version
python repo_cloner.py --help
```

소스에서 바로 실행할 수 있습니다. 명령으로 설치하려면 다음을 사용하세요.
아래 설치는 현재 체크아웃을 대상으로 하며 PyPI 배포 여부를 전제로 하지 않습니다.

```bash
python -m venv .venv
# 가상환경 활성화 후
python -m pip install .
repo-cloner --help
```

PowerShell 활성화: `.venv\Scripts\Activate.ps1`, macOS/Linux 활성화: `source .venv/bin/activate`.
macOS/Linux 환경에 따라 `python` 대신 `python3`를 사용하세요.
가상환경 활성화가 제한된 환경에서는 해당 환경의 Python 실행 파일을 직접 지정해도 됩니다.

## 빠른 시작

`examples/credentials.json`을 `repositories.json`으로 복사하고 인증 정보를 입력하세요.

```json
{
  "username": "you@example.com",
  "token": "YOUR_TOKEN"
}
```

`repositories.json`에는 **username과 token만** 저장합니다. 저장 경로, provider, workspace, 조직,
프로젝트, 저장소 목록은 TUI에서 설정하며 파일에 기록하지 않습니다. 실행할 때마다 다시 설정합니다.
인증 정보는 화면에 표시하지 않습니다. 이 파일은 Git 제외 대상입니다.

```powershell
# Windows PowerShell
Copy-Item examples/credentials.json repositories.json
```

```bash
# macOS / Linux
cp examples/credentials.json repositories.json
```

복사한 파일의 YOUR_TOKEN과 이메일을 수정하세요. 예제 원본에는 실제 인증 값을 넣지 마세요.
직접 Git URL만 사용할 경우 repositories.json을 `{}`로 작성해도 됩니다.

```bash
python repo_cloner.py
# Git 실행 없이 설정·조회·미리 보기
python repo_cloner.py --dry-run
# 설치 후 명령으로 실행
python -m pip install .
repo-cloner
```

## 실행 모드 비교

| 모드 | 명령 | 설정 파일 | 선택과 확인 | 권장 상황 |
| --- | --- | --- | --- | --- |
| TUI (기본) | `python repo_cloner.py` | 인증 전용 repositories.json | 화면 설정·다중 선택, 마지막 Enter로 실행 | 목록을 탐색하며 수동 실행 |
| Batch | `python repo_cloner.py --batch --config batch.json` | 전체 source 설정 | 앱 선택·확인 없음 | 같은 대상 반복 실행, 예약 작업, CI |
| 번호 입력 | `python repo_cloner.py -i --config batch.json` | 전체 source 설정 | 번호 선택 후 y로 실행, Enter는 취소 | 단순 콘솔에서 선택 실행 |

세 모드 모두 `--dry-run`을 지원합니다. `--batch`, `-i`, `--tui`는 동시에 지정할 수 없습니다.
API 인증 전용 파일과 전체 설정 파일은 자동 병합되지 않습니다.

## TUI 실행 흐름

1. **저장 경로 입력**: 기본값은 인증 파일 옆의 `clones`입니다. 직접 입력하는 상대 경로는 현재 실행 폴더 기준이며 `~`를 지원합니다. 입력만으로 폴더를 만들지 않습니다.
2. **SSH / HTTPS 선택**: API에서 가져올 저장소의 clone URL 형식을 선택합니다.
3. **서비스 설정**: Bitbucket Cloud는 인증 계정이 접근 가능한 워크스페이스를 조회해 목록에서 선택합니다. GitHub 조직·API 주소, Bitbucket Server의 HTTPS 주소 또는 직접 Git URL은 입력합니다.
4. **연결 추가**: 필요하면 다른 서비스 연결이나 직접 Git URL을 추가합니다. 별도의 source 폴더 이름은 입력하지 않습니다. 프로젝트 정보가 없는 직접 Git URL은 묶어서 저장할 프로젝트명을 입력합니다.
5. **프로젝트·저장소 선택**: 접근 가능한 목록을 조회하고 여러 항목을 선택합니다.
6. **대상 확인**: 작업 종류와 최종 저장 경로를 검토한 뒤 `Enter` 또는 `Y`로 실행합니다. `N`, `Esc`, `Q`는 실행을 취소합니다.

Bitbucket 프로젝트는 `<저장 경로>/<프로젝트명>/<저장소 이름>`에 저장됩니다.
폴더명은 API에서 조회한 프로젝트 표시 이름이며 프로젝트 키는 조회에만 사용합니다.
예를 들어 `KEY` 키의 프로젝트명이 `관제 시스템`이면 `clones/관제 시스템/api` 형태입니다.
GitHub는 `<저장 경로>/<조직명>/<저장소 이름>`, 직접 Git URL은 `<저장 경로>/<입력한 프로젝트명>/<저장소 이름>`에 저장됩니다.
같은 이름의 프로젝트를 동시에 선택하거나 프로젝트명을 폴더명으로 사용할 수 없으면 실행 전에 오류로 중단합니다.
기존 `--batch` 및 `-i`의 설정 기반 경로 규칙은 유지됩니다.
저장 경로를 바꾸면 새 경로를 대상으로 실행하며 기존 폴더를 이동하지 않습니다.

입력 화면에서는 `Ctrl+U`로 기존 값을 지우고 새 값을 입력하세요. 한글·공백·대소문자를 유지합니다.
`←` / `→`, `Home` / `End`로 입력 위치를 이동하고 `Backspace`로 삭제합니다.
입력 중 `Q`는 일반 문자이며 `Esc` 또는 `Ctrl+C`로 취소합니다.

| 선택 화면 키 | 동작 |
| --- | --- |
| `↑` / `↓`, `k` / `j` | 항목 이동 |
| `Space` | 다중 선택 화면에서 선택/해제 |
| `A` / `N` | 전체 선택/해제 |
| `Enter` | 다음 단계 또는 단일 옵션 선택 |
| `PageUp` / `PageDown`, `Home` / `End` | 긴 목록 이동 |
| `←` / `→` | 긴 저장 경로 좌우 스크롤 |
| `Q`, `Esc`, `Ctrl+C` | 취소 |

다중 선택의 초기 상태는 선택 없음입니다. dry-run 확인 화면에서는 `Enter`로 미리 보기를 마칩니다.
목록 조회, clone/update 진행률, Git 로그와 최종 집계는 일반 터미널 화면에 표시됩니다.
메뉴를 닫으면 이전 화면과 커서를 복구합니다.
Windows ANSI 콘솔(예: Windows Terminal), macOS/Linux 터미널에서 최소 61열 × 12행으로 사용하세요.
크기를 바꾸면 다음 키 입력 때 다시 그립니다. 파일·파이프 입출력 환경에서는 `--batch`를 사용하세요.

## Batch 모드

batch는 JSON에 지정한 저장소를 **확인 입력 없이 순서대로 clone/update**합니다.
TUI에서 선택했던 결과를 자동 재사용하는 기능이 아니라 별도의 재현 가능한 작업 설정을 실행하는 방식입니다.

API가 필요 없는 예제로 시작할 수 있습니다. 아래 내용을 프로젝트 루트의 `batch.json`에 저장하세요.

```json
{
  "destination": "./clones",
  "sources": [
    {
      "name": "personal",
      "provider": "git",
      "repositories": [
        {"name": "repo-cloner", "url": "https://github.com/park-gwimong/repo-cloner.git"}
      ]
    }
  ]
}
```

```bash
python repo_cloner.py --batch --config batch.json --dry-run
python repo_cloner.py --batch --config batch.json
```

첫 명령은 미리 보기이고 두 번째는 실제 실행입니다. 위 예제의 결과는 `clones/personal/repo-cloner`입니다.
API provider를 사용하면 해당 source에 workspace·조직·프로젝트 키와 인증 정보를 추가합니다.
`--batch`만 지정해도 파일명이 batch.json으로 바뀌지 않으므로 `--config`를 명시하세요.

### 저장 경로 규칙

| 모드와 대상 | 저장 경로 |
| --- | --- |
| TUI Bitbucket | `<destination>/<프로젝트 표시 이름>/<저장소>` |
| TUI GitHub | `<destination>/<조직명>/<저장소>` |
| TUI 직접 URL | `<destination>/<입력한 프로젝트명>/<저장소>` |
| Batch 단일 project / GitHub / 직접 URL | `<destination>/<source.name>/<저장소>` |
| Batch projects 목록 | `<destination>/<source.name>/<프로젝트 키>/<저장소>` |

batch도 프로젝트명 바로 아래에 저장하려면 프로젝트마다 source를 만들고
`name`을 프로젝트명, `project`를 API 프로젝트 키로 지정하세요.
JSON destination의 상대 경로는 **설정 파일 위치**, CLI --destination의 상대 경로는 **현재 작업 디렉터리** 기준입니다.

### 처리와 자동화

설정 검사 → 저장소 조회 → 필터 → 전체 대상 표시 → 순차 clone/update → 결과 집계 순서입니다.
잡힌 조회·저장소 처리 오류는 실패로 집계하고 나머지를 계속하며, 시작 단계의 설정 오류는 실행을 중단합니다.
같은 설정으로 재실행하면 기존 경로를 검사해 안전한 경우만 갱신합니다.

batch는 앱의 입력을 생략하지만 Git/SSH 인증 프롬프트까지 없애지는 않습니다.
예약 실행 계정에서 인증을 미리 설정하고 같은 저장 경로의 작업을 중복 실행하지 마세요.
상세한 Bitbucket 예제, 필터, 로그 저장, 예약 실행과 종료 코드 설명은 [Batch 가이드](docs/BATCH.md)를 보세요.

## 인증

- Bitbucket Cloud: `username`은 토큰을 발급한 계정 이메일, `token`은 Bitbucket API 토큰입니다. 둘을 Basic 인증에 사용합니다.
- GitHub, Bitbucket Server / Data Center: `token`을 Bearer 인증에 사용하며 `username`은 전송하지 않습니다.
- 직접 Git URL: 목록 조회 API 인증을 사용하지 않습니다.
- Bearer 인증만 필요하면 `username`을 생략할 수 있습니다. 익명 조회나 직접 URL만 사용하면 `{}`도 허용합니다. 항목을 지정한 경우 빈 문자열은 허용하지 않습니다.

이번 실행에 추가한 API source들은 같은 토큰을 사용하므로 해당 서비스에 맞는 인증 파일을 선택하세요.
다른 계정은 `--config`로 별도 인증 파일을 지정할 수 있습니다. `.env`·환경변수는 API 인증에 사용하지 않습니다.
**목록 조회 인증과 Git clone 인증은 별개입니다.** SSH 키 또는 Git Credential Manager 등 로컬 Git 인증을 설정하세요.
Git URL에는 비밀번호나 토큰을 넣지 않습니다. Bitbucket Cloud 토큰에는 저장소 조회용 `read:repository:bitbucket`과 워크스페이스 선택용 `read:workspace:bitbucket` scope가 필요합니다.
워크스페이스는 [공식 사용자 워크스페이스 API](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-workspaces/#api-user-workspaces-get)로 모든 페이지를 조회합니다.
목록에서는 이름과 식별자를 표시하며, 이름이 없는 응답은 식별자만 표시합니다. 방향키와 `Enter`로 선택하고 `Esc`·`Q`로 취소할 수 있습니다.
조회 실패나 빈 목록이면 원인을 안내하고 중단하며, workspace를 직접 입력하도록 전환하지 않습니다.

## 실행 옵션

| 옵션 | 동작 |
| --- | --- |
| 옵션 없음 / `--tui` | TUI 설정 및 프로젝트·저장소 선택 |
| `--config PATH` | 인증 JSON 경로. 기본값 `repositories.json` |
| `--destination PATH` | TUI 저장 경로의 초기값. 화면에서 변경 가능 |
| `--dry-run` | 조회·대상 표시만 수행. Git 실행 및 폴더 생성 없음 |
| `--batch` | 별도의 전체 source 설정 파일로 확인 입력 없이 일괄 실행 |
| `--interactive`, `-i` | 별도의 전체 source 설정 파일로 기존 번호 입력 모드 실행 |
| `--help` | 도움말 |

`--tui`, `--batch`, `-i`는 함께 사용할 수 없습니다.
기존 전체 설정 파일은 별도 이름으로 보관하고 `--batch` 또는 `-i`로 실행하세요.
TUI는 인증 전용 형식을 검사하며 기존 전체 설정 파일을 자동 변경하지 않습니다.

```bash
python repo_cloner.py --destination "D:/Git Copies"
python repo_cloner.py --batch --config batch.json --dry-run
python repo_cloner.py --batch --config batch.json
python repo_cloner.py -i --config batch.json
```

전체 설정 예제는 [examples/batch.all-providers.json](examples/batch.all-providers.json),
프로젝트별 설정·include/exclude·API 문제 해결 및 갱신 조건은 [일괄 실행 참고 문서](docs/BATCH.md)를 보세요.
별도 파일에 실제 토큰을 넣었다면 해당 파일도 커밋하지 마세요.

## 안전한 갱신과 결과

없는 경로는 clone하고 기존 일반 디렉터리는 안전 조건을 확인한 뒤 현재 upstream만 fast-forward합니다.
원격 URL이 다르거나 로컬 수정·untracked 파일·진행 중 Git 작업·불명확한 upstream이 있으면 건너뜁니다.
로컬 커밋은 보존하며 stash, reset, clean, rebase를 실행하지 않습니다. 서브모듈도 자동 초기화하지 않습니다.
`UPDATE?`는 갱신 후보이며 안전 검사가 끝났다는 뜻은 아닙니다.

진행률은 처리한 저장소 수를 기준으로 하며 마지막에 `cloned`, `updated`, `unchanged`,
`skipped`, `planned`, `failed`를 집계합니다. 실패한 source·저장소 뒤에도 나머지를 처리합니다.
실패가 있으면 종료 코드 1, 정상 종료는 0, 키보드 취소는 130입니다.
잘못된 CLI 옵션이나 상호 배타적인 옵션 조합은 종료 코드 2입니다.
실행 전 확인에서 취소하면 변경 없이 종료하며 앞선 조회 실패가 없다면 0입니다.
실행 도중 중단했을 때는 이미 완료한 작업을 되돌리지 않습니다.

실패한 clone은 `.clone-<임의 값>` 임시 폴더나 불완전한 최종 폴더를 남길 수 있습니다.
출력된 경로를 확인한 뒤 다시 실행하세요. 동시에 같은 저장 경로를 변경하지 마세요.
dry-run은 API 조회는 수행하지만 Git 실행·폴더 생성·기존 저장소 갱신 자격 검사는 하지 않습니다.

정확한 원격 URL 비교, upstream 검사, FETCH_HEAD/tracking ref 변경 범위는 [안전 정책](docs/SAFETY.md)에 설명되어 있습니다.

## 문서 안내

| 문서 | 내용 |
| --- | --- |
| [Batch 가이드](docs/BATCH.md) | 전체 설정 실행, 경로, 필터, 로그·예약 실행, 종료 코드 |
| [설정 레퍼런스](docs/CONFIGURATION.md) | TUI/batch 형식, provider별 필드, 인증·경로 규칙 |
| [안전 정책](docs/SAFETY.md) | clone/update 보호 조건과 재실행의 한계 |
| [문제 해결](docs/TROUBLESHOOTING.md) | API 인증·네트워크·Git·TUI 오류 |
| [구조 설명](docs/ARCHITECTURE.md) | 두 Python 모듈의 역할과 실행 흐름 |
| [예제 목록](examples/README.md) | 서비스별 복사해서 사용할 JSON |
| [변경 기록](CHANGELOG.md) | 주요 변경과 설정·동작 호환성 |

## 프로젝트 구조

```text
repo-cloner/
├── repo_cloner.py               # 진입점, API, 계획, clone/update
├── repo_cloner_tui.py           # 키보드 입력, 설정 화면, 선택·확인
├── pyproject.toml              # 패키징 및 repo-cloner 명령
├── examples/                   # 인증 및 provider별 batch 예제
├── docs/                       # 사용·설정·안전·구조 문서
├── tests/                      # 표준 unittest 테스트
├── .github/
│   ├── workflows/tests.yml     # OS·Python 조합 CI
│   ├── ISSUE_TEMPLATE/         # 버그 및 기능 요청 양식
│   └── pull_request_template.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── README.md
└── LICENSE
```

핵심 파일 중심의 구조이며 로컬 자격 증명·도구 파일은 생략했습니다.
두 Python 모듈은 소스 직접 실행과 설치 명령을 모두 지원하도록 루트에 둡니다.
`repo_cloner.py`가 TUI 모듈을 필요할 때 불러오므로 TUI 파일을 따로 실행할 필요가 없습니다.
기존 루트의 예제 JSON 두 개는 `examples/credentials.json`, `examples/batch.all-providers.json`으로 이동했습니다.

## 개발과 기여

```bash
python -m unittest discover -s tests -v
```

테스트는 실제 API 토큰 없이 API 조회, 인증, TUI 설정·선택·취소, dry-run,
임시 Git 원격을 이용한 안전한 갱신을 검증합니다. Git이 PATH에 있어야 합니다.
GitHub Actions는 Windows/Linux/macOS와 Python 3.10/3.13 조합으로 테스트·설치·명령 도움말을 확인합니다.
개발 환경과 PR 검증 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 보세요.
버그 보고와 기능 제안은 [Issues](https://github.com/park-gwimong/repo-cloner/issues)에서 양식을 사용하세요.

문서·폴더 구성은 [Ruff](https://github.com/astral-sh/ruff)의 문서/기여 분리,
[yt-dlp](https://github.com/yt-dlp/yt-dlp)의 목차·명령 옵션·예제 중심 설명,
[Textual](https://github.com/Textualize/textual)의 사용자·개발 문서 구분을 참고했습니다.
이 프로젝트의 규모와 표준 라이브러리 기반 실행 방식에 맞게 적용했습니다.

## 라이선스

[MIT](LICENSE). Atlassian 또는 GitHub의 공식 도구가 아닙니다.
