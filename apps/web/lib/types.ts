// 백엔드 응답 계약. worker/api 의 스키마와 동기화할 것.

export type ScoreMode = "live" | "snapshot";

export interface FactorDetail {
  score: number;
  weight: number;
  raw: number | null;
  accrual_penalty?: number;
}

export interface ScoreResponse {
  stock_code: string;
  corp_name: string;
  mode: ScoreMode;
  /** 스냅샷일 때 기준 시각. 실시간과 혼동되지 않도록 UI 에 반드시 표기한다. */
  as_of: string;
  expires_at?: string;
  final_score: number;
  recommendation_label: string;
  contributing_factors: {
    financial_health: FactorDetail;
    financial_growth: FactorDetail;
    news_sentiment: FactorDetail;
    macro_adjustment: FactorDetail;
  };
  evidence: string[];
  /** final_score 에 포함되지 않는 참고 정보 (별도 패널로만 노출). */
  analyst_consensus?: AnalystConsensus;
}

export interface AnalystConsensus {
  opinion_counts: Record<string, number>;
  avg_target_price: number | null;
  report_count: number;
  latest_report_date: string | null;
}

export interface Candle {
  time: number; // epoch seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type ChartMode = "realtime" | "static";

export interface ChartAnnotation {
  ts: number;
  pattern_label: string;
  indicator_flags: Record<string, unknown>;
  explanation_text: string;
}

export interface ChartResponse {
  stock_code: string;
  mode: ChartMode;
  as_of: string;
  candles: Candle[];
  annotations: ChartAnnotation[];
}

export interface WatchlistItem {
  corp_code: string;
  stock_code: string;
  corp_name: string;
  registered_at: string;
}

export interface CompanySearchResult {
  corp_code: string;
  stock_code: string | null;
  corp_name: string;
  sector: string | null;
}
