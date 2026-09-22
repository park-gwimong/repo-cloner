# Legacy batch configuration reference

Run the following commands from the project root. Full source settings belong in a separate batch.json file. The default repositories.json is now authentication-only; launch without flags for TUI setup.

# Project Repo Cloner

GitHub 조직·Bitbucket 프로젝트 또는 직접 지정한 Git URL 목록을 일괄 clone하고 안전하게 갱신하는 Python CLI입니다.
콘솔에서 프로젝트와 저장소를 조회해 선택하거나, JSON에 지정한 여러 프로젝트를 일괄 실행할 수 있습니다.
실행 전 대상과 저장 경로를 표시하고, 처리 중 완료 개수·진행률·현재 저장소·경과 시간을 출력합니다.
Python 3.10 이상과 Git이 필요하며, 런타임 외부 라이브러리는 없습니다. Windows, macOS, Linux에서 사용할 수 있습니다.

## 빠른 시작

`repositories.batch.example.json`을 `batch.json`으로 복사한 뒤 사용할 source만 남기고 값을 수정하세요.

```json
{
  "destination": "./clones",
  "protocol": "ssh",
  "sources": [
    {
      "name": "my-workspace",
      "provider": "bitbucket-cloud",
      "workspace": "my-workspace",
      "projects": ["PROJECT_A", "PROJECT_B"],
      "username": "you@example.com",
      "token": "YOUR_TOKEN"
    }
  ]
}
```

API 인증 정보는 각 source의 `username`과 `token`에 직접 입력합니다.
Bitbucket Cloud API 토큰은 `username`에 토큰을 발급한 계정 이메일을 입력합니다.
`.env`와 환경변수는 API 인증에 사용하지 않습니다. `batch.json`은 Git 제외 대상입니다.

`PROJECT_A`, `PROJECT_B`는 실제 프로젝트 키로 바꾸세요. 대화형 모드에서 프로젝트를 선택할 때는
`projects`를 생략할 수 있습니다. 인증 값이 들어 있는 다른 이름의 설정 파일도 커밋하지 마세요.

실행 코드는 모든 OS에서 동일합니다. 환경에 따라 `python` 대신 `python3`를 사용하세요.

```bash
# 프로젝트와 저장소를 목록에서 선택한 뒤 미리 보기
python repo_cloner.py --config batch.json -i --dry-run

# 목록에서 선택 → 대상 확인 → y 입력 → clone 또는 안전한 갱신
python repo_cloner.py --config batch.json -i
```

여러 source가 있으면 source부터 선택합니다. 번호는 `1,3-5`, 전체 선택은 `all`, 취소는 `q`입니다.
실행 확인에서 Enter만 누르면 취소합니다. 선택 결과는 JSON에 저장하지 않습니다.

JSON의 `project` 또는 `projects`에 지정한 대상 전체를 확인 입력 없이 실행하려면 `--batch`를 지정하세요.

```bash
python repo_cloner.py --config batch.json --dry-run --batch
python repo_cloner.py --config batch.json --batch
```

CLI 명령으로 설치해서 사용할 수도 있습니다.

```bash
python -m pip install .
repo-cloner --config batch.json -i --dry-run
repo-cloner --config batch.json -i
```

## 실행 옵션

| 옵션 | 동작 |
| --- | --- |
| `--config PATH` | 읽을 전체 설정 JSON 파일. `--config batch.json`으로 명시 |
| `--batch` | 전체 설정을 사용해 확인 입력 없이 실행 |
| `--interactive`, `-i` | source·프로젝트·저장소를 번호로 선택하고 실행 전 확인 |
| `--dry-run` | API 조회와 대상 표시만 수행. Git 실행·폴더 생성·저장소 변경 없음 |
| `--destination PATH` | JSON의 저장 루트를 덮어씀. 상대 경로는 현재 폴더 기준 |
| `--help`, `-h` | 도움말 표시 |

