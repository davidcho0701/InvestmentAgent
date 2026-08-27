# NewsFin Quant

재무·뉴스·거시경제 통합 투자 스코어 + 실시간 차트 해설. (구 프로젝트명: InvestScope)

DART(재무) + ECOS(거시) + 뉴스(감성, LLM 근거 생성) + KIS(실시간 시세·투자의견)를 통합해
**설명 가능한 중장기 투자 스코어(Part 1)** 와 **매매 신호 없는 실시간 캔들차트 해설(Part 2)**
을 제공하는 웹 대시보드. 아무 국내 상장기업이나 검색해 1회성 "스냅샷 리포트"를 볼 수 있고,
최대 3개까지 "관심종목"으로 등록하면 실시간(라이브)으로 전환된다.

개발 순서와 Phase별 완료 기준은 [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md), 최근 작업
인수인계는 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 참조.

---

## 주요 기능

**Part 1 — 재무 스코어**
- DART 재무제표 → 발생액 비율·섹터 백분위 등 파생지표 계산
- 네이버 뉴스 수집 → 중복 제거 → KR-FinBERT 감성분석 → 30일 시간가중 롤링 점수
- 고영향 뉴스는 LLM(기본: 로컬 Ollama)이 매수/매도 표현 없는 중립 근거 문장을 생성 (대시보드의
  "LLM 뉴스 근거" 패널에 노출, `final_score` 산식에는 섞이지 않음)
- ECOS 거시지표(기준금리·환율·국고채3년·CPI) × 업종별 민감도 → 거시 조정 스코어
- KIS 종목투자의견(애널리스트 컨센서스) — 참고용 별도 패널, 스코어 미반영
- 관심종목 미등록 종목은 그 자리에서 1회 계산하는 **스냅샷**(Redis 캐시, 기준 시각 표기),
  등록 종목(최대 3개)은 배치/이벤트 트리거로 갱신되는 **라이브**로 자동 분기

**Part 2 — 차트 쉽게 읽기**
- KIS WebSocket 실시간 체결 → 캔들 집계 → 패턴(장대양봉/도지/갭 등)·지표(이동평균·RSI·거래량
  급증) 감지 → 중립 서술형 해설 (매매 신호 문구 절대 생성하지 않음)
- 장 마감 등으로 실체결이 없을 때는 종목코드 기반 시드 목업 캔들로 화면을 채우고, 작은 안내
  문구("실체결 없음 · 예시 화면")로만 구분

## 디렉터리

```
apps/web/                Next.js 프론트엔드
  app/                   라우트(랜딩 "/", 대시보드 "/dashboard")
  components/part1/      FundamentalReport, LlmNewsEvidence
  components/part2/      ChartLiteracy, CandleChart
  components/shared/     CompanySelector, ModeBadge, LogoMark
  lib/                   api 클라이언트, 타입, 훅(useScorePolling 등), mockChart(데모 목업)
apps/worker/             Python 백엔드
  ingestion/             DART / ECOS / 네이버뉴스 / KIS 클라이언트
  pipeline/              정규화·감성분석·거시조정·컨센서스·스코어링·패턴감지
  streaming/             KIS WebSocket 컨슈머, 캔들 집계, RealtimeChartRuntime
  scheduler/             APScheduler 배치 잡 등록
  api/                   FastAPI 라우트(main.py 가 엔트리포인트)
db/migrations/           SQL DDL (순서대로 적용)
tests/, apps/worker/tests/  pytest 테스트
```

## 사전 요구사항

| 항목 | 버전 | 확인 |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node.js | 20+ (또는 Docker) | `node --version` |
| PostgreSQL | Supabase 무료 티어 | — |
| Redis | Upstash 무료 티어 | — |
| Ollama | 로컬 LLM 실행용(선택) | `ollama --version` |

Node.js를 로컬에 설치하기 어려우면 프론트엔드는 Docker로도 실행할 수 있다 (아래 "프론트엔드"
절 참고).

## 셋업

### 1. 환경변수

```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
```

