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
| Permission denied (publickey) | 해당 서비스에 등록된 SSH 키와 SSH agent 설정 확인 |
| Host key verification failed | 서비스가 공개한 지문과 비교하여 로컬 SSH known_hosts 설정 확인 |

오류를 보고할 때 OS, Python/Git 버전, 실행 명령, 비밀 값을 지운 설정과 로그를 첨부하세요.
username, token, 인증 헤더, 개인 키는 포함하지 마세요.

[README로 돌아가기](../README.md)
