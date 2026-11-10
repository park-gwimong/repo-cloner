# 변경 기록

사용자에게 영향을 주는 변경을 기록합니다. 버전은 `repo_cloner.py`의 `__version__`이며 `repo-cloner --version`으로 확인합니다.
버전별 항목은 같은 이름의 Git 태그(`v0.1.0` 등)에 해당합니다.

## Unreleased

### 추가

- TUI batch 저장 시 범위 선택: 지금 고른 저장소만, 또는 프로젝트·계정 전체(나중에 생긴 저장소 자동 포함).

## [0.2.1] - 2026-11-10

### 수정

- 기존 저장소 검사·update 때 저장소 설정의 `core.fsmonitor` 명령이 실행되던 문제. 모든 Git 명령에 `-c core.fsmonitor=false` 적용.

### 변경

- CI에 Python 3.14 추가.

## [0.2.0] - 2026-11-10

### 추가

- GitHub source `skipArchived`·`skipForks`: 보관·fork 저장소 제외. 선택 화면에 `[archived]`·`[fork]` 표시.

### 변경

- batch 예제가 토큰 대신 `credentials`로 인증 파일을 참조. 중복된 batch.shared-credentials.json 제거.
- 예제가 참조하는 인증 파일(github.json, bitbucket-cloud.json, bitbucket-server.json)을 Git 제외 대상에 추가.
- 문제 해결 문서에 credentials·layout·submodules 오류, batch 저장, `--status` 상태별 해결 방법 추가.
- CI 액션을 Node 24 기반 v7로 올리고 Dependabot으로 액션 버전을 매월 갱신.

## [0.1.1] - 2026-11-10

### 수정

- 저장 경로의 상위 폴더가 링크(macOS `/var` → `/private/var`, Windows junction 등)이면 기존 저장소 update를 항상 건너뛰던 문제.
- 설정 파일 폴더 경로를 실제 경로로 바꾸지 않고 입력한 그대로 사용(macOS `/private/var`, Windows 8.3 짧은 이름이 화면과 저장 경로에 나타나던 문제).
- macOS·Windows CI 실패 해결. CI가 모든 OS 결과를 끝까지 보고하고, 실패한 테스트를 로그인 없이 볼 수 있는 주석으로 남김.

## [0.1.0] - 2026-11-10

첫 배포 버전입니다.

### 추가

- `--version` 옵션과 단일 버전 관리, pipx 설치 안내.
- TUI 선택을 batch 파일로 저장. 토큰 대신 인증 파일 경로를 기록하고, TUI와 같은 폴더 구조를 재현.
- batch `credentials` 필드: 최상위 또는 source별로 username·token 인증 파일을 참조.
- `--status` 모드: 설정과 로컬 상태 비교(읽기 전용, fetch 없음). OK/BEHIND/AHEAD/DIVERGED/MISSING/SKIP/WARN/EXTRA/PARTIAL 표시.
- batch `submodules` 설정: clone 시 서브모듈 포함, 안전한 update 뒤 서브모듈 갱신.
- Git LFS 저장소인데 git-lfs가 없으면 clone 직후와 `--status`에서 경고.
- batch·`-i` `layout: "project"`: TUI와 같은 폴더(프로젝트 표시 이름, 조직·계정명) 사용. 기본값 `source`는 기존 경로 유지.
- TUI 실행 대시보드: 전체 진행률, 현재 저장소·경과 시간, Git 로그, 결과 집계 및 프로세스 트리 취소.
- TUI의 Git/SSH 입력 대기를 비활성화하고 인증·호스트 키 확인 실패를 별도로 안내.
- GitHub 개인 계정 모드: 토큰으로 계정명 자동 확인, 본인 소유 공개·비공개 저장소 조회 및 선택. batch provider는 github-user.
- 기본 키보드 TUI: 저장 경로 편집, 서비스·workspace·프로젝트·저장소 선택.
- Bitbucket Cloud 사용자 workspace 목록 조회 및 페이지 순회.
- 여러 프로젝트 처리, 실행 대상 미리 보기, 진행률 및 결과 집계.
- provider별 examples/, batch·설정·안전·문제 해결 문서, 기여 가이드와 이슈·PR 템플릿.

### 변경

- 기본 실행은 TUI이며 자동화는 `--batch --config batch.json`을 명시.
- TUI 설정은 username·token 전용. 전체 작업 설정은 메모리에서 만들고 저장하지 않음.
- TUI Bitbucket 경로는 프로젝트 표시 이름 아래에 저장소를 배치. batch/-i 기본 경로 규칙은 유지(`layout: "project"`로 TUI와 통일 가능).
- TUI 마지막 Enter는 실행, N/Esc/Q는 취소. 번호 입력 모드의 마지막 Enter는 계속 취소.
- 루트 repositories.example.json은 examples/credentials.json으로 이동.
- 루트 repositories.batch.example.json은 examples/batch.all-providers.json으로 이동.
- 프로젝트와 무관한 gjc-install.ps1 제거.

### 호환성 안내

- 기존 전체 JSON은 별도 파일에 보관하고 `--batch` 또는 `-i`로 실행.
- workspace 자동 조회는 API 토큰에 `read:workspace:bitbucket` scope가 필요.
- TUI와 batch의 저장 경로가 다르므로 기존 저장소를 재사용할 때 미리 보기로 확인.
- 예제 파일을 새 위치에서 직접 실행하면 상대 destination 기준도 바뀜. 복사해서 사용할 것을 권장.
