# 설정 예제

예제 파일을 프로젝트 루트 또는 별도의 설정 디렉터리로 **복사해서** 사용하세요.
실제 자격 증명은 추적 중인 예제 파일에 입력하지 마세요.

batch 예제에는 토큰이 없습니다. `"credentials"`로 **같은 폴더의 인증 파일**을 참조하므로,
batch 파일을 복사한 폴더에 인증 파일도 만드세요. 인증 파일 형식은 [credentials.json](credentials.json)과 같습니다.
이렇게 하면 batch 파일은 여러 PC에서 공유하고 인증 파일만 PC마다 따로 둘 수 있습니다.

| 파일 | 실행 모드 | 용도 |
| --- | --- | --- |
| [credentials.json](credentials.json) | TUI | username·token만 포함. repositories.json으로 복사 |
| [batch.git.json](batch.git.json) | batch / -i | API 없이 직접 Git URL 목록 사용 |
| [batch.github.json](batch.github.json) | batch / -i | GitHub 조직. archived·fork 제외와 이름 필터. 인증: repositories.json |
| [batch.github-user.json](batch.github-user.json) | batch / -i | 토큰 소유자의 개인 저장소. name을 원하는 계정 폴더명으로 수정. 인증: repositories.json |
| [batch.bitbucket-cloud.json](batch.bitbucket-cloud.json) | batch / -i | Cloud workspace의 여러 프로젝트. 인증: repositories.json |
| [batch.bitbucket-server.json](batch.bitbucket-server.json) | batch / -i | Server / Data Center 단일 프로젝트. 인증: repositories.json |
| [batch.all-providers.json](batch.all-providers.json) | batch / -i | 전체 필드 참고. 서비스별 인증 파일(github.json, bitbucket-cloud.json, bitbucket-server.json) 사용. 필요한 source만 남길 것 |

batch 예제는 `batch.json`으로 복사한 뒤 서비스·조직·프로젝트 키를 수정합니다. 인증 값은 참조한 인증 파일에만 넣습니다.
`destination: "./clones"`는 **복사한 설정 파일이 있는 폴더 기준**입니다.
예제 파일을 직접 실행하면 `examples/clones`가 기본 대상이 됩니다.
`--destination`으로 지정한 상대 경로는 명령 실행 폴더 기준입니다.

```powershell
Copy-Item examples/batch.github.json batch.json
Copy-Item examples/credentials.json repositories.json   # 토큰 입력
python repo_cloner.py --batch --config batch.json --dry-run
```

```bash
cp examples/batch.github.json batch.json
cp examples/credentials.json repositories.json          # 토큰 입력
python3 repo_cloner.py --batch --config batch.json --dry-run
```

루트의 `repositories.json`, `batch.json`, `github.json`, `bitbucket-cloud.json`, `bitbucket-server.json`은 Git 제외 대상입니다. 다른 이름의 개인 설정 파일은
직접 Git 제외 처리해야 합니다. batch 파일은 `credentials` 필드로 지정한 인증 파일만 읽습니다.

[batch 사용법](../docs/BATCH.md) · [설정 항목](../docs/CONFIGURATION.md)