`-i`와 `--dry-run`은 함께 사용할 수 있습니다. 자동화에서는 `--batch`로 실행하세요.

## 어디에서 가져와 어디에 저장하나요?

이 도구의 복제 대상은 **원격 Git 저장소**입니다. 일반 로컬 폴더 복사나
미커밋 작업까지 포함하는 백업 도구는 아닙니다.

```text
단일 project 또는 GitHub / 직접 Git URL:
  저장 루트 / source.name / 저장소 이름

projects 목록:
  저장 루트 / source.name / 프로젝트 키 / 저장소 이름

D:/GitCopies/
└── personal/                  ← source.name
    └── repo-cloner/            ← 원격 저장소 이름 또는 직접 지정한 name
        ├── .git/
        └── ...
```

대화형 모드에서 설정의 단일 `project`와 같은 프로젝트를 선택하면 기존 경로를 유지합니다.
그 외 프로젝트는 프로젝트 키별 하위 폴더에 저장합니다. 실제 적용 경로는 실행 전 대상 표에서 확인하세요.

| 지정 방법 | 상대 경로 기준 | 예 |
| --- | --- | --- |
| JSON의 `destination` | 설정 파일이 있는 폴더 | `"destination": "../copies"` |
| CLI의 `--destination` | 명령을 실행한 현재 폴더 | `--destination ./copies` |
| 절대 경로 | 그대로 사용 | Windows `D:/GitCopies`, macOS `/Users/me/GitCopies`, Linux `/home/me/GitCopies` |

`--destination`이 JSON보다 우선합니다. 둘 다 생략하면 설정 파일 옆 `clones`가
저장 루트입니다. `~`는 사용자 홈으로 확장하지만 JSON 안의 `$HOME`·`%USERPROFILE%`
같은 환경변수 표현은 치환하지 않습니다. JSON의 Windows 경로는 `D:/GitCopies`처럼
슬래시를 쓰거나 `D:\\GitCopies`처럼 역슬래시를 이스케이프하세요.

예를 들어 `C:/settings/batch.json`의 `destination`이 `./clones`라면,
어느 폴더에서 실행해도 `C:/settings/clones` 아래에 저장됩니다.
설정 파일을 다른 폴더로 옮기면 상대 저장 위치도 달라집니다.

```powershell
# Windows: 공백이 있는 경로는 따옴표로 감쌉니다.
python repo_cloner.py --config C:/settings/batch.json --destination "D:/Git Copies" --dry-run --batch
```

```bash
# macOS / Linux: 사용자 홈 아래에 저장
python3 repo_cloner.py --config ./batch.json --destination ~/GitCopies --dry-run --batch
```

저장 루트나 `source.name`을 바꾸면 **기존 폴더를 이동하지 않고 새 경로를 대상으로**
실행합니다. 같은 경로를 다시 사용하면 아래의 안전한 갱신 정책을 적용합니다.

## 개별 저장소 URL로 시작하기

개인 계정 저장소나 일부 저장소만 복제하려면 다음 내용을 별도 설정 파일로 저장하세요.
`provider: "git"`은 목록 조회 API나 API 토큰 없이 지정된 URL을 사용합니다.
실제 복제·갱신에는 여전히 Git과 해당 URL의 접근 권한이 필요합니다.

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

```bash
# 위 JSON을 personal.json에 저장한 경우
python repo_cloner.py --config personal.json --dry-run --batch
python repo_cloner.py --config personal.json --batch
```

- `repositories`는 비어 있지 않은 목록이며 각 항목의 `name`, `url`은 필수입니다.
- `name`은 로컬 폴더 이름입니다. 원격 이름과 다르게 지정할 수 있으며 URL에서 추측하지 않습니다.
- 같은 source 안에서 대소문자만 다른 이름도 중복으로 거절합니다.
  `../repo`, `a/b` 같은 경로를 `name`으로 지정할 수 없습니다.
