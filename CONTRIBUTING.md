# 기여 안내

버그 보고, 문서 개선, 테스트 및 기능 변경을 받습니다. 먼저 기존 이슈에서 같은 내용이 있는지 확인하세요.

## 개발 환경

Python 3.10 이상과 Git이 필요합니다. 저장소 루트에서 실행하세요.

```bash
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
repo-cloner --help
```

런타임 외부 의존성은 없으며 테스트도 unittest를 사용합니다.
API와 키 입력은 mock으로 검증하고 실제 Git 검사는 임시 로컬 저장소를 사용합니다.
테스트에 실제 서비스 토큰이나 개인 계정을 사용하지 마세요.

## 변경 절차

1. 문제와 재현 조건을 이슈나 PR 설명에 적습니다.
2. 변경 내용을 한 목적에 맞게 작성하고 해당 동작을 검증합니다.
3. 옵션·설정·저장 경로·종료 코드가 바뀌면 README와 해당 docs/ 문서 및 예제를 함께 갱신합니다.
4. 사용자에게 영향을 주는 변경은 CHANGELOG.md의 Unreleased에 기록합니다.
5. 테스트 결과와 제한 사항을 포함해 PR을 작성합니다.

```bash
# TUI만 수정한 경우의 관련 검사 예
python -m unittest discover -s tests -p "test_tui*.py" -v
# 제출 전 전체 검사
python -m unittest discover -s tests -v
git diff --check
```

문서만 수정했다면 상대 링크·JSON 예제·복사한 예제의 dry-run 명령을 확인하세요.
CI는 Python 3.10/3.13과 Windows/Linux/macOS에서 전체 테스트, 패키지 설치, 명령 도움말을 검사합니다.

## 코드와 데이터 보호

Python 3.10 문법 및 Windows/POSIX 터미널 동작을 유지하세요. Git 동작 변경은 로컬 수정·커밋 보존을 검증해야 합니다.
자동 reset/clean/stash/rebase 또는 URL에 API 토큰을 삽입하는 방식은 현재 보호 정책과 충돌합니다.
자세한 조건은 [안전 정책](docs/SAFETY.md)을 확인하세요.

repositories.json, batch.json, .env, 개인 키와 토큰은 커밋하지 마세요.
예제·테스트에는 명백한 가짜 값만 사용하세요. 오류 보고에서 인증 헤더와 비밀 값을 제거하세요.

보안상 민감한 재현 정보나 실제 자격 증명을 공개 이슈에 올리지 마세요.
실수로 노출한 토큰은 해당 서비스에서 폐기·재발급하세요. 별도의 비공개 신고 채널이나 응답 기한은 현재 약속하지 않습니다.

## PR 설명

변경 전 문제, 변경 후 동작, 확인한 테스트를 적습니다. TUI 변경은 가능하면 비밀 정보가 없는 화면 예제를 첨부하세요.
호환성 변경과 새 토큰 scope 요구 사항을 명시하고, 관련 이슈가 있다면 연결하세요.

[README](README.md) · [구조 설명](docs/ARCHITECTURE.md) · [MIT 라이선스](LICENSE)
