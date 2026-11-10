# 문제 해결

Bitbucket Cloud용 API 토큰은 **Create API token with scopes → Bitbucket**을 선택하고,
저장소 목록 조회에 필요한 **`read:repository:bitbucket`** 권한을 명시적으로 지정해 발급하세요.
Admin이나 Write를 선택해도 Read가 자동으로 포함되지 않습니다.
발급 절차는 [공식 API 토큰 생성 안내](https://support.atlassian.com/bitbucket-cloud/docs/create-an-api-token/),
권한 동작은 [공식 REST API 문서](https://developer.atlassian.com/cloud/bitbucket/rest/)를 참고하세요.

| 증상 | 확인할 항목 |
| --- | --- |
| HTTP 401 | 이메일과 토큰의 계정 일치 여부, 만료·폐기 여부, Bitbucket용 scope를 지정해 발급했는지 확인 |
| HTTP 403 | `read:repository:bitbucket` 권한과 계정의 대상 저장소 접근 권한 확인 |
| 조회 성공인데 저장소 0개 | workspace 식별자, 프로젝트 **키와 대소문자**, 접근 가능한 저장소 유무 확인 |
| 목록 조회는 성공하지만 clone 실패 | `protocol`에 맞는 SSH 키 또는 Git HTTPS 인증 설정 확인 |
| `API request timed out` | 응답 지연. 최대 3회 시도 후에도 실패하면 네트워크·VPN·서비스 상태 확인 |
| `API DNS lookup failed` / `API connection failed` | DNS, VPN, 방화벽, 프록시 연결 확인 |
| `API TLS verification/handshake failed` | 사용 중인 Python의 인증서 신뢰 설정과 HTTPS 프록시 확인 |
| `API returned invalid JSON` | API 대신 프록시 로그인 화면이나 오류 페이지가 반환되는지 확인 |

일시적인 연결 실패·응답 시간 초과·HTTP 502/503/504는 1초, 2초 대기 후 재시도하며 최대 3회 요청합니다.
각 요청의 소켓 시간 제한은 60초입니다. 인증·TLS·JSON 오류는 자동 재시도하지 않습니다.

`project`에는 표시 이름 대신 실제 키를 입력합니다. 예를 들어 실제 키가 `SDSP`라면
`sdsp`로 조회했을 때 결과가 없을 수 있습니다. `-i --dry-run`으로 프로젝트 목록을 조회해 선택하면
키를 직접 입력하지 않고도 대상과 저장 경로를 확인할 수 있습니다.


## TUI 및 설정 파일

| 증상 | 해결 방법 |
| --- | --- |
| Workspace listing failed / HTTP 403 | 토큰의 `read:workspace:bitbucket` scope와 계정의 workspace 접근 권한 확인 |
| No accessible Bitbucket workspaces | 토큰 계정의 workspace 소속과 접근 권한 확인 |
| TUI config must contain only username and token | 전체 설정은 `--batch --config batch.json` 또는 `-i --config batch.json`으로 실행 |
| sources must be a nonempty list | batch에는 인증 전용 repositories.json 대신 전체 설정 파일을 지정 |
| requires an interactive terminal | 터미널에서 TUI 실행. 리다이렉션·예약 실행은 `--batch` 사용 |
| Duplicate project folder / Invalid folder name | 같은 표시 이름의 프로젝트를 분리해서 실행하거나 이름 수정. batch는 source.name으로 경로를 직접 구분 가능 |
| 화면이 작아 조작할 수 없음 | 터미널을 61열 × 12행 이상으로 확대 후 키 입력 |
| Git was not found in PATH | Git 설치 후 새 터미널에서 git --version 확인 |
| GitHub 개인 계정을 조직으로 조회해 404 발생 | GitHub 메뉴에서 Personal account 선택. Organization은 실제 조직 식별자만 입력 |
| Permission denied (publickey) | 해당 서비스에 등록된 SSH 키와 SSH agent 설정 확인 |
| Host key verification failed | 서비스가 공개한 지문과 비교하여 로컬 SSH known_hosts 설정 확인 |

## batch 설정 (credentials · layout · submodules)

| 오류 메시지 | 원인과 해결 |
| --- | --- |
| `Cannot read credentials file <경로> (FileNotFoundError)` | 참조한 인증 파일이 없음. 상대 경로는 **batch 파일이 있는 폴더 기준**이므로 위치를 확인하고, 다른 PC라면 그 PC에도 인증 파일을 만듦 |
| `Credentials file is not valid JSON: <경로>` | 인증 파일의 JSON 문법 오류. 주석·끝 쉼표 제거 |
| `Credentials file must contain only username and token: <경로>` | 인증 파일에 다른 필드가 있음. 전체 설정 파일(batch)을 인증 파일로 지정하지 않았는지 확인 |
| `Use either credentials or inline token/username in a source, not both` | 한 source에 `credentials`와 `token`/`username`을 함께 씀. 하나만 남김 |
| `credentials must be a nonempty path string` | `credentials` 값이 비었거나 문자열이 아님 |
| `Folder '<이름>' is already used by another source; use distinct names or layout "source"` | `layout: "project"`에서 두 프로젝트·source가 같은 폴더(대소문자 무시)로 모임. 표시 이름을 바꾸거나 기본 layout 사용 |
| `Project name '<이름>' cannot be used as a folder name; use layout "source"` | 프로젝트 표시 이름에 `/` 등 폴더에 쓸 수 없는 문자가 있음. 기본 layout 사용 |
| `skipArchived is only supported for GitHub sources` | `skipArchived`·`skipForks`는 `github`·`github-user` source에만 지정 |
| `layout must be source or project` / `submodules must be true or false` | 값의 철자·형식 확인. `submodules`는 따옴표 없는 `true`/`false` |
| `Submodule update failed; the main repository is unchanged by this step (...)` | 서브모듈 URL 접근 권한(SSH 키·Git 인증)이나 서브모듈 안의 로컬 변경 확인. 본 저장소의 fast-forward는 이미 끝났을 수 있음 |

## TUI에서 batch 파일 저장

| 메시지 | 원인과 해결 |
| --- | --- |
| `Batch file cannot be saved: Two selected sources use the folder '<이름>'; ...` | 저장할 source 이름이 겹침. 실행은 계속되며 파일만 저장하지 않음. 겹치지 않게 나눠 실행 |
| `Batch file not saved: ...` | 저장 위치의 권한이나 디스크 상태 확인. 실행은 계속됨 |
| 다른 PC에서 GitHub 또는 Bitbucket 인증 실패 | TUI는 한 인증 파일만 쓰므로 저장된 batch의 모든 source가 같은 파일을 가리킴. 서비스별로 `credentials`를 고쳐 다른 파일을 지정 |

## `--status` 결과 해결

| 상태 | 할 일 |
| --- | --- |
| `BEHIND` | batch를 실행하면 fast-forward됨 |
| `AHEAD` | 해당 저장소에서 `git push`. PC를 옮기기 전에 처리 |
| `DIVERGED` | 해당 저장소에서 직접 rebase 또는 merge 후 push. 이 도구는 자동으로 합치지 않음 |
| `MISSING` | batch를 실행하면 clone됨 |
| `SKIP (working tree or index has local changes)` | 변경을 커밋·stash하거나 되돌림 |
| `SKIP (remote URL does not exactly match ...)` | `git remote -v`로 URL 확인. SSH/HTTPS 형식이나 끝의 `.git` 차이도 다른 주소로 봄. batch의 `protocol`과 맞추거나 `git remote set-url` |
| `SKIP (HEAD is detached or unborn)` / `SKIP (missing or ambiguous upstream ...)` | 원격 추적 브랜치로 `git switch`하거나 `git branch --set-upstream-to` |
| `WARN (submodules not initialized ...)` | batch를 실행하거나 `git submodule update --init --recursive` |
| `WARN (uses Git LFS but git-lfs is not installed ...)` | git-lfs 설치 후 `git lfs install`, 해당 저장소에서 `git lfs pull` |
| `EXTRA` | 필요한 저장소면 batch 설정에 추가하고, 아니면 직접 정리. 이 도구는 지우지 않음 |
| `PARTIAL` | 실패한 clone이 남긴 `.clone-*` 임시 폴더. 내용 확인 후 삭제하고 다시 실행 |
| `ERROR` | 표시된 Git 오류 확인. `git status`가 해당 폴더에서 정상 동작하는지 확인 |

`--status`는 fetch하지 않으므로 BEHIND·AHEAD는 마지막 fetch 기준입니다. 최신 원격과 비교하려면 먼저 batch를 실행하세요.

오류를 보고할 때 OS, Python/Git 버전, 실행 명령, 비밀 값을 지운 설정과 로그를 첨부하세요.
username, token, 인증 헤더, 개인 키는 포함하지 마세요.


## SSH 호스트 확인에서 멈춘 것처럼 보일 때

`Are you sure you want to continue connecting (yes/no/[fingerprint])?`는 GitHub 서버의 SSH 호스트 키를
아직 신뢰 목록에 등록하지 않아 SSH가 답변을 기다리는 상태입니다. API 토큰 인증과는 별개입니다.
TUI 실행에서는 이 질문을 기다리지 않고 해당 저장소를 실패로 처리하며 `AUTH / SSH SETUP REQUIRED`를 표시합니다.
기존 batch/-i에서는 Git의 질문이 그대로 나타날 수 있습니다.

같은 실행 계정과 Git이 사용하는 SSH 환경에서 별도로 다음 명령으로 확인하세요.

```bash
ssh -T git@github.com
```

표시된 지문을 [GitHub 공식 호스트 키 지문](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)과
비교하고 일치할 때 승인합니다. 정상 인증 뒤에도 GitHub의 이 테스트 명령은 셸 접근을 제공하지 않으므로 종료 코드 1일 수 있습니다.
설명은 [공식 SSH 연결 테스트](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)를 참고하세요.
Windows에서는 Git 내장 SSH와 Windows OpenSSH가 다를 수 있으므로 Git의 core.sshCommand, GIT_SSH_COMMAND 및 SSH 경로를 확인하세요.
암호화된 개인 키는 실행 전에 SSH agent에 준비하고 HTTPS는 Git Credential Manager에서 인증을 준비하세요.

10초 이상 출력이 없는 경우 대시보드는 마지막 출력 이후 시간을 표시합니다. 출력이 없다는 이유만으로
인증 대기라고 단정하지 않습니다. 네트워크·서버·사용자 정의 credential helper 지연도 가능하며 Q로 중단할 수 있습니다.

[README로 돌아가기](../README.md)