- 지원 URL은 `https://host/owner/repo.git`, `ssh://git@host/owner/repo.git`,
  `git@host:owner/repo.git` 형태입니다. 로컬 경로·`file://`·실행형 remote helper는 거절합니다.
- 이 모드에서는 전역 `protocol`로 URL을 바꾸지 않습니다. HTTPS/SSH URL을 그대로 사용합니다.
  비밀번호나 HTTPS 사용자 정보·토큰을 URL에 넣지 말고 Git 인증 설정을 사용하세요.
- source 목록 안에서 다른 provider와 함께 사용할 수 있습니다.

## 콘솔에서 목록 조회하고 선택하기

콘솔에서 직접 목록을 조회하고 선택하려면 대화형 모드를 사용하세요.

```powershell
python repo_cloner.py --config batch.json --interactive
# 선택과 미리 보기만 수행
python repo_cloner.py --config batch.json -i --dry-run
```

1. source가 여러 개면 사용할 source를 선택합니다.
2. Bitbucket의 접근 가능한 프로젝트 목록을 조회하고 프로젝트를 선택합니다.
3. 선택한 프로젝트의 저장소 목록에서 실행할 저장소를 선택합니다.
4. 최종 대상과 저장 경로를 확인하고 `y`를 입력하면 실행합니다.

선택 입력은 `1,3-5`(복수 번호·범위), `all`(전체), `none`(선택 안 함), `q`(취소)를 지원합니다.
잘못된 번호는 다시 입력받습니다. 실행 확인의 기본값은 취소이며, 입력 종료나 Ctrl+C로도 취소할 수 있습니다.
`--dry-run`은 실행 확인 없이 선택 결과를 미리 보기로 출력합니다.

대화형 모드에서는 설정의 `project`/`projects` 목록 밖의 프로젝트도 조회·선택할 수 있으며,
두 필드 모두 생략해도 됩니다. 선택 결과는 이번 실행에만 적용하고 JSON을 수정하지 않습니다.
Cloud 프로젝트 목록은 접근 가능한 저장소에서 수집하므로 별도 프로젝트 조회 권한이 필요 없으며,
빈 프로젝트나 접근 가능한 저장소가 없는 프로젝트는 표시되지 않습니다.
프로젝트 키·이름과 다음 페이지 정보만 요청해 응답 크기를 줄이며, 조회 중에는 현재 페이지와 발견한 프로젝트 수를 표시합니다.
Server / Data Center는 프로젝트 조회 API를 사용합니다.
GitHub와 직접 Git URL source는 저장소 선택 단계로 진행합니다. 기존 include/exclude 필터는 계속 적용됩니다.

설정에 단일 `project`가 있고 그 프로젝트를 선택하면 기존 저장 경로를 유지합니다.
그 외 프로젝트는 `<destination>/<name>/<project>/<repository>`에 저장합니다.
`--batch`를 지정하면 기존 설정 기반 일괄 실행 방식을 사용합니다.

## 여러 프로젝트 일괄 실행하기

Bitbucket Cloud와 Server / Data Center는 한 source에 여러 프로젝트 키를 지정할 수 있습니다.
인증 정보와 이름 필터는 해당 프로젝트들에 공통으로 적용합니다.

```json
{
  "name": "pabloair",
  "provider": "bitbucket-cloud",
  "workspace": "pabloair",
  "projects": ["SDSP", "IADS"],
  "username": "you@example.com",
  "token": "YOUR_TOKEN"
}
```

`projects`는 비어 있지 않은 프로젝트 키 목록이며, `project`와 동시에 지정할 수 없습니다.
프로젝트 키의 대소문자를 정확히 입력하세요. 중복 키와 폴더 이름으로 사용할 수 없는 키는 거절합니다.
여러 프로젝트 형식은 `<destination>/<name>/<project>/<repository>`에 저장합니다.
기존 단일 `project` 형식은 `<destination>/<name>/<repository>` 경로를 유지합니다.
기존 저장소가 있다면 설정 형식을 바꾸기 전에 경로 차이를 확인하세요.
서로 다른 계정·workspace·서비스는 `sources`에 별도 항목으로 추가합니다.

