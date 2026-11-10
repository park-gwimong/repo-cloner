# 설정 파일 레퍼런스

[README](../README.md) · [batch 실행](BATCH.md) · [JSON 예제](../examples/README.md)

## 두 가지 설정 형식

| 구분 | TUI (기본) | batch / 번호 입력 모드 |
| --- | --- | --- |
| 권장 파일 | repositories.json | batch.json |
| 최상위 필드 | username, token만 허용 | credentials, destination, protocol, layout, submodules, sources |
| 인증 위치 | 최상위 | 참조한 인증 파일 또는 sources의 각 항목 |
| 작업 대상·경로 | TUI에서 입력·선택 | 파일에서 읽음 |
| 저장·파일 병합 | 선택하면 batch 파일로 저장 | `credentials`로 지정한 인증 파일만 읽음 |

JSON 파일은 UTF-8이며 BOM이 있어도 읽습니다. 주석과 trailing comma는 허용하지 않습니다.
알 수 없는 전체 설정 필드가 모두 엄격하게 거절되는 것은 아닙니다. 아래 문서화된 필드만 사용하세요.

## TUI 인증

```json
{"username": "you@example.com", "token": "YOUR_TOKEN"}
```

Bitbucket Cloud는 두 값을 Basic 인증에 사용합니다. GitHub·Bitbucket Server TUI는 token만 Bearer 인증에 사용합니다.
token만 있으면 Bearer 인증, `{}`는 익명 조회·직접 URL 용도입니다. username만 있으면 오류입니다.
지정한 값은 비어 있지 않은 문자열이어야 하며 제어 문자를 넣을 수 없습니다.

## Batch 최상위 필드

