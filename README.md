# InvestScope

재무·뉴스·거시경제 통합 투자 스코어 + 실시간 차트 해설.

DART(재무) + ECOS(거시) + 뉴스(감성) + KIS(시세·투자의견)를 통합해 **설명 가능한 중장기 투자 스코어(Part 1)** 와 **캔들차트 해설(Part 2)** 을 제공하는 웹 대시보드. 아무 국내 상장기업이나 검색해 1회성 "스냅샷 리포트"를 볼 수 있고, 최대 3개까지 "관심종목"으로 등록하면 실시간(라이브)으로 전환된다.

개발 순서와 Phase별 완료 기준은 [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) 참조.

---

## 사전 요구사항

| 항목 | 버전 | 확인 |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Node.js | 20+ | `node --version` |
| PostgreSQL | Supabase 무료 티어 | — |
| Redis | Upstash 무료 티어 | — |

## 디렉터리

```
apps/web/       Next.js 프론트엔드 (Vercel 배포)
apps/worker/    Python 백엔드 — ingestion / pipeline / scheduler / streaming / api
db/migrations/  SQL DDL
```

## 셋업

### 1. 환경변수

```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
```

API 키 4종(DART, ECOS, 네이버, KIS)과 `DATABASE_URL`, `REDIS_URL` 을 채운다.
고영향 뉴스 근거 생성은 기본적으로 로컬 Ollama 를 사용한다.

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
```

psql 이 없으면 Supabase 대시보드의 SQL Editor 에 마이그레이션 파일 내용을 붙여넣어 실행해도 된다.

### 4. 로컬 LLM (Ollama)

```bash
brew install ollama       # macOS Homebrew 사용 시
ollama pull qwen2.5:1.5b-instruct
ollama serve
```

`.env` 기본값:

```bash
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:1.5b-instruct
OLLAMA_BASE_URL=http://localhost:11434
```

### 5. 프론트엔드 (apps/web)

```bash
cd apps/web
npm install
```

## 실행

```bash
# API 서버 (리포 루트에서)
uvicorn apps.worker.api.main:app --reload --port 8000

# 배치 스케줄러 (별도 터미널)
python -m apps.worker.scheduler.jobs

# 실시간 WebSocket 소비자 (별도 터미널, Phase 5 이후)
python -m apps.worker.streaming.ws_consumer

# 프론트엔드 (별도 터미널)
cd apps/web && npm run dev
```

접속: http://localhost:3000 · 헬스체크: http://localhost:8000/health (키 미설정 항목을 `missing_env` 로 알려준다)

## 검증

```bash
pytest                          # 순수 계산 로직 (재무 지표, 스코어링)
ruff check .                    # 파이썬 린트
cd apps/web && npm run typecheck
```

## 설정 튜닝

스코어 가중치·정규화 범위·발생액 페널티·패턴 임계값은 코드가 아니라 [apps/worker/config.yaml](apps/worker/config.yaml) 에 있다. 실험 시 이 파일만 고친다.

## 제약 (전 Phase 공통)

- Part 2 차트 해설은 **어떤 경우에도 매수/매도 권유 문장을 생성하지 않는다.** 모든 해설은 중립 어미로 끝나고 "신호 아님" 문구를 동반한다.
- KIS API 는 **시세·투자의견 조회 엔드포인트만** 사용한다. 주문(order) 관련 코드는 리포지토리에 포함하지 않는다.
- 애널리스트 컨센서스는 `final_score` 연산에 **절대 섞지 않고** 별도 패널로만 노출한다.
- 스냅샷 데이터는 반드시 **기준 시각과 함께** 반환·표시해 실시간과 혼동되지 않게 한다.
- 관심종목 슬롯 초과 시 명확한 에러를 반환하고, 임의로 기존 슬롯을 대체하지 않는다.
