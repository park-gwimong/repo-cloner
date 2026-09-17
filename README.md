# Project Repo Cloner

GitHub 조직·Bitbucket 프로젝트 또는 직접 지정한 Git URL 목록을 일괄 clone하고 안전하게 갱신하는 Python CLI입니다.
Python 3.10 이상과 Git이 필요하며, 런타임 외부 라이브러리는 없습니다. Windows, macOS, Linux에서 사용할 수 있습니다.

## 빠른 시작

`repositories.example.json`을 `repositories.json`으로 복사한 뒤 사용할 source만 남기고 값을 수정하세요.

```json
{
  "destination": "./clones",
  "protocol": "ssh",
  "sources": [
    {
      "name": "my-project",
      "provider": "bitbucket-cloud",
      "workspace": "my-workspace",
      "project": "PROJ",
      "usernameEnv": "BITBUCKET_CLOUD_EMAIL",
      "tokenEnv": "BITBUCKET_CLOUD_TOKEN"
    }
  ]
}
```

API 인증 정보는 환경변수로 전달합니다. Bitbucket Cloud API 토큰은 계정 이메일과 함께 사용합니다.

설정 JSON 파일과 같은 폴더에 `.env`를 작성하면 실행 시 자동으로 읽습니다.
`sample.env`를 `.env`로 복사하고 사용하는 서비스의 인증 값을 입력하세요. GitHub, Bitbucket Cloud, Bitbucket Server / Data Center 항목이 포함되어 있습니다. 기존 `.env`가 있다면 필요한 항목만 추가하세요.

```dotenv
BITBUCKET_CLOUD_EMAIL=you@example.com
BITBUCKET_CLOUD_TOKEN=YOUR_TOKEN
```

이미 터미널에 설정된 환경변수가 있으면 해당 값을 우선하며, `.env`가 없어도 실행할 수 있습니다.
UTF-8(BOM 포함), 빈 줄, `#` 주석, `export KEY=value`, 작은따옴표와 큰따옴표로 감싼 한 줄 값을 지원합니다.
따옴표 밖의 공백 뒤 `#`는 주석으로 처리합니다. 변수 치환, 이스케이프 변환, 여러 줄 값은 지원하지 않습니다.
잘못된 형식은 값 대신 파일 경로와 줄 번호로 안내합니다. `.env`는 Git 제외 대상입니다.

터미널에서 직접 환경변수를 설정할 수도 있습니다.

```bash
# macOS / Linux
export BITBUCKET_CLOUD_EMAIL='you@example.com'
export BITBUCKET_CLOUD_TOKEN='YOUR_TOKEN'
```

```powershell
# Windows 터미널에서 환경변수 설정
$env:BITBUCKET_CLOUD_EMAIL = 'you@example.com'
$env:BITBUCKET_CLOUD_TOKEN = 'YOUR_TOKEN'
```

실행 코드는 모든 OS에서 동일합니다. 환경에 따라 `python` 대신 `python3`를 사용하세요.

```bash
# 실제 API로 대상 조회. 폴더 생성 및 clone 없음
python repo_cloner.py --config repositories.json --dry-run

# 일괄 clone
python repo_cloner.py --config repositories.json
```

CLI 명령으로 설치해서 사용할 수도 있습니다.

```bash
python -m pip install .
repo-cloner --config repositories.json --dry-run
repo-cloner --config repositories.json
```

## 어디에서 가져와 어디에 저장하나요?

이 도구의 복제 대상은 **원격 Git 저장소**입니다. 일반 로컬 폴더 복사나
미커밋 작업까지 포함하는 백업 도구는 아닙니다.

```text
최종 경로 = 저장 루트 / source.name / 저장소 이름

D:/GitCopies/
└── personal/                  ← source.name
    └── repo-cloner/            ← 원격 저장소 이름 또는 직접 지정한 name
        ├── .git/
        └── ...
```

| 지정 방법 | 상대 경로 기준 | 예 |
| --- | --- | --- |
| JSON의 `destination` | 설정 파일이 있는 폴더 | `"destination": "../copies"` |
| CLI의 `--destination` | 명령을 실행한 현재 폴더 | `--destination ./copies` |
| 절대 경로 | 그대로 사용 | Windows `D:/GitCopies`, macOS `/Users/me/GitCopies`, Linux `/home/me/GitCopies` |

`--destination`이 JSON보다 우선합니다. 둘 다 생략하면 설정 파일 옆 `clones`가
저장 루트입니다. `~`는 사용자 홈으로 확장하지만 JSON 안의 `$HOME`·`%USERPROFILE%`
같은 환경변수 표현은 치환하지 않습니다. JSON의 Windows 경로는 `D:/GitCopies`처럼
슬래시를 쓰거나 `D:\\GitCopies`처럼 역슬래시를 이스케이프하세요.

예를 들어 `C:/settings/repositories.json`의 `destination`이 `./clones`라면,
어느 폴더에서 실행해도 `C:/settings/clones` 아래에 저장됩니다.
설정 파일을 다른 폴더로 옮기면 상대 저장 위치와 자동 로드할 `.env` 위치도 달라집니다.

```powershell
# Windows: 공백이 있는 경로는 따옴표로 감쌉니다.
python repo_cloner.py --config C:/settings/repositories.json --destination "D:/Git Copies" --dry-run
```