| 필드 | 형식 / 기본값 | 설명 |
| --- | --- | --- |
| `credentials` | 문자열 / 없음 | 모든 source의 기본 인증 파일 경로. 설정 파일 기준 상대 경로, `~` 지원 |
| `destination` | 문자열 / `./clones` | 설정 파일 기준 저장 루트. CLI --destination이 우선 |
| `protocol` | `ssh` 또는 `https` / `ssh` | API provider의 clone URL 형식 |
| `submodules` | `true` / `false` / `false` | 서브모듈 초기화 기본값. source별 `submodules`가 우선 |
| `layout` | `source` 또는 `project` / `source` | 저장 폴더 규칙. `project`는 TUI와 같은 경로 ([batch 가이드](BATCH.md#tui와-같은-경로-쓰기-layout-project)) |
| `sources` | 비어 있지 않은 객체 배열 / 필수 | 순서대로 실행할 연결 및 대상 |

## Source 공통 필드

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `name` | 필수 문자열 | 저장 폴더 이름. source 간 대소문자를 무시하고 고유해야 함 |
| `provider` | 필수 문자열 | github, github-user, bitbucket-cloud, bitbucket-server, git |
| `include` | 문자열 배열 / `[]` | 저장소 이름 glob. 빈 목록이면 전체 후보 |
| `exclude` | 문자열 배열 / `[]` | 저장소 이름 glob. include보다 우선 |
| `credentials` | 선택 문자열 | 이 source만 쓸 인증 파일 경로. 최상위 credentials보다 우선 |
| `submodules` | 선택 `true`/`false` | 이 source의 서브모듈 초기화 여부. 최상위 값보다 우선 |
| `skipArchived` | 선택 `true`/`false` / `false` | GitHub 전용. 보관(archived)된 저장소 제외 |
| `skipForks` | 선택 `true`/`false` / `false` | GitHub 전용. fork한 저장소 제외 |
| `token` | 선택 문자열 | 실제 API 토큰. 환경변수 이름이 아님 |
| `username` | 선택 문자열 | token과 함께 있으면 Basic 인증. token 없이 단독 사용 불가 |

batch의 기존 API provider는 두 인증 필드가 있으면 Basic, token만 있으면 Bearer 인증입니다.
`github-user`는 token이 필수이며 username 유무와 관계없이 Bearer 인증을 사용합니다.
GitHub·Bitbucket Server PAT 예제는 username 없이 token만 지정합니다. 직접 URL provider는 API 인증을 사용하지 않습니다.
`tokenEnv`, `usernameEnv`, `.env` 기반 API 인증은 지원하지 않습니다.

## 인증 파일 참조 (`credentials`)

batch 파일에 토큰을 넣지 않으려면 TUI와 같은 형식(username·token만 있는 JSON)의 파일을 참조합니다.

```json
{
  "credentials": "./repositories.json",
  "destination": "./clones",
  "sources": [
    {"name": "관제 시스템", "provider": "bitbucket-cloud", "workspace": "YOUR_WORKSPACE", "project": "CONTROL"},
    {"name": "my-org", "provider": "github", "organization": "YOUR_ORGANIZATION", "credentials": "~/secrets/github.json"}
  ]
}
```

- 참조한 파일의 값은 TUI와 같은 규칙으로 적용합니다. token은 모든 API provider에, username은 Bitbucket Cloud에만 사용합니다.
- 우선순위: source의 `token`/`username` 직접 지정 또는 source `credentials` → 최상위 `credentials`.
- 한 source에 `credentials`와 `token`/`username`을 함께 쓰면 오류입니다. `git` provider는 인증 파일을 읽지 않습니다.
- 파일이 없거나 username·token 외의 필드가 있으면 시작 단계에서 중단합니다. 오류 메시지에 인증 값은 표시하지 않습니다.

TUI 확인 화면 다음에 `Save batch file`을 선택하면 이 형식의 batch 파일을 자동으로 만듭니다.
저장 범위는 둘 중 하나를 고릅니다.

| 범위 | API source | 직접 URL source |
| --- | --- | --- |
| 지금 고른 저장소만 | 고른 이름을 `include`에 고정 | 고른 URL만 `repositories`에 기록 |
| 프로젝트·계정 전체 | `include` 없음. 나중에 생긴 저장소도 포함 | TUI에서 입력한 URL 전체 기록 |

include 이름의 `*`, `?`, `[`는 glob이 아닌 문자로 처리되도록 `[*]`처럼 기록합니다.

## Provider별 필드

| provider | 필수 항목 | 선택 항목 / 범위 |
| --- | --- | --- |
| `github` | `organization` | `apiUrl` 기본 https://api.github.com. GitHub Enterprise API URL 지정 가능 |
| `github-user` | `token` | 토큰 사용자가 소유한 저장소. `apiUrl`은 GitHub와 동일. organization 지정 불가 |
| `bitbucket-cloud` | `workspace`, `project` 또는 `projects` | workspace 식별자와 정확한 프로젝트 키 |
| `bitbucket-server` | `baseUrl`, `project` 또는 `projects` | HTTPS 서버 주소. context path 포함 가능 |
| `git` | `repositories` | 비어 있지 않은 name·url 객체 배열 |

`-i`는 Bitbucket 프로젝트를 조회해서 선택하므로 project/projects를 생략할 수 있습니다.
batch는 프로젝트 키를 미리 지정해야 합니다. `projects`는 Bitbucket에만 사용할 수 있으며 `project`와 동시에 지정하지 않습니다.
키 목록의 빈 값·중복은 오류입니다. 단일 project와 projects 목록은 저장 경로가 다릅니다.

`github`는 조직 저장소, `github-user`는 인증된 사용자 본인 소유 저장소를 조회합니다.
개인 모드는 공개·비공개 여부와 관계없이 토큰으로 조회 가능한 항목만 표시하며 조직·다른 소유자의 협업 저장소는 제외합니다.
GitHub Projects 보드는 지원하지 않습니다. TUI는 `/user`로 계정명을 확인해 폴더 이름으로 사용하고,
batch는 다른 provider처럼 source.name을 폴더 이름으로 사용합니다.
개인 batch 예제는 [batch.github-user.json](../examples/batch.github-user.json)을 참고하세요.

## 서브모듈과 Git LFS

`"submodules": true`이면 clone에 `--recurse-submodules`를 사용하고, 기존 저장소는 안전 검사와 fast-forward(또는 이미 최신 확인)가
끝난 뒤 `git submodule update --init --recursive`를 실행합니다. 작업 트리가 깨끗한 경우에만 이 단계에 도달합니다.
서브모듈 단계가 실패하면 해당 저장소를 `failed`로 집계합니다. 이미 끝난 fast-forward는 되돌리지 않습니다.
서브모듈 URL 접근에도 로컬 Git 인증이 필요하며, `file`·`ext` 같은 프로토콜 허용 여부는 Git 기본 정책을 따릅니다.

Git LFS는 별도 설정이 없습니다. git-lfs가 설치되어 있으면 Git이 clone·checkout 때 자동으로 파일을 받습니다.
루트 `.gitattributes`에 `filter=lfs`가 있는데 git-lfs가 없으면 clone 직후와 `--status`에서 경고합니다.
git-lfs를 설치한 뒤 해당 저장소에서 `git lfs pull`을 실행하세요.

## 직접 URL

```json
{
  "name": "personal",
  "provider": "git",
  "repositories": [
    {"name": "local-folder", "url": "git@github.com:OWNER/REPOSITORY.git"}
  ]
}
```

repositories의 name은 로컬 폴더명이며 URL에서 추측하지 않습니다. 동일 source 안에서 대소문자만 다른 이름도 중복입니다.
HTTPS, ssh://, git@host:path 형식을 지원합니다. 로컬 경로·file://·실행형 remote helper는 지원하지 않습니다.
직접 지정한 URL에는 전역 protocol이 적용되지 않습니다. HTTPS 사용자 정보·비밀번호·토큰을 URL에 넣지 마세요.

## 경로와 이름

source.name, 프로젝트 키, 저장소 폴더명에는 `..`, `/`, `\`, Windows 예약 이름, 끝 점·공백 등을 사용할 수 없습니다.
TUI의 프로젝트 표시 이름도 같은 폴더명 검사를 받습니다. TUI는 표시 이름을 자동 변환하지 않습니다.

| 입력 | 기준 |
| --- | --- |
| JSON destination의 상대 경로 | JSON 파일이 있는 폴더 |
| CLI --destination 상대 경로 | 현재 작업 디렉터리 |
| TUI에서 편집한 상대 경로 | 현재 작업 디렉터리 |
| 절대 경로 | 그대로 사용 |
| `~` | 사용자 홈으로 확장 |
| `$HOME`, `%USERPROFILE%` 문자열 | JSON에서 확장하지 않음 |

설정 파일을 다른 폴더로 옮기면 JSON 상대 destination의 실제 위치도 바뀝니다.
source.name이나 destination을 변경해도 기존 저장소를 자동 이동하지 않습니다.

## 인증 권한과 저장

Bitbucket Cloud TUI workspace 조회에는 `read:workspace:bitbucket`, 저장소·프로젝트 탐색에는 `read:repository:bitbucket`이 필요합니다.
batch는 workspace 목록을 조회하지 않으므로 이 기능을 위해 workspace 읽기 scope를 추가할 필요는 없습니다.
API 토큰의 권한과 계정 자체의 접근 권한을 모두 충족해야 합니다.
Git clone/update 인증은 SSH 키·로컬 Git 자격 증명으로 별도 처리합니다.

루트 repositories.json·batch.json은 Git 제외 대상입니다. 인증을 참조로만 둔 batch 파일은 공유해도 되지만 참조된 인증 파일은 공유하지 마세요. 다른 경로·이름의 개인 설정은 직접 제외하고 파일 접근 권한도 관리하세요.
API는 HTTPS만 허용하고 리다이렉트를 따르지 않습니다. 인증서를 우회하는 옵션은 없습니다.