API 키(DART, ECOS, 네이버 2종, KIS 3종)와 `DATABASE_URL`, `REDIS_URL`을 채운다. 고영향 뉴스
근거 생성은 기본적으로 로컬 Ollama를 쓰므로 `LLM_API_KEY`는 비워둬도 된다.

### 2. 백엔드 (apps/worker)

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows
source .venv/bin/activate              # macOS/Linux
pip install -r apps/worker/requirements.txt
```

### 3. DB 마이그레이션

```bash
psql "$DATABASE_URL" -f db/migrations/0001_init.sql
psql "$DATABASE_URL" -f db/migrations/0002_seed_sector_sensitivity.sql
psql "$DATABASE_URL" -f db/migrations/0003_consensus_unique_index.sql
```

psql이 없으면 Supabase 대시보드의 SQL Editor에 마이그레이션 파일 내용을 순서대로 붙여넣어
실행해도 된다.

### 4. 로컬 LLM (Ollama)

```bash
ollama pull qwen2.5:1.5b-instruct
ollama serve
```

`.env` 기본값:

```bash
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:1.5b-instruct
OLLAMA_BASE_URL=http://localhost:11434
```

`LLM_PROVIDER`를 비워두면 `LLM_API_KEY`가 설정된 경우에만 Anthropic 을 자동 사용하고,
그 외에는 Ollama로 동작한다. 모델은 `ollama pull`로 미리 받아둬야 한다 — Ollama 앱 설치만으로는
동작하지 않는다.

### 5. 프론트엔드 (apps/web)

```bash
cd apps/web
npm install
```

**Node.js가 없다면 Docker로 대체 가능:**

```bash
docker run -d --name newsfin-web -p 3000:3000 \
  -e WATCHPACK_POLLING=true \
  -v "$(pwd):/app" -w /app/apps/web node:24-alpine \
  sh -c "apk add --no-cache libc6-compat && npm install && npx next dev -H 0.0.0.0 -p 3000"
```

`WATCHPACK_POLLING=true`는 Docker 바인드 마운트에서 파일 변경 감지(inotify)가 안 될 때 필요하다
(특히 Windows).

## 실행

```bash
# API 서버 (리포 루트에서) — KIS 키가 설정돼 있으면 서버 기동 시 실시간 캔들 수신도 같이 시작된다
uvicorn apps.worker.api.main:app --reload --port 8000

# 배치 스케줄러 (별도 터미널) — DART 일 배치, ECOS 월 배치, 뉴스 폴링, 정기 재스코어링
python -m apps.worker.scheduler.jobs

# 프론트엔드 (별도 터미널, 위 "프론트엔드" 절 참고)
cd apps/web && npm run dev
```

접속: http://localhost:3000/dashboard · 헬스체크: http://localhost:8000/health
(키 미설정 항목을 `missing_env`로 알려준다)

## 검증

```bash
pytest                          # tests/ + apps/worker/tests/ — 재무 지표, 스코어링, KIS, 패턴감지 등
ruff check .                    # 파이썬 린트
cd apps/web && npx tsc --noEmit
```

## 설정 튜닝

스코어 가중치·정규화 범위·발생액 페널티·패턴 임계값은 코드가 아니라
[apps/worker/config.yaml](apps/worker/config.yaml)에 있다. 실험 시 이 파일만 고친다.

## 제약 (전 Phase 공통)

- Part 2 차트 해설은 **어떤 경우에도 매수/매도 권유 문장을 생성하지 않는다.** 모든 해설은 중립
  어미로 끝나고 "신호 아님" 문구를 동반한다.
- KIS API는 **시세·투자의견 조회 엔드포인트만** 사용한다. 주문(order) 관련 코드는 리포지토리에
  포함하지 않는다.
- 애널리스트 컨센서스와 LLM 뉴스 근거는 `final_score` 연산에 **절대 섞지 않고** 별도 패널로만
  노출한다.
- 스냅샷 데이터는 반드시 **기준 시각과 함께** 반환·표시해 실시간과 혼동되지 않게 한다. 실체결이
  없어 목업으로 채운 차트도 마찬가지로 예시 화면임을 표시한다.
- 관심종목 슬롯 초과 시 명확한 에러를 반환하고, 임의로 기존 슬롯을 대체하지 않는다.