## 실행 대상과 진행률

실행할 source·프로젝트를 조회하고 이름 필터와 대화형 선택을 적용한 뒤,
**첫 clone/update 전에 전체 대상 표**를 표시합니다.
표에는 저장소, CLONE/UPDATE?/SKIP 구분, 저장 경로가 나옵니다.
일괄 모드는 확인 입력 없이 이어서 실행하고, 대화형 모드는 `y` 입력 후 실행합니다.
미리 보기만 하려면 `--dry-run`을 사용하세요. UPDATE?는 실행 시 안전 조건을 검사할 갱신 후보입니다.

```text
Targets: 2 repositories
# | Source / Repository | Action | Destination
1 | pabloair/SDSP/api | CLONE | .../pabloair/SDSP/api
2 | pabloair/IADS/web | UPDATE? | .../pabloair/IADS/web
Progress: 0/2 (0%) RUNNING pabloair/SDSP/api elapsed=0s
Progress: 1/2 (50%) CLONED pabloair/SDSP/api
Progress: 2/2 (100%) UPDATED pabloair/IADS/web
```

전체 진행률은 **처리 완료한 저장소 수 / 대상 저장소 수**입니다. 실패·건너뜀도 처리 완료로 집계하므로
100%가 모든 저장소의 성공을 뜻하지는 않습니다. 최종 `Done` 집계를 확인하세요.
처리 중에는 1초마다 현재 저장소와 경과 시간을 출력하며, clone 중에는 Git 전송 진행률도 표시합니다.
조회 실패와 이름 필터 제외 항목은 대상 수에 포함되지 않고 최종 failed/skipped 집계에 포함됩니다.
일부 프로젝트 조회에 실패해도 다른 프로젝트는 계속 처리합니다.

대화형 저장소 목록에서 선택하지 않은 항목도 `skipped`로 집계합니다.

| 최종 집계 | 의미 |
| --- | --- |
| `cloned` | 새로 복제한 저장소 |
| `updated` | 기존 브랜치를 fast-forward로 갱신한 저장소 |
| `unchanged` | 갱신할 새 커밋이 없는 저장소 |
| `skipped` | 필터·선택에서 제외했거나 안전 조건 때문에 건너뛴 저장소 |
| `planned` | dry-run에서 확인한 실행 후보 |
| `failed` | 프로젝트·저장소 목록 조회 또는 저장소 처리 실패 |

## 이름으로 저장소 필터링하기

모든 source에서 `include`와 `exclude`로 **저장소 이름**을 필터링할 수 있습니다.
API provider는 조회된 이름/slug, `git` provider는 직접 지정한 `name`을 비교합니다.

```json
{
  "name": "team",
  "provider": "github",
  "organization": "YOUR_ORGANIZATION",
  "token": "YOUR_TOKEN",
  "include": ["api-*", "web-?"],
  "exclude": ["*-old", "*-archive"]
}
```

- 패턴은 `*`, `?`, `[abc]`를 지원하는 glob이며 정규식이 아닙니다.
  Windows에서도 대소문자를 구분합니다.
- `include`가 생략되거나 `[]`이면 전체가 후보입니다. 값이 있으면 하나 이상 일치해야 합니다.
- `exclude`는 **항상 우선**합니다. 두 규칙에 모두 맞으면 제외합니다.
- 위 예에서 `api-core`, `web-a`는 선택되고 `api-old`, `notes`, `API-extra`는 제외됩니다.
- 문자열 하나가 아니라 문자열 목록을 사용하세요. `"include": "api-*"`는 오류입니다.
- 제외한 저장소는 clone/update하지 않고 `skipped`로 집계합니다.
  모두 제외되어도 정상 종료(0)하며 저장 폴더를 만들지 않습니다.
