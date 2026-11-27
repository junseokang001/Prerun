export type Explain = {
  id: string;
  title: string;
  plain: string;
  values: { label: string; value: string; note?: string }[];
  why: string;
  evidence: string;
  source?: string;
};

export type Tag = { id: string; text: string; explain: Explain };

export type Timing = {
  label: string | null;
  detail: string | null;
  probability: number;
  sample_n: number;
  bucket_note: string;
  window_start: string | null;
  window_end: string | null;
  windows: {
    label: string;
    probability: number;
    count: number;
    range_label?: string | null;
    start?: number | null;
  }[];
  available: boolean;
  explain: Explain;
};

export type Card = {
  symbol: string;
  code: string;
  name: string;
  market: string;
  currency: "KRW" | "USD";
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  value20: number | null;
  vol_ratio: number | null;
  score: number;
  probability: number | null;
  threshold: number | null;
  baseline_hit_rate?: number | null;
  bucket: { label: string; n: number; predicted_mean: number | null; actual_hit_rate: number | null; legacy_hit_rate?: number | null } | null;
  calibrated_probability?: number | null;
  contributions?: {
    feature: string;
    label: string;
    value: number;
    median: number;
    delta: number;
    text: string;
    explain: Explain;
  }[];
  status: "candidate" | "demoted" | "neutral";
  signal_date: string;
  demoted_at: string | null;
  demote_reason: string | null;
  gain_since_signal: number;
  timing: Timing;
  tags: Tag[];
  explain_score: Explain;
  explain_timing: Explain;
  plan?: {
    stop: number;
    target: number;
    resistance: number | null;
    stop_method: string;
    evidence: string;
    explain_stop: Explain;
    explain_target: Explain;
    explain_resistance: Explain | null;
  } | null;
  spark: number[];
  source: string;
  price_source: string;
  price_time: string;
  signal_bar_date: string;
  dropped_today: boolean;
};

export type Tracked = {
  symbol: string;
  name: string;
  code: string;
  market: string;
  currency: "KRW" | "USD";
  price: number;
  change: number;
  change_pct: number;
  probability: number | null;
  status: string;
  demoted_at: string | null;
  demote_reason: string | null;
  stop: number | null;
  target: number | null;
};

export type FlowStock = {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  candidate: boolean;
  market: string;
};

export type FlowGroup = {
  id: number | string;
  name: string;
  kind: string;
  count?: number | null;
  change_1d: number | null;
  change_1w: number | null;
  change_1m: number | null;
  return_note?: string | null;
  leader: FlowStock | null;
  stocks: FlowStock[];
  value_today: number | null;
  volume_surge: { available: boolean; reason: string };
  foreign: {
    available: boolean;
    reason: string | null;
    foreign_net: number | null;
    institution_net: number | null;
    date: string | null;
    name: string | null;
  };
  has_candidate: boolean;
  rise_count?: number | null;
  fall_count?: number | null;
};

export type SectorPayload = {
  status: string;
  error?: string | null;
  updated_at?: string | null;
  industries: FlowGroup[];
  themes: FlowGroup[];
  source?: string;
};

export type NewsItem = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  sentiment: "positive" | "negative" | "neutral";
  summary: string;
  summary_mode?: string;
  related: { symbol: string; name: string; market: string }[];
  explain: Explain;
};

export type IndexItem = {
  id: string;
  name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  source: string;
  updated_at: string;
  error: string | null;
};

