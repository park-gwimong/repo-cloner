# 변경 기록

사용자에게 영향을 주는 변경을 기록합니다. 아래 Unreleased 항목은 배포 버전이나 배포 일자를 의미하지 않습니다.
현재 패키지 메타데이터 버전은 pyproject.toml에서 확인하세요.

## Unreleased

### 추가

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
- TUI Bitbucket 경로는 프로젝트 표시 이름 아래에 저장소를 배치. batch/-i 경로 규칙은 유지.
- TUI 마지막 Enter는 실행, N/Esc/Q는 취소. 번호 입력 모드의 마지막 Enter는 계속 취소.
- 루트 repositories.example.json은 examples/credentials.json으로 이동.
- 루트 repositories.batch.example.json은 examples/batch.all-providers.json으로 이동.

### 호환성 안내

- 기존 전체 JSON은 별도 파일에 보관하고 `--batch` 또는 `-i`로 실행.
- workspace 자동 조회는 API 토큰에 `read:workspace:bitbucket` scope가 필요.
- TUI와 batch의 저장 경로가 다르므로 기존 저장소를 재사용할 때 미리 보기로 확인.
- 예제 파일을 새 위치에서 직접 실행하면 상대 destination 기준도 바뀜. 복사해서 사용할 것을 권장.
