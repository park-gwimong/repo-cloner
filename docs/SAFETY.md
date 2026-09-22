# 안전한 갱신과 데이터 보호

결과는 실행 전 대상 표의 경로에 저장됩니다. batch의 여러 프로젝트 형식에서는 source 이름 아래에
프로젝트 키 폴더가 추가됩니다. TUI는 프로젝트 표시 이름을 폴더로 사용합니다. 없는 경로는 clone하고,
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
선택 중 `q`·입력 종료·Ctrl+C로 중단하면 130입니다. 번호 입력 모드(`-i`)의 실행 확인에서 `n` 또는 Enter를 입력하면
저장소를 변경하지 않고 종료하며, 앞선 조회 실패가 없으면 0, 있으면 1입니다. 실패한 clone은 `.clone-<임의 값>` 임시 폴더를 남길 수
하므로 출력된 경로를 확인한 뒤 원인을 해결하고 다시 실행하세요. 갱신은 stash,
reset, clean, rebase를 하지 않으며 서브모듈도 자동 초기화하지 않습니다. 갱신용
임시 hook 디렉터리 정리에 실패하면 오류와 해당 절대 경로를 출력하며, 이미 수행된
fast-forward를 되돌리지 않습니다.

clone은 `.clone-<임의 값>` 폴더에서 먼저 실행됩니다. clone 실패 시 해당 경로를 출력하고 재실행 시 다시 시도합니다. 성공 후 최종 폴더로 내용을 옮기는 도중 중단되면 최종 폴더도 불완전할 수 있습니다. 출력된 경로를 확인하고 불완전한 폴더를 정리한 후 다시 실행하세요. 실행 중 같은 출력 위치를 다른 프로세스에서 변경하지 마세요.

API 통신은 HTTPS만 허용하며 인증 정보 보호를 위해 리다이렉트를 따르지 않습니다. 사내 인증서는 운영체제/Python에서 신뢰하도록 설정해야 합니다.


TUI 최종 확인에서는 Enter/Y가 실행, N/Esc/Q가 취소입니다. batch는 확인 입력이 없습니다.

[README로 돌아가기](../README.md)
