-- ============================================
-- InvestScope 초기 스키마 (AGENT_INSTRUCTIONS.md §5)
-- 적용: psql "$DATABASE_URL" -f db/migrations/0001_init.sql
-- ============================================

-- 기업 마스터
CREATE TABLE IF NOT EXISTS dim_company (
    corp_code   VARCHAR(8) PRIMARY KEY,
    stock_code  VARCHAR(6) UNIQUE,
    corp_name   TEXT NOT NULL,
    aliases     TEXT[],
    sector      TEXT
);
CREATE INDEX IF NOT EXISTS idx_dim_company_name   ON dim_company (corp_name);
CREATE INDEX IF NOT EXISTS idx_dim_company_sector ON dim_company (sector);

-- 재무제표 (정규화 후)
CREATE TABLE IF NOT EXISTS fact_financial_statement (
    id                      SERIAL PRIMARY KEY,
    corp_code               VARCHAR(8) REFERENCES dim_company(corp_code),
    report_date             DATE,
    account_id              TEXT,
    account_value           NUMERIC,
    sector_percentile_rank  NUMERIC,
    accrual_ratio           NUMERIC,
    dso                     NUMERIC,
    dio                     NUMERIC,
    source_rcp_no           TEXT,
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ffs_corp_date_account
    ON fact_financial_statement (corp_code, report_date, account_id);

-- 거시지표
CREATE TABLE IF NOT EXISTS fact_macro_indicator (
    id             SERIAL PRIMARY KEY,
    indicator_code TEXT,
    period         TEXT,
    value          NUMERIC
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_macro_code_period
    ON fact_macro_indicator (indicator_code, period);

-- 업종별 거시 민감도
CREATE TABLE IF NOT EXISTS dim_sector_sensitivity (
    sector           TEXT PRIMARY KEY,
    rate_sensitivity TEXT,   -- 고/중/저
    fx_sensitivity   TEXT
);

-- 뉴스 감성
CREATE TABLE IF NOT EXISTS fact_news_sentiment (
    id               SERIAL PRIMARY KEY,
    corp_code        VARCHAR(8) REFERENCES dim_company(corp_code),
    published_at     TIMESTAMPTZ,
    title            TEXT,
    url              TEXT,
    sentiment_score  NUMERIC,
    topic_tag        TEXT,
    dedup_group_id   TEXT,
    sentiment_source TEXT     -- 'local' | 'llm'
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_news_url ON fact_news_sentiment (url);
CREATE INDEX IF NOT EXISTS idx_news_corp_time
    ON fact_news_sentiment (corp_code, published_at DESC);

-- 애널리스트 컨센서스 (final_score 에 반영하지 않고 별도 노출)
CREATE TABLE IF NOT EXISTS fact_analyst_consensus (
    id              SERIAL PRIMARY KEY,
    stock_code      VARCHAR(6),
    report_date     DATE,
    securities_firm TEXT,
    opinion         TEXT,     -- 매수/중립/매도
    target_price    NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_consensus_stock_date
    ON fact_analyst_consensus (stock_code, report_date DESC);

-- 라이브 스코어 (관심종목 등록 기업)
CREATE TABLE IF NOT EXISTS mart_investment_score (
    id                   SERIAL PRIMARY KEY,
    corp_code            VARCHAR(8) REFERENCES dim_company(corp_code),
    score_date           TIMESTAMPTZ,
    final_score          NUMERIC,
    contributing_factors JSONB,
    recommendation_label TEXT,
    trigger_type         TEXT     -- 'batch' | 'event'
);
CREATE INDEX IF NOT EXISTS idx_mart_score_corp_date
    ON mart_investment_score (corp_code, score_date DESC);

-- 스냅샷 스코어 (미등록 기업 1회성 조회)
CREATE TABLE IF NOT EXISTS fact_snapshot_score (
    corp_code            VARCHAR(8) PRIMARY KEY REFERENCES dim_company(corp_code),
    requested_at         TIMESTAMPTZ,
    final_score          NUMERIC,
    contributing_factors JSONB,
    expires_at           TIMESTAMPTZ
);

-- 관심종목
CREATE TABLE IF NOT EXISTS user_watchlist (
    user_id       TEXT,
    corp_code     VARCHAR(8) REFERENCES dim_company(corp_code),
    registered_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, corp_code)
);

-- 실시간 OHLCV (라이브 대상만)
CREATE TABLE IF NOT EXISTS fact_ohlcv_realtime (
    id         SERIAL PRIMARY KEY,
    stock_code VARCHAR(6),
    ts         TIMESTAMPTZ,
    open       NUMERIC,
    high       NUMERIC,
    low        NUMERIC,
    close      NUMERIC,
    volume     BIGINT,
    bid_price  NUMERIC,
    ask_price  NUMERIC
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ohlcv_stock_ts
    ON fact_ohlcv_realtime (stock_code, ts);

-- 차트 주석 (패턴/지표 해설)
CREATE TABLE IF NOT EXISTS fact_chart_annotation (
    id               SERIAL PRIMARY KEY,
    stock_code       VARCHAR(6),
    ts               TIMESTAMPTZ,
    pattern_label    TEXT,
    indicator_flags  JSONB,
    explanation_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_annotation_stock_ts
    ON fact_chart_annotation (stock_code, ts DESC);
