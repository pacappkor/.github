<!-- SPDX-License-Identifier: GPL-3.0-only -->
# pacappkor 공통 GitHub 설정

[![visitors](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pacappkor/.github/traffic/.traffic/badge-views.json)](https://github.com/pacappkor/.github)
[![clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pacappkor/.github/traffic/.traffic/badge-clones.json)](https://github.com/pacappkor/.github)

공개 저장소의 GitHub 조회수와 clone 수를 매일 보존하고 README 배지로 보여 주는 재사용 워크플로입니다. 외부 방문 추적 픽셀은 사용하지 않습니다. `visitors`는 README 이미지 조회수가 아니라 **GitHub 저장소 traffic views**입니다.

## 저장소 연결

1. 이 저장소를 공개 `pacappkor/.github`로 게시한 뒤, 조직의 각 공개 저장소에 아래 설정을 적용합니다. 기본 브랜치는 `main`이어야 합니다.
2. GitHub에서 fine-grained personal access token을 생성합니다.
   - **Resource owner: pacappkor**
   - **Repository access: Only select repositories** → 집계할 저장소만 선택
   - **Repository permissions → Administration: Read-only**
   - Metadata read는 GitHub가 자동 부여합니다. 별도의 Contents 쓰기, Actions 쓰기, 조직 관리 권한은 부여하지 않습니다.
   - 토큰 소유 계정도 대상 저장소의 traffic을 볼 수 있는 관리자 접근 권한이 필요합니다. 조직 정책에 따른 승인과 만료/갱신을 확인합니다.
3. 조직 **Settings → Secrets and variables → Actions → New organization secret**에 `TRAFFIC_TOKEN`으로 저장합니다. 접근 범위도 집계 대상 저장소로 제한합니다. 평문 토큰을 파일이나 로그에 넣지 않습니다.
4. [templates/traffic.yml](templates/traffic.yml)을 각 저장소의 **main** 브랜치 `.github/workflows/traffic.yml`로 복사합니다. 예약 작업은 기본 브랜치에서만 실행됩니다. 매일 03:17 UTC (한국 12:17) 실행하며 `workflow_dispatch`로 즉시 실행할 수도 있습니다.
5. [templates/badges.md](templates/badges.md)의 `<REPO>`를 저장소 이름으로 바꾸고 각 README에 넣습니다. raw URL과 Shields endpoint는 **공개 저장소에서만** 동작합니다. 첫 성공 실행 전에는 배지가 없거나 오류로 보일 수 있습니다.
6. Actions의 읽기/쓰기 정책이 `contents: write`를 허용하고, `traffic`에 대한 보호 규칙/규칙 집합이 GITHUB_TOKEN의 정상 push를 허용하는지 확인합니다. 강제 push나 보호 규칙 우회는 하지 않습니다.

Traffic API(`/traffic/views?per=day`, `/traffic/clones?per=day`)는 Administration 읽기 권한이 필요하여 기본 `GITHUB_TOKEN`만으로 조회할 수 없습니다. 반대로 브랜치 checkout/push에는 **GITHUB_TOKEN만** 사용하고 `TRAFFIC_TOKEN`을 쓰지 않습니다. 런타임 토큰 권한은 `contents: write` 하나뿐이며 API 토큰은 집계 단계에만 전달됩니다.

## traffic 브랜치의 규칙

- 개발은 모두 `main`에서 합니다. `traffic`은 main 전체 내용 **위에 집계 데이터만 추가**하는 브랜치이며 orphan/data-only 트리는 아닙니다. 수동 개발, force push, main으로 역병합하지 않습니다.
- 매일 full-history checkout 후 없으면 `origin/main`에서 만듭니다. 기존 브랜치는 먼저 fast-forward를 시도하고, 분기했다면 명시적인 merge commit으로 `origin/main`을 병합합니다.
- 충돌이 `.traffic/` 내부에만 있으면 counting branch(ours)의 데이터를 보존합니다. 그 외 충돌은 병합을 중단하고 실패합니다. main에서 원인을 정리한 뒤 재실행합니다. 집계 데이터는 main에서 편집하지 않습니다.
- `.traffic/views.json`, `.traffic/clones.json`은 UTC 날짜별 `timestamp`, `count`, `uniques` 배열입니다. 같은 날짜는 각 수치의 최댓값을 사용하고, API 창 밖의 과거 날짜를 삭제하지 않습니다.
- `.traffic/badge-views.json`, `.traffic/badge-clones.json`은 Shields endpoint JSON입니다. 예: `1.2k views / 300 daily uniques`. 두 배지는 각각 views/clones 누적 합계와 **일별 uniques 합계**를 나타냅니다.
- 네 개의 데이터 파일만 stage하고 바뀐 때만 집계 commit을 만듭니다. 데이터가 그대로여도 새로운 main 병합은 push합니다. 작성자는 `antisocial-socialist` 및 GitHub noreply 주소입니다.
- 저장소별 concurrency로 동시 집계를 직렬화합니다. 외부 수동 push와 경합하면 일반 push가 실패하므로 재실행합니다. 과거 데이터는 강제로 덮어쓰지 않습니다.
- 선택 입력은 `branch`(기본 `traffic`)와 `data-dir`(기본 `.traffic`)입니다. 바꾸면 배지 URL도 바꿉니다. 경로는 상대 디렉터리여야 하며 루트, `.git`, 상위 경로, symlink를 허용하지 않습니다. 운영 중 경로를 바꾸면 이전 이력의 수동 이전이 필요합니다.

재사용 워크플로는 호출 저장소의 파일이 아니라 중앙 공개 저장소의 `scripts/`를 먼저 가져와 임시 경로에 보관한 뒤 실행합니다. 따라서 호출 저장소에는 Python 코드를 복사할 필요가 없습니다. 호출 저장소는 재사용 워크플로를 **검토된 full commit SHA**로 고정하고, 재사용 워크플로는 `job.workflow_sha`(호출된 워크플로와 같은 commit)에서 `scripts/`를 가져옵니다. 따라서 중앙 main이 바뀌어도 고정을 명시적으로 올리기 전에는 각 저장소에서 실행되지 않습니다. checkout/setup-python 액션은 full SHA로 고정했습니다.

## 한계와 운영

- GitHub API가 제공하는 이력은 최근 **14일**입니다. 최초 연결 시 그때 제공되는 최대 14일을 보존하고 이후 누적합니다. 그보다 앞선 lifetime 수치는 복원할 수 없습니다. 14일 넘게 수집이 멈추면 누락 구간도 복원할 수 없습니다.
- **uniques는 기간별 지표이지 평생 중복 제거한 사용자 수가 아닙니다.** 같은 사람이 여러 날 방문하면 일별 uniques 합계에 여러 번 포함됩니다. GitHub UI의 14일 uniques와도 다릅니다. 원시 사용자 식별자는 수집하지 않습니다.
- 당일/최근 수치는 부분 집계이며 지연됩니다. 최대값 유지 정책은 재집계로 감소한 값을 반영하지 않습니다. 오류나 수정된 통계에 대한 공식 감사 수치가 아닙니다.
- 예약 작업은 지연될 수 있고 공개 저장소가 장기간 비활성 상태이면 GitHub가 예약을 비활성화할 수 있습니다(일반적으로 60일). Actions 상태와 토큰 만료를 확인하고 필요하면 수동 실행합니다.
- raw/CDN 및 Shields 캐시 때문에 배지 갱신이 늦을 수 있습니다. 배지 파일은 cacheSeconds=3600을 요청합니다.
- 다른 공개 저장소는 이 메커니즘으로 자동 변경하지 않습니다. 각 저장소의 main에 caller와 배지를 넣어야 합니다. 비공개 저장소를 공개로 바꾸지 않습니다.

## 로컬 검증

Python 3.12 이상, 외부 패키지나 네트워크 없이 실행합니다.

```sh
python -I -B -m unittest discover -s tests -v
```

테스트는 합성 API 응답 및 임시 로컬 git 저장소만 사용합니다. 누적, timestamp 중복, 창 rollover, 배지 형식, 멱등성, 경로/응답 검증과 분기/병합/충돌 정책을 검사합니다. CI는 Python 3.12에서 같은 테스트를 실행하며 secret을 사용하지 않습니다.

## 라이선스

[GNU GPL version 3 only](LICENSE), SPDX `GPL-3.0-only`. 각 소스 파일의 SPDX 헤더가 적용 버전을 명시합니다.

## 운영상 한계: 예약 실행 자동 비활성화

GitHub는 공개 저장소에서 60일 동안 저장소 활동이 없으면 예약(`schedule`) 워크플로를 자동으로 비활성화합니다. 그러면 조회·클론이 계속 있어도 집계가 멈춥니다. `workflow_dispatch`가 있다고 해서 비활성화된 워크플로가 다시 켜지지는 않습니다.

- 배지 값이 오랫동안 바뀌지 않으면 해당 저장소의 **Actions → Daily traffic**이 비활성화되었는지 확인합니다. 비활성화되었다면 **Enable workflow**를 누른 뒤 수동으로 한 번 실행합니다.
- GitHub traffic API는 최근 14일만 제공합니다. 14일을 넘겨 멈추면 그 사이의 일별 값은 복구할 수 없고 누적치에 빠집니다.

## 위협 모델: `TRAFFIC_TOKEN`

- `TRAFFIC_TOKEN`은 조직 secret입니다. 권한은 fine-grained **Administration: read-only** 하나뿐이고, traffic API 읽기에만 씁니다. contents·secrets·workflow 쓰기 권한은 없습니다.
- 브랜치에서 workflow를 바꿀 수 있는 쓰기 권한자는 `workflow_dispatch`를 쓰지 않아도 `on: push` workflow로 같은 secret에 접근할 수 있습니다. 따라서 트리거 제거는 경계가 아닙니다. 실제 경계는 다음 두 가지입니다.
  1. 조직 저장소 쓰기 권한은 운영 계정 하나로 제한합니다.
  2. 토큰 권한은 위와 같이 최소로 유지합니다.
- 외부 기여자(fork PR)에게는 secret이 전달되지 않습니다. caller의 트리거는 `schedule`과 `workflow_dispatch`뿐입니다.
- 쓰기 권한자가 늘면 secret 노출 위험도 커집니다. 그 경우 토큰을 저장소별 environment secret(배포 브랜치 `main` 한정)으로 옮기고, 재사용 워크플로 job에 `environment:`를 지정합니다.
