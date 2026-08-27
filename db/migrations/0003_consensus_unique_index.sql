-- 애널리스트 컨센서스 중복 적재 방지.
-- 같은 종목/일자/증권사는 한 번만 보관한다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_consensus_stock_date_firm
    ON fact_analyst_consensus (stock_code, report_date, COALESCE(securities_firm, ''));