- API provider의 필터는 **목록 조회 후** 적용합니다. API 접근 권한이나 페이지 조회를 생략하지 않습니다.

## 실행 전 원본과 최종 경로 확인하기

`--dry-run`은 저장 루트와 원격 URL → 로컬 경로를 표시합니다.

```text
Destination: D:\GitCopies
[personal] Found 1 repositories
PLAN  CLONE https://github.com/park-gwimong/repo-cloner.git -> D:\GitCopies\personal\repo-cloner
```

`CLONE`은 없는 경로, `UPDATE?`는 이미 있는 일반 디렉터리의 갱신 후보입니다.
`UPDATE?`는 원격 일치·로컬 수정 여부 등 **갱신 자격을 검사했다는 뜻이 아닙니다**.
파일·링크 같은 비대상이나 이름 필터 제외 항목은 `SKIP`으로 표시됩니다.
Git 실행과 폴더 생성은 없으며 API provider만 목록 조회를 위해 네트워크를 사용합니다.
경로와 대상을 확인한 뒤 같은 명령에서 `--dry-run`을 빼면 실제 실행합니다.

## 지원 서비스

| provider | 조회 단위 | 필수 설정 | API 인증 |
| --- | --- | --- | --- |
| `git` | 직접 지정한 URL 목록 | `repositories`: `name`·`url` 목록 | API 인증 없음; Git 접근 권한 필요 |
| `github` | GitHub Organization | `organization` | `token`: PAT 등 |
| `bitbucket-cloud` | workspace 안의 프로젝트 | `workspace`, `project` 또는 `projects` | `username`: 이메일, `token`: API 토큰 |
| `bitbucket-server` | Server / Data Center 프로젝트 | `baseUrl`, `project` 또는 `projects` | `token`: 개인 액세스 토큰 |

Bitbucket의 `project`/`projects`는 일괄 모드에서 필요하며, 대화형 모드에서는 생략할 수 있습니다.
같은 연결의 여러 프로젝트는 `projects`로 지정하고, 다른 계정·workspace·서비스는 `sources`에 추가합니다.
source마다 고유한 `name`을 지정하세요.
예제 파일에는 세 API 서비스와 직접 URL 지정 예제가 있습니다. 사용할 source만 남기세요.

각 source에 인증 값을 직접 지정합니다. 여러 source는 같은 값을 사용하거나 서로 다른 값을 사용할 수 있습니다.

- `destination`: 저장 위치. 상대 경로는 설정 파일 위치 기준입니다.
- `protocol`: `ssh`(기본값) 또는 `https`.
- `project`: Bitbucket의 표시 이름이 아닌 프로젝트 **키**.
- `projects`: 여러 프로젝트 키의 목록. `project`와 동시에 지정할 수 없습니다.
- `token`, `username`: 인증에 사용할 **실제 값**. 둘 다 생략하면 익명 조회, `token`만 있으면 Bearer 인증, 둘 다 있으면 Basic 인증을 사용합니다. 빈 값은 허용하지 않습니다. 이전 `tokenEnv`·`usernameEnv` 설정은 오류로 안내합니다.
- `github.apiUrl`: Enterprise 사용 시 `https://github.example.com/api/v3` 지정.
- `bitbucket-server.baseUrl`: 예: `https://bitbucket.example.com` 또는 context path를 포함한 주소.
- 공개 저장소를 익명 조회하려면 `token`을 생략합니다. Bearer 인증을 사용하려면 `username`을 생략합니다.

`github` provider는 Organization 전체를 조회한 뒤 이름 필터를 적용합니다. GitHub Projects 보드 및 개인 계정 단위 자동 조회는 지원하지 않습니다. 개인 저장소는 `git` provider로 URL을 지정할 수 있습니다. 토큰 권한으로 조회 가능한 저장소만 포함되며, 모든 페이지를 순회합니다. 조직의 토큰 승인이나 SSO 설정에 따라 접근 범위가 제한될 수 있습니다.

