# InvestmentAgent 개발 인수인계

작성일: 2026-08-27  
작업 위치: `/Users/joseoglae/hansung/26-2/InvestmentAgent`  
원격 저장소: `https://github.com/davidcho0701/InvestmentAgent`

## 현재 상태

- `main` 최신 커밋: `323f616 feat: sync analyst consensus from KIS`
- 이전 주요 커밋: `1eb2dc5 fix: support study environment setup`
- 로컬 브랜치 상태: `main...origin/main` 동기화 완료
- `origin/Suk`는 `main`과 같은 커밋을 가리키는 것으로 확인됨
- `origin/Seong`은 `main`에 이미 포함된 것으로 확인됨
- 백엔드: `http://127.0.0.1:8000`
- 프론트엔드: `http://localhost:3000`

## 환경

현재 개발은 conda `study` 환경 기준으로 진행했다.

```bash
conda activate study
python --version
```

확인된 Python 버전은 3.10.19다. `apps/worker/requirements.txt` 전체 설치는
`pandas-ta==0.4.71b0`의 Python 3.12 이상 요구 때문에 실패할 수 있어, 현재 개발에
필요한 백엔드 핵심 의존성만 `study` 환경에 설치해 진행했다.

VS Code 터미널에서 `.env`를 자동 주입하도록 다음 설정도 추가했다.

```json
{
  "python.envFile": "${workspaceFolder}/.env",
  "python.terminal.useEnvFile": true
}
```

## 환경변수

`.env`는 로컬에만 두고 커밋하지 않는다. 동료는 `.env.example`을 복사해 아래 값을 채우면 된다.

```bash
cp .env.example .env
```

필수 값:

- `DATABASE_URL`
- `REDIS_URL`
- `DART_API_KEY`
- `ECOS_API_KEY`
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `KIS_APP_KEY`
- `KIS_APP_SECRET`

주의:

- Supabase session pooler URL의 `<password>`에는 GitHub 비밀번호가 아니라 Supabase DB 비밀번호를 넣는다.
- Upstash Redis는 TLS 접속이므로 `REDIS_URL`은 `rediss://default:<password>@<host>:6379` 형식으로 둔다.
- Redis 비밀번호가 대화/화면에 한 번 노출됐으므로 Upstash에서 비밀번호 rotate 후 `.env`를 갱신하는 것을 권장한다.
- API 키, DB URL, Redis URL 전체값은 문서/커밋/채팅에 남기지 않는다.

## DB 마이그레이션

현재 마이그레이션 파일:

```text
db/migrations/0001_init.sql
db/migrations/0002_seed_sector_sensitivity.sql
db/migrations/0003_consensus_unique_index.sql
```

Supabase에는 위 3개가 적용되어 있다. `0003_consensus_unique_index.sql`은
애널리스트 컨센서스가 같은 종목/일자/증권사 기준으로 중복 적재되지 않게 하는 인덱스다.

`psql`이 있으면:

```bash
psql "$DATABASE_URL" -f db/migrations/0001_init.sql
psql "$DATABASE_URL" -f db/migrations/0002_seed_sector_sensitivity.sql
psql "$DATABASE_URL" -f db/migrations/0003_consensus_unique_index.sql
```

`psql`이 없으면 Supabase SQL Editor에서 각 파일 내용을 실행하면 된다.

## 구현된 주요 내용

### 기본 연결/셋업

- GitHub 저장소를 `26-2` 폴더에 연결하고 `main`을 최신 상태로 pull/push했다.
- conda `study` 환경에서 백엔드 실행이 가능하도록 Python 3.10 호환 이슈를 수정했다.
- `datetime.UTC` 사용부를 `datetime.timezone.utc`로 바꿔 Python 3.10에서도 동작하게 했다.
- Supabase session pooler 연결을 확인했다.
- Upstash Redis TLS 연결을 확인했다.

### 기업 검색/스코어 데이터

- DART 기업코드 마스터를 적재했다.
- 현재 `dim_company`에는 3,988개 기업이 들어 있다.
- 삼성전자 검색 확인:
  - `삼성`
  - `삼전`
  - `005930`
- 삼성전자 재무, 뉴스, 거시 데이터 기반 스코어가 생성된다.
- 삼성전자 현재 점수 확인값:
  - `final_score`: 64.61
  - `mode`: `live`

### 섹터 매핑 보강

`apps/worker/ingestion/dart_client.py`에서 반도체 관련 DART 업종 prefix 매핑을 보강했다.
삼성전자와 관련 peer의 섹터 백분위 계산이 가능하도록 하기 위한 변경이다.

### 애널리스트 컨센서스