```bash
# macOS / Linux: 사용자 홈 아래에 저장
python3 repo_cloner.py --config ./repositories.json --destination ~/GitCopies --dry-run
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
python repo_cloner.py --config personal.json --dry-run
python repo_cloner.py --config personal.json
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

## 조직·프로젝트에서 필요한 저장소만 선택하기

모든 source에서 `include`와 `exclude`로 **저장소 이름**을 필터링할 수 있습니다.
API provider는 조회된 이름/slug, `git` provider는 직접 지정한 `name`을 비교합니다.

```json
{
  "name": "team",
  "provider": "github",
  "organization": "YOUR_ORGANIZATION",
  "tokenEnv": "GITHUB_TOKEN",
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
| `github` | GitHub Organization | `organization` | `tokenEnv`: PAT 등 |
| `bitbucket-cloud` | workspace 안의 프로젝트 | `workspace`, `project` | `usernameEnv`: 이메일, `tokenEnv`: API 토큰 |
| `bitbucket-server` | Server / Data Center 프로젝트 | `baseUrl`, `project` | `tokenEnv`: 개인 액세스 토큰 |

여러 프로젝트는 `sources`에 추가합니다. source마다 고유한 `name`을 지정하세요.
예제 파일에는 세 API 서비스와 직접 URL 지정 예제가 있습니다. 사용할 source만 남기세요.

인증 환경변수는 `<서비스명>_TOKEN`, `<서비스명>_EMAIL` 형식으로 통일합니다. 토큰 종류는 서비스별로 다릅니다.

| provider | `tokenEnv` | `usernameEnv` | 입력할 토큰 |
| --- | --- | --- | --- |
| `github` | `GITHUB_TOKEN` | 생략 | GitHub 개인 액세스 토큰 |
| `bitbucket-cloud` | `BITBUCKET_CLOUD_TOKEN` | `BITBUCKET_CLOUD_EMAIL` | Bitbucket Cloud API 토큰 |
| `bitbucket-server` | `BITBUCKET_SERVER_TOKEN` | 생략 | Server / Data Center 개인 액세스 토큰 |

이전에 사용한 `BITBUCKET_API_TOKEN`, `BITBUCKET_EMAIL`은 각각 `BITBUCKET_CLOUD_TOKEN`, `BITBUCKET_CLOUD_EMAIL`로 변경했습니다. 기존 터미널 환경변수도 새 이름으로 설정하세요.
코드는 `tokenEnv`와 `usernameEnv`에 지정한 이름을 그대로 읽으므로, 별도 설정 파일에서 기존 이름이나 사용자 지정 이름을 사용하는 것도 가능합니다.

- `destination`: 저장 위치. 상대 경로는 설정 파일 위치 기준입니다.
- `protocol`: `ssh`(기본값) 또는 `https`.
- `project`: Bitbucket의 표시 이름이 아닌 프로젝트 **키**.
- `tokenEnv`, `usernameEnv`: 비밀 값 자체가 아닌 환경변수 **이름**.
- `github.apiUrl`: Enterprise 사용 시 `https://github.example.com/api/v3` 지정.
- `bitbucket-server.baseUrl`: 예: `https://bitbucket.example.com` 또는 context path를 포함한 주소.
- 공개 저장소를 익명 조회하려면 `tokenEnv`를 생략합니다. Bearer 방식의 Bitbucket Cloud access token 사용 시 `usernameEnv`를 생략합니다.

`github` provider는 Organization 전체를 조회한 뒤 이름 필터를 적용합니다. GitHub Projects 보드 및 개인 계정 단위 자동 조회는 지원하지 않습니다. 개인 저장소는 `git` provider로 URL을 지정할 수 있습니다. 토큰 권한으로 조회 가능한 저장소만 포함되며, 모든 페이지를 순회합니다. 조직의 토큰 승인이나 SSO 설정에 따라 접근 범위가 제한될 수 있습니다.

**목록 조회 인증과 Git clone 인증은 별개입니다.** SSH는 제공자에 등록한 SSH 키, HTTPS는 Git Credential Manager 등 로컬 Git 인증 설정을 사용합니다. 토큰을 Git URL에 삽입하지 않습니다.

## 재실행과 안전한 갱신

결과는 `<저장 루트>/<source 이름>/<저장소 이름>`에 저장됩니다. 없는 경로는 clone하고,
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
중단하면 130입니다. 실패한 clone은 `.clone-<임의 값>` 임시 폴더를 남길 수
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
계속 진행을 검증합니다. 테스트를 실행하려면 Git이 PATH에 있어야 하며 서브모듈이나
외부 서비스는 사용하지 않습니다. GitHub Actions에서도 Python 3.10/3.13과
Windows/Linux/macOS 조합으로 실행합니다.

변경 시 관련 테스트와 문서를 함께 수정해주세요. 비밀 값과 로컬 설정 파일은 커밋하지 마세요. 기본 라이선스는 [MIT](LICENSE)입니다. 공개 배포 전 저작권자 정보와 패키지 이름 사용 가능 여부를 확인하세요. 이 프로젝트는 Atlassian 또는 GitHub의 공식 도구가 아닙니다.

## API 문서

- [GitHub 조직 저장소 목록](https://docs.github.com/en/rest/repos/repos#list-organization-repositories)
- [Bitbucket Cloud 프로젝트별 조회](https://support.atlassian.com/bitbucket-cloud/kb/get-repository-list-within-project-by-using-api/)
- [Bitbucket Data Center 프로젝트 API](https://developer.atlassian.com/server/bitbucket/rest/v1000/api-group-project/)
