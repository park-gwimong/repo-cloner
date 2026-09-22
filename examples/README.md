# 설정 예제

예제 파일을 프로젝트 루트 또는 별도의 설정 디렉터리로 **복사해서** 사용하세요.
실제 자격 증명은 추적 중인 예제 파일에 입력하지 마세요.

| 파일 | 실행 모드 | 용도 |
| --- | --- | --- |
| [credentials.json](credentials.json) | TUI | username·token만 포함. repositories.json으로 복사 |
| [batch.git.json](batch.git.json) | batch / -i | API 없이 직접 Git URL 목록 사용 |
| [batch.github.json](batch.github.json) | batch / -i | GitHub 조직의 저장소와 이름 필터 |
| [batch.bitbucket-cloud.json](batch.bitbucket-cloud.json) | batch / -i | Cloud workspace의 여러 프로젝트 |
| [batch.bitbucket-server.json](batch.bitbucket-server.json) | batch / -i | Server / Data Center 단일 프로젝트 |
| [batch.all-providers.json](batch.all-providers.json) | batch / -i | 전체 필드 참고. 필요한 source만 남길 것 |

batch 예제는 `batch.json`으로 복사한 뒤 서비스·프로젝트 키·인증 값을 수정합니다.
`destination: "./clones"`는 **복사한 설정 파일이 있는 폴더 기준**입니다.
예제 파일을 직접 실행하면 `examples/clones`가 기본 대상이 됩니다.
`--destination`으로 지정한 상대 경로는 명령 실행 폴더 기준입니다.

```powershell
Copy-Item examples/batch.git.json batch.json
python repo_cloner.py --batch --config batch.json --dry-run
```

```bash
cp examples/batch.git.json batch.json
python3 repo_cloner.py --batch --config batch.json --dry-run
```

루트의 `repositories.json`과 `batch.json`은 Git 제외 대상입니다. 다른 이름의 개인 설정 파일은
직접 Git 제외 처리해야 합니다. 이 도구는 인증 파일과 batch 파일을 자동 병합하지 않습니다.

[batch 사용법](../docs/BATCH.md) · [설정 항목](../docs/CONFIGURATION.md)