KIS 공식 샘플을 기준으로 국내주식 종목투자의견 API를 연결했다.

- 엔드포인트: `/uapi/domestic-stock/v1/quotations/invest-opinion`
- TR ID: `FHKST663300C0`
- 조회 범위 기본값: 최근 180일
- 저장 테이블: `fact_analyst_consensus`
- 프론트 노출 위치: `/api/score/{stock_code}` 응답의 `analyst_consensus`
- `final_score`에는 반영하지 않고 별도 참고 패널로만 노출한다.

삼성전자 적재 확인값:

- 전체 적재: 85건
- 기간: 2026-03-03 ~ 2026-08-10
- 최근 90일 리포트: 28건
- 평균 목표가: 약 496,964원
- 최신 리포트일: 2026-08-10
- 의견 분포: `매수 28`

관련 변경 파일:

- `apps/worker/ingestion/kis_client.py`
- `apps/worker/pipeline/analyst_consensus.py`
- `tests/worker/test_kis_client.py`
- `db/migrations/0003_consensus_unique_index.sql`

KIS 참고 링크:

- https://github.com/koreainvestment/open-trading-api
- https://apiportal.koreainvestment.com/intro

## 실행 방법

백엔드:

```bash
conda activate study
cd /Users/joseoglae/hansung/26-2/InvestmentAgent
python -m uvicorn apps.worker.api.main:app --port 8000
```

프론트엔드:

```bash
cd /Users/joseoglae/hansung/26-2/InvestmentAgent/apps/web
npm run dev
```

브라우저:

```text
http://localhost:3000
```

헬스체크:

```bash
curl http://127.0.0.1:8000/health
```

정상 예시:

```json
{"status":"ok","db":true,"redis":true,"missing_env":[]}
```

삼성전자 점수 API:

```bash
curl "http://127.0.0.1:8000/api/score/005930?user_id=demo-user"
```

현재 확인된 응답 요약:

```text
corp_name=삼성전자
mode=live
final_score=64.61
analyst_report_count=28
analyst_avg_target_price=496964
analyst_latest_report_date=2026-08-10
analyst_opinion_counts={'매수': 28}
```

## 데이터 수동 동기화

삼성전자 애널리스트 컨센서스 재동기화:

```bash
conda activate study
cd /Users/joseoglae/hansung/26-2/InvestmentAgent
python -c "from apps.worker.pipeline import analyst_consensus; print(analyst_consensus.sync_consensus('005930'))"
```

주의: KIS 토큰 발급 API는 1분당 1회 제한이 있어 너무 빠르게 반복 실행하면 403이 발생할 수 있다.

스냅샷 캐시 삭제:

```bash
python -c "from apps.worker.core import cache; print(cache.get_client().delete(cache.snapshot_key('005930')))"
```

## 검증 명령

이번 상태에서 통과한 검증:

```bash
conda run -n study python -m ruff check apps/worker/ingestion/kis_client.py apps/worker/pipeline/analyst_consensus.py tests/worker/test_kis_client.py
conda run -n study python -m pytest tests/worker/test_kis_client.py tests/worker/test_api_app.py apps/worker/tests/test_scoring.py
cd apps/web && npm run typecheck
```

검증 결과:

- Ruff: 통과
- Pytest: 16 passed
- TypeScript typecheck: 통과

## 현재 남은 이슈

- KIS historical OHLCV 조회는 아직 stub 상태다.
- 실시간 차트는 관심종목 등록 후 WebSocket 연결까지 확인했지만, 장 종료 후에는 새 tick이 없어서 차트 데이터가 비어 보일 수 있다.
- “차트 쉽게 읽기”는 실시간/과거 OHLCV 캔들이 들어와야 패턴과 지표 해석이 가능하다.
- npm install 결과 보안 취약점 경고가 3개 있었지만 아직 별도 조치하지 않았다.
- `requirements.txt`의 `pandas-ta==0.4.71b0`은 Python 3.12 이상 요구라 `study` Python 3.10 환경에서는 전체 설치가 막힐 수 있다.

## 동료에게 전달할 체크리스트

1. `.env`를 새로 만들고 각자 발급받은 비밀값을 넣는다.
2. Supabase 마이그레이션 3개가 적용됐는지 확인한다.
3. Upstash Redis URL은 `rediss://`로 시작하는지 확인한다.
4. `conda activate study` 후 백엔드를 실행한다.
5. `apps/web`에서 프론트를 실행한다.
6. `/health`가 `db=true`, `redis=true`, `missing_env=[]`인지 확인한다.
7. `005930` 검색 후 애널리스트 컨센서스 패널이 나오는지 확인한다.