**목록 조회 인증과 Git clone 인증은 별개입니다.** SSH는 제공자에 등록한 SSH 키, HTTPS는 Git Credential Manager 등 로컬 Git 인증 설정을 사용합니다. 토큰을 Git URL에 삽입하지 않습니다.

## Bitbucket 인증과 조회 문제 해결

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

## 재실행과 안전한 갱신

결과는 실행 전 대상 표의 경로에 저장됩니다. 여러 프로젝트 형식에서는 source 이름 아래에
프로젝트 키 폴더가 추가됩니다. 없는 경로는 clone하고,
이미 있는 **일반 디렉터리**는 안전 조건을 모두 만족할 때만 현재 브랜치의 명시적
upstream을 갱신합니다. 별도 `--update` 옵션은 없습니다. 실행 중 같은 저장소나
출력 위치를 다른 프로세스에서 변경하지 마세요. 이 도구는 경쟁 상태를 원자적으로
잠그지 않습니다.

기존 저장소를 갱신하려면 다음 조건이 모두 필요합니다.

- `.git` worktree이며 현재 브랜치에 커밋과 단일 원격 upstream이 있어야 합니다.
- `branch.<현재 브랜치>.remote/merge`가 하나의 원격 `refs/heads/*`를 가리키고,
  원격 fetch refspec에서 실제로 하나의 직접 `refs/remotes/*` tracking ref로
  해석되어야 합니다. 설정에 없는 목적지를 임의로 만들지 않으며 custom tracking
  경로도 안전한 단일 매핑이면 사용할 수 있습니다. detached/unborn HEAD, local
  upstream, 복수/누락/기호식 매핑, 진행 중 merge/rebase/cherry-pick/revert/bisect,
  index 잠금은 건너뜁니다.
- 현재 upstream 원격의 fetch URL 하나가 API가 반환한 clone URL과 **엄격히 같은
  형식과 주소**여야 합니다. HTTPS끼리, `ssh://`끼리, SCP형(`git@host:path`)끼리만
  비교합니다. ASCII host 대소문자와 HTTPS 443/SSH 22의 생략만 정규화하며,
  `.git`, 끝 `/`, 경로 대소문자/encoding, SSH 사용자, alias, 식별을 바꾸는
  `insteadOf`, query/fragment/userinfo 차이는 추정하지 않습니다. 다르면
  `skipped`입니다.
  `pushurl`은 비교하지 않습니다.

예를 들어 `https://example.com/org/repo`와
`https://EXAMPLE.com:443/org/repo`는 같은 주소로 보지만,
`https://example.com/org/repo.git`, `ssh://example.com/org/repo`,
`git@example.com:org/repo`, `https://example.com/org/repo/`는 각각 다른
표현이므로 갱신하지 않습니다.
- staged/unstaged/삭제/untracked 파일, dirty submodule, assume-unchanged/
  skip-worktree 인덱스 항목이 없어야 합니다.

조건을 통과하면 현재 upstream 한 개만 목적지 ref 없이 `FETCH_HEAD`로 가져옵니다.
`--refmap=`, `--no-tags`, `--no-prune`으로 다른 branch/tag/tracking ref의 변경을
막으며 서브모듈은 초기화하거나 재귀 fetch하지 않습니다. 가져온 단일 커밋을
검증한 뒤 기존 tracking ref가 검사 당시 값일 때만 원자적 비교·교환으로 갱신합니다.
현재 로컬 브랜치는 그 정확한 커밋 ID까지 fast-forward만 수행합니다.
local-only 또는 diverged 커밋은 보존하고 `skipped`로 끝납니다.
원격 이력이 교체되거나 되감겨도 로컬 커밋은 버리지 않습니다. 다만 `skipped`여도
`FETCH_HEAD`와 해당 tracking metadata/OID는 새 원격 상태를 반영할 수 있습니다.
작업 파일, index, 로컬 branch 커밋은 보호됩니다.
갱신 명령은 저장된 hook 설정을 바꾸지 않고 작업 트리 밖의 빈 임시 hook 디렉터리를
사용합니다.

