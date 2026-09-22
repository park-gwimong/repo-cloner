# Project Repo Cloner

GitHub 조직, Bitbucket 프로젝트, 직접 지정한 Git URL의 저장소를 일괄 clone하고 안전하게 갱신하는 터미널 도구입니다.
**기본 실행은 TUI**입니다. 저장 경로와 조회할 서비스를 화면에서 설정한 뒤 프로젝트·저장소를 선택합니다.
Python 3.10 이상과 Git이 필요하며 런타임 외부 라이브러리는 없습니다.

## 빠른 시작

`repositories.example.json`을 `repositories.json`으로 복사하고 인증 정보를 입력하세요.

```json
{
  "username": "you@example.com",
  "token": "YOUR_TOKEN"
}
```

`repositories.json`에는 **username과 token만** 저장합니다. 저장 경로, provider, workspace, 조직,
프로젝트, 저장소 목록은 TUI에서 설정하며 파일에 기록하지 않습니다. 실행할 때마다 다시 설정합니다.
인증 정보는 화면에 표시하지 않습니다. 이 파일은 Git 제외 대상입니다.

```bash
python repo_cloner.py
# Git 실행 없이 설정·조회·미리 보기
python repo_cloner.py --dry-run
# 설치 후 명령으로 실행
python -m pip install .
repo-cloner
```

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

전체 설정 예제는 [repositories.batch.example.json](repositories.batch.example.json),
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
실행 전 확인에서 취소하면 변경 없이 종료하며 앞선 조회 실패가 없다면 0입니다.
실행 도중 중단했을 때는 이미 완료한 작업을 되돌리지 않습니다.

실패한 clone은 `.clone-<임의 값>` 임시 폴더나 불완전한 최종 폴더를 남길 수 있습니다.
출력된 경로를 확인한 뒤 다시 실행하세요. 동시에 같은 저장 경로를 변경하지 마세요.
dry-run은 API 조회는 수행하지만 Git 실행·폴더 생성·기존 저장소 갱신 자격 검사는 하지 않습니다.

## 개발

```bash
python -m unittest discover -s tests -v
```

테스트는 실제 API 토큰 없이 API 조회, 인증, TUI 설정·선택·취소, dry-run,
임시 Git 원격을 이용한 안전한 갱신을 검증합니다. Git이 PATH에 있어야 합니다.
라이선스는 [MIT](LICENSE)입니다.