export type Backtest = {
  sample_start: string | null;
  sample_end: string | null;
  target: string;
  baseline: { n: number; hit10: number; hit10_rate: number };
  candidates: { n: number; hit10: number; hit10_rate: number };
  ml: {
    available: boolean;
    reason?: string | null;
    test_start?: string;
    test_end?: string;
    test_n?: number;
    baseline_hit_rate?: number;
    legacy_baseline_hit_rate?: number | null;
    legacy_precision_at_threshold?: number | null;
    embargo_days?: number;
    blend_w?: number | null;
    oof_log_loss_hgb?: number | null;
    oof_log_loss_blend?: number | null;
    label?: string;
    threshold?: number | null;
    threshold_reason?: string | null;
    precision_at_threshold?: number | null;
    precision_at_50?: number | null;
    alerts?: number;
    top_quintile_n?: number;
    top_quintile_hit_rate?: number;
    train_end?: string;
    calibrate_start?: string;
    calibrate_end?: string;
    calibration?: {
      label: string;
      n: number;
      predicted_mean: number | null;
      raw_mean?: number | null;
      actual_hit_rate: number | null;
      legacy_hit_rate?: number | null;
    }[];
  };
  note: string;
};

export type Screener = {
  status: string;
  error?: string | null;
  updated_at: string | null;
  scanned?: number;
  universe?: number;
  passed?: number;
  candidates: Card[];
  demoted: Card[];
  tracked?: Tracked[];
  backtest?: Backtest;
  errors?: { symbol: string; message: string }[];
  signal_session?: { kr: string; us: string; note: string };
  regime?: {
    available: boolean;
    weak: boolean;
    badge: string;
    applied_threshold?: number | null;
    cap?: number | null;
    kospi_distance?: number | null;
    kosdaq_distance?: number | null;
    fx_ret_20?: number | null;
    missing?: string[];
  };
  risk?: { count: number; names?: { name: string; reasons: string[] }[] };
  freshness?: { ok: boolean; warnings: string[] };
  ledger?: {
    headline: string;
    closed: number;
    open: number;
    d20: LedgerWindow;
    d60: LedgerWindow;
  };
};

export type LedgerWindow = {
  n: number;
  open?: number;
  hit_rate: number | null;
  avg_return: number | null;
  stop_first_rate: number | null;
  target_n?: number;
  stop_n?: number;
  expired_n?: number;
};

export type Bar = { t: string; o: number; h: number; l: number; c: number; v: number };

export type Line = {
  id: string;
  type: "horizontal" | "segment" | "note";
  price?: number;
  t1?: string;
  p1?: number;
  t2?: string;
  p2?: number;
  label: string;
  explain?: Explain;
};

export type StockDetail = Card & {
  chart_range: string;
  bars: Bar[];
  indicator_series: {
    ma5?: (number | null)[];
    ma20?: (number | null)[];
    ma60?: (number | null)[];
    bb_upper?: (number | null)[];
    bb_mid?: (number | null)[];
    bb_lower?: (number | null)[];
    rsi?: (number | null)[];
    macd?: (number | null)[];
    macd_signal?: (number | null)[];
    macd_hist?: (number | null)[];
  };
  lines: Line[];
  chart_error: string | null;
  orderbook: {
    available: boolean;
    reason?: string | null;
    sells: { price: number; qty: number }[];
    buys: { price: number; qty: number }[];
    total_sell?: number | null;
    total_buy?: number | null;
    source?: string | null;
    source_url?: string | null;
    updated_at?: string;
  };
  investors: {
    available: boolean;
    reason?: string | null;
    rows: {
      date: string;
      foreign_net: number | null;
      institution_net: number | null;
      individual_net: number | null;
      foreign_ratio: number | null;
    }[];
    source?: string | null;
    source_url?: string | null;
    ownership_note?: string;
  };
  buy_sell: { available: boolean; reason: string };
  why: {
    direction: string;
    lead: string;
    factors: { title: string; detail: string; url: string | null; source: string | null }[];
    articles: NewsItem[];
  };
  forecast: {
    headline: string;
    timing: Timing;
    ml: Backtest["ml"] & { probability?: number | null };
    explain: Explain;
  };
  signals: { id: string; name: string; fired: boolean; contribution: number; explain: Explain }[];
  indicator_explain: Record<string, Explain>;
  session: string;
};