`--dry-run`은 API 목록 조회만 수행합니다. Git 실행, 임시 디렉터리 생성, clone,
worktree 검사, 기존 디렉터리 갱신 자격 판정은 하지 않습니다. 없는 clone 대상과
기존 일반 디렉터리는 `planned`, 파일/심볼릭 링크/junction 같은 명백한 비대상은
`skipped`입니다.

마지막에 저장소당 한 번씩 다음 여섯 개 집계를 표시합니다.
`cloned`, `updated`, `unchanged`, `skipped`, `planned`, `failed`.
목록 조회 실패도 `failed`에 포함하며 한 source의 실패 뒤에도 나머지를 계속
처리합니다. 실패가 있으면 종료 코드 1, 안전하게 건너뛴 경우는 0, 사용자가
선택 중 `q`·입력 종료·Ctrl+C로 중단하면 130입니다. 실행 확인에서 `n` 또는 Enter를 입력하면
저장소를 변경하지 않고 종료하며, 앞선 조회 실패가 없으면 0, 있으면 1입니다. 실패한 clone은 `.clone-<임의 값>` 임시 폴더를 남길 수
하므로 출력된 경로를 확인한 뒤 원인을 해결하고 다시 실행하세요. 갱신은 stash,
reset, clean, rebase를 하지 않으며 서브모듈도 자동 초기화하지 않습니다. 갱신용
임시 hook 디렉터리 정리에 실패하면 오류와 해당 절대 경로를 출력하며, 이미 수행된
fast-forward를 되돌리지 않습니다.

clone은 `.clone-<임의 값>` 폴더에서 먼저 실행됩니다. clone 실패 시 해당 경로를 출력하고 재실행 시 다시 시도합니다. 성공 후 최종 폴더로 내용을 옮기는 도중 중단되면 최종 폴더도 불완전할 수 있습니다. 출력된 경로를 확인하고 불완전한 폴더를 정리한 후 다시 실행하세요. 실행 중 같은 출력 위치를 다른 프로세스에서 변경하지 마세요.

API 통신은 HTTPS만 허용하며 인증 정보 보호를 위해 리다이렉트를 따르지 않습니다. 사내 인증서는 운영체제/Python에서 신뢰하도록 설정해야 합니다.

## 개발 및 기여

```bash
python -m unittest discover -s tests -v
```

테스트는 실제 서비스나 토큰 없이 API 페이지 순회, 인증, dry-run, 엄격한 원격
식별, 실제 임시 Git 원격/작업 트리의 fetch·fast-forward, 로컬 변경 보존과 실패 후
계속 진행을 검증합니다. 여러 프로젝트 분리, 진행률 출력, 대화형 번호·범위 선택과 취소도 검증합니다.
테스트를 실행하려면 Git이 PATH에 있어야 하며 서브모듈이나
외부 서비스는 사용하지 않습니다. GitHub Actions에서도 Python 3.10/3.13과
Windows/Linux/macOS 조합으로 실행합니다.

변경 시 관련 테스트와 문서를 함께 수정해주세요. 비밀 값과 로컬 설정 파일은 커밋하지 마세요. 기본 라이선스는 [MIT](../LICENSE)입니다. 공개 배포 전 저작권자 정보와 패키지 이름 사용 가능 여부를 확인하세요. 이 프로젝트는 Atlassian 또는 GitHub의 공식 도구가 아닙니다.

## API 문서

- [GitHub 조직 저장소 목록](https://docs.github.com/en/rest/repos/repos#list-organization-repositories)
- [Bitbucket Cloud 프로젝트별 조회](https://support.atlassian.com/bitbucket-cloud/kb/get-repository-list-within-project-by-using-api/)
- [Bitbucket Data Center 프로젝트 API](https://developer.atlassian.com/server/bitbucket/rest/v1000/api-group-project/)
