# Batch 모드 가이드

[README](../README.md) · [설정 항목](CONFIGURATION.md) · [예제](../examples/README.md) · [갱신 정책](SAFETY.md)

batch는 JSON에 지정한 source·프로젝트·저장소를 **화면 선택이나 실행 확인 없이 순서대로 처리**하는 모드입니다.
같은 대상을 반복 동기화하거나 예약 작업·CI에서 실행할 때 사용합니다. 병렬 작업이나 별도 백그라운드 서비스는 아닙니다.

## 목차

- [설정 파일 준비](#설정-파일-준비)
- [실행 순서](#실행-순서)
- [프로젝트별 저장 경로](#프로젝트별-저장-경로)
- [여러 프로젝트와 필터](#여러-프로젝트와-필터)
- [진행률과 종료 코드](#진행률과-종료-코드)
- [자동화와 로그](#자동화와-로그)
- [재실행과 제한](#재실행과-제한)

## 설정 파일 준비

TUI의 `repositories.json`은 username·token만 담습니다. batch에는 **전체 작업 설정**이 필요하므로
`--config batch.json`을 명시하세요. `--batch`만 붙여도 기본 파일명이 batch.json으로 바뀌지는 않습니다.
두 파일을 합치거나 한 파일의 인증 정보를 다른 파일에서 자동으로 가져오지 않습니다.

가장 간단한 예제는 API 인증이 필요 없는 직접 URL 방식입니다.

```json
{
  "destination": "./clones",
  "sources": [
    {
      "name": "personal",
      "provider": "git",
      "repositories": [
        {
          "name": "repo-cloner",
          "url": "https://github.com/park-gwimong/repo-cloner.git"
        }
      ]
    }
  ]
}
```

이 내용을 프로젝트 루트의 `batch.json`으로 저장하면 대상은 `clones/personal/repo-cloner`입니다.
Git URL의 접근 권한은 로컬 Git 인증을 사용합니다.

## 실행 순서

```bash
# 1. 조회와 계획만 확인
python repo_cloner.py --batch --config batch.json --dry-run
# 2. 같은 설정으로 실제 실행 (확인 입력 없음)
python repo_cloner.py --batch --config batch.json
# 3. 저장 루트를 이번 실행만 변경
python repo_cloner.py --batch --config batch.json --destination "D:/Git Copies"
```

설치했다면 `python repo_cloner.py` 대신 `repo-cloner`를 사용할 수 있습니다.
macOS/Linux에서는 환경에 따라 `python3`를 사용하세요. 명령 예제는 프로젝트 루트에서 실행합니다.

1. JSON, source 이름, 필터, 프로젝트 목록과 저장 루트를 검사합니다.
2. 각 source의 저장소를 조회합니다. API provider는 모든 페이지를 순회하고 `git` provider는 JSON의 URL 목록을 읽습니다.
3. include/exclude를 적용하고 전체 실행 대상·예상 동작·경로를 표시합니다.
4. 없는 경로는 clone하고 기존 일반 디렉터리는 안전한 갱신 조건을 검사합니다.
5. 처리 결과를 집계하고 종료 코드를 반환합니다.

batch는 workspace나 프로젝트 목록을 찾아 선택하지 않습니다. 설정의 workspace 및 프로젝트 **키**를 사용합니다.
프로젝트 표시 이름을 키 대신 넣으면 기대한 저장소를 찾지 못할 수 있습니다.

GitHub 개인 계정은 [github-user 예제](../examples/batch.github-user.json)를 사용합니다.
`provider: "github-user"`와 token을 지정하면 본인 소유 저장소를 조회하며 organization 필드는 넣지 않습니다.
계정명 입력은 필요 없고 저장 폴더명은 source.name으로 지정합니다. 조직은 기존 provider github를 사용합니다.

`--dry-run`은 Git 실행·폴더 생성·로컬 갱신 자격 검사를 하지 않습니다. API source는 조회를 위해 네트워크와 인증이 필요합니다.
실행 전 표시되는 `UPDATE?`는 갱신 후보라는 뜻입니다. dry-run 성공만으로 Git 인증이나 실제 갱신 성공이 보장되지는 않습니다.

## 프로젝트별 저장 경로

| batch 설정 | 실제 경로 |
| --- | --- |
| Bitbucket 단일 `project` | `<destination>/<source.name>/<repository>` |
| Bitbucket `projects` 목록 | `<destination>/<source.name>/<PROJECT_KEY>/<repository>` |
| GitHub 조직 | `<destination>/<source.name>/<repository>` |
| GitHub 개인 계정 (`github-user`) | `<destination>/<source.name>/<repository>` |
| 직접 Git URL | `<destination>/<source.name>/<repository.name>` |

TUI의 `<destination>/<프로젝트 표시 이름>/<repository>`와 경로 규칙이 다릅니다.
batch에서도 프로젝트명 바로 아래에 저장하려면 **프로젝트마다 source를 하나씩 만들고 `name`을 프로젝트명으로 설정**하세요.

```json
{
  "destination": "./clones",
  "protocol": "ssh",
  "sources": [
    {
      "name": "관제 시스템",
      "provider": "bitbucket-cloud",
      "workspace": "YOUR_WORKSPACE",
      "project": "CONTROL",
      "username": "you@example.com",
      "token": "YOUR_TOKEN"
    }
  ]
}
```

```text
clones/
└── 관제 시스템/       # source.name
    ├── api/
    └── web/
```

JSON의 상대 destination은 설정 파일 위치 기준입니다. CLI `--destination`은 명령 실행 폴더 기준이며 JSON보다 우선합니다.
생략하면 설정 파일 옆의 `clones`를 사용합니다. `~`는 홈으로 확장하고 `$HOME`·`%USERPROFILE%` 같은 문자열은 확장하지 않습니다.
Windows JSON 경로는 `D:/GitCopies`처럼 슬래시를 사용하면 편합니다.

## 여러 프로젝트와 필터

```json
{
  "destination": "./clones",
  "protocol": "ssh",
  "sources": [
    {
      "name": "company",
      "provider": "bitbucket-cloud",
      "workspace": "YOUR_WORKSPACE",
      "projects": ["APP", "OPS"],
      "username": "you@example.com",
      "token": "YOUR_TOKEN",
      "include": ["api-*", "web-*"],
      "exclude": ["*-archive"]
    }
  ]
}
```

이 예제는 `clones/company/APP/<repo>`와 `clones/company/OPS/<repo>`에 저장합니다.
`project`와 `projects`는 동시에 사용할 수 없으며 `projects`는 비어 있지 않은 고유한 키 목록이어야 합니다.
여러 source를 배열에 추가하면 다른 계정·서비스도 한 번에 처리합니다. API 인증은 source마다 지정합니다.

필터는 API 조회 **후** 저장소 이름에 적용합니다. 대소문자를 구분하는 glob이며 `*`, `?`, `[abc]`를 지원합니다.
include가 없거나 `[]`이면 전체가 후보입니다. include에 일치해도 exclude에 일치하면 제외됩니다.
패턴은 문자열 목록이어야 합니다. 필터 제외는 `skipped`에 포함되며 전부 제외되면 폴더를 만들지 않고 정상 종료합니다.

## 진행률과 종료 코드

```text
Targets: 2 repositories
# | Source / Repository | Action | Destination
1 | company/APP/api-main | CLONE | .../company/APP/api-main
2 | company/OPS/web-admin | UPDATE? | .../company/OPS/web-admin
Progress: 0/2 (0%) RUNNING company/APP/api-main elapsed=0s
Progress: 1/2 (50%) CLONED company/APP/api-main
Progress: 2/2 (100%) UPDATED company/OPS/web-admin
Done: cloned=1 updated=1 unchanged=0 skipped=0 planned=0 failed=0
```

진행률은 **처리 완료한 저장소 수 / 실행 대상 저장소 수**입니다. 실패·건너뜀도 완료 수에 포함합니다.
Git 자체 전송 진행률은 별도로 표시될 수 있습니다. 필터 제외나 source 조회 실패는 대상 분모 밖에서 집계됩니다.

| 결과 | 의미 |
| --- | --- |
| `cloned` | 새 저장소 복제 완료 |
| `updated` | 기존 저장소 fast-forward 완료 |
| `unchanged` | 이미 원격과 같은 상태 |
| `skipped` | 필터 제외, 경로 비대상, 안전 조건 미충족 등으로 건너뜀 |
| `planned` | dry-run의 clone/update 후보 |
| `failed` | 조회 또는 저장소 처리 실패 |

| 종료 코드 | 의미 |
| --- | --- |
| `0` | 실패 없이 종료. skipped만 있어도 0 |
| `1` | 설정 오류, Git 부재, 조회/처리 실패 등 |
| `2` | argparse가 잘못된 CLI 옵션이나 충돌한 모드 옵션을 거절 |
| `130` | Ctrl+C 등 사용자가 중단 |

처리 중 잡힌 source 조회 오류와 저장소별 오류는 실패로 집계하고 나머지를 계속합니다.
시작 단계의 설정 오류는 실행 자체를 중단합니다. 예기치 않은 내부 오류나 강제 프로세스 종료까지 복구하는 것은 아닙니다.
여러 저장소를 하나의 트랜잭션으로 처리하지 않으므로 일부 실패해도 이미 완료한 clone/update는 남습니다.

## 자동화와 로그

batch는 앱의 선택·확인 입력을 없애지만, **Git/SSH의 암호·호스트 키·인증 입력까지 자동 해결하지는 않습니다.**
예약 실행 계정에서 먼저 Git 인증을 준비하세요. 아래 예제는 인증이 준비되지 않으면 프롬프트 대신 실패하도록 설정합니다.

PowerShell:

```powershell
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$env:GIT_SSH_COMMAND = 'ssh -o BatchMode=yes'
python repo_cloner.py --batch --config batch.json *> batch.log
$result = $LASTEXITCODE
exit $result
```

macOS/Linux:

```bash
GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never GIT_SSH_COMMAND='ssh -o BatchMode=yes' \
  python3 repo_cloner.py --batch --config batch.json > batch.log 2>&1
result=$?
exit "$result"
```

`exit` 예제는 독립 실행 스크립트용입니다. 터미널에서 직접 시도할 때는 결과 변수를 출력해 확인할 수 있습니다.
로그에는 저장소·프로젝트·경로가 포함되므로 공유 전에 확인하세요.

cron·Windows 작업 스케줄러에는 Python 실행 파일, 스크립트, 설정 파일, destination의 절대 경로를 지정하는 것이 명확합니다.
Git이 실행 계정의 PATH에 있어야 하며 그 계정의 SSH 키·Git Credential Manager 설정이 사용됩니다.
이 도구 자체에는 스케줄러·작업 잠금·Git 명령의 실행 시간 제한이 없습니다. 같은 출력 경로의 작업을 겹쳐 실행하지 마세요.

## 재실행과 제한

같은 설정으로 다시 실행하면 기존 경로를 검사합니다. clone을 무조건 덮어쓰거나 로컬 변경을 버리지 않습니다.
현재 브랜치와 원격 URL·upstream·작업 트리 상태가 안전할 때만 fast-forward합니다.
진행 중 Git 작업, 로컬 수정, untracked 파일, 원격 URL 차이는 건너뛰는 사유입니다.
`stash`, `reset`, `clean`, `rebase`를 실행하지 않으며 서브모듈도 자동 초기화하지 않습니다.

실패한 clone의 임시 폴더는 `.clone-<임의 값>`으로 남을 수 있습니다. 출력된 경로를 확인하고 원인을 해결하세요.
일부 갱신은 skipped여도 FETCH_HEAD나 tracking metadata를 갱신했을 수 있습니다. 정확한 보호 범위는 [안전 정책](SAFETY.md)을 보세요.
이 도구는 전체 refs를 보관하는 mirror/백업 도구가 아니며 로컬 미커밋 변경을 백업하지 않습니다.

같은 전체 설정을 번호 메뉴로 선택해서 실행하려면 다음을 사용하세요.

```bash
python repo_cloner.py -i --config batch.json --dry-run
python repo_cloner.py -i --config batch.json
```

`-i`의 마지막 확인은 `y`가 실행이고 Enter는 취소입니다. TUI의 Enter 실행과 다릅니다.
`--batch`, `-i`, `--tui`는 상호 배타적입니다.
