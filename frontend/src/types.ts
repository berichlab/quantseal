export interface AuthStatus {
  auth_enabled: boolean;
  authenticated: boolean;
  version: string;
}

export interface EValuePoint {
  step: number;
  date?: string;
  delta: number;
  lambda: number;
  evalue: number;
  peak_evalue: number;
  strategy_return_pct?: number;
  benchmark_return_pct?: number;
  note?: string;
}

export interface OverviewResponse {
  version: string;
  engine_code_hash: string;
  auth_enabled: boolean;
  llm_configured: boolean;
  llm_provider: string;
  llm_model: string;
  kpis: {
    total_campaigns: number;
    sealed_campaigns: number;
    pending_validation: number;
    active_shadow_strategies: number;
    promoted_strategies: number;
    retired_strategies: number;
    highest_peak_evalue: number;
  };
  ladder_counts: Record<string, number>;
  featured_shadow: {
    strategy_key: string;
    title: string;
    state: string;
    peak_evalue: number;
    evalue: number;
    observations_count: number;
    cumulative_excess_pct: number;
    shadow_threshold: number;
    live_threshold: number;
    series: EValuePoint[];
  } | null;
  scheduler: {
    running: boolean;
    jobs: Array<{ id: string; next_run_time: string | null; trigger: string }>;
  };
  recent_events: Array<{
    id: number;
    category: string;
    level: string;
    message: string;
    created_at: string;
  }>;
}

export interface CampaignSummaryItem {
  campaign_id: string;
  status: string;
  source: string;
  cost_preset: string;
  config_hash: string;
  data_hash: string;
  code_hash: string;
  prior_campaign_id: string | null;
  validation_evaluated_once: boolean;
  validation_contaminated: boolean;
  total_candidates: number;
  dev_passed: number;
  qualified_count: number;
  created_at: string;
  updated_at: string;
}

export interface ArmMetrics {
  n_trades: number;
  n_signal_days: number;
  avg_net_return_pct: number;
  win_rate_pct: number;
  profit_factor: number;
  cumulative_portfolio_return_pct: number;
  max_drawdown_pct: number;
  annualized_sharpe: number;
  boundary_excluded_signals: number;
  capacity_skipped_signals: number;
  bootstrap_ci: {
    mean: number;
    ci_lower: number;
    ci_upper: number;
    n_clusters: number;
    passed: boolean;
  };
  cost_stress: Record<
    string,
    { multiplier: number; avg_net_return: number; profit_factor: number; passed: boolean }
  >;
  concentration: {
    passed: boolean;
    max_asset_pct: number;
    max_sector_pct: number;
    top_asset: string | null;
    top_sector: string | null;
  };
}

export interface PartitionEval {
  partition: string;
  start_date: string;
  end_date: string;
  verdict: string;
  reason: string;
  arms: Record<string, ArmMetrics>;
  pairwise_comparisons: Record<
    string,
    {
      status: string;
      ref_trades: number;
      mean_daily_delta_pct: number | null;
      cum_return_delta_pct: number | null;
      beat_reference: boolean;
    }
  >;
}

export interface ExperimentItem {
  spec_id: string;
  title: string;
  source: string;
  fingerprint: string;
  spec: Record<string, unknown>;
  development: PartitionEval;
  novelty: {
    state: string;
    closest_reference: string | null;
    max_structural_jaccard: number;
    max_signal_jaccard: number;
    max_signal_containment: number;
    explanation: string;
  };
  validation: PartitionEval | null;
  outcome: {
    final_status: string;
    qualified_candidate: boolean;
    reason: string;
    next_step: string;
  };
}

export interface CampaignDetail {
  campaign_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  config_hash: string;
  data_hash: string;
  code_hash: string;
  prior_campaign_id: string | null;
  validation_holdout_contaminated: boolean;
  contamination_label: string;
  validation_evaluated_once: boolean;
  development_only: boolean;
  partitions: {
    warmup_end: string;
    discovery_start: string;
    discovery_end: string;
    validation_start: string;
    validation_end: string;
    sealed_start: string | null;
    sealed_end: string | null;
  };
  coverage_report: {
    asset_count: number;
    symbols: string[];
    discovery_days: number;
    validation_days: number;
    sealed_days: number;
    blind_status: string;
    availability_convention: string;
  };
  proposal_audits: Array<Record<string, unknown>>;
  experiments: ExperimentItem[];
  summary: {
    total_candidates: number;
    dev_passed: number;
    validation_evaluated: number;
    qualified_for_shadow: number;
    rejected: number;
    zero_pass_honest_completion: boolean;
  };
}

export interface ShadowStrategyItem {
  strategy_key: string;
  title: string;
  source_campaign_id: string | null;
  spec_fingerprint: string | null;
  state: string;
  observations_count: number;
  evalue: number;
  peak_evalue: number;
  cumulative_return_pct: number;
  cumulative_excess_pct: number;
  max_drawdown_pct: number;
  consecutive_losses: number;
  last_reason: string;
  updated_at: string;
}

export interface ShadowStrategyDetail extends ShadowStrategyItem {
  spec: Record<string, unknown>;
  shadow_threshold: number;
  live_threshold: number;
  policy: Record<string, number>;
  series: EValuePoint[];
}

export interface AuditResponse {
  passed: boolean;
  verdict: string;
  rejection_reasons: string[];
  summary: {
    n_trades: number;
    avg_net_return_pct: number;
    win_rate_pct: number;
    profit_factor: number;
  };
  bootstrap_ci: {
    mean: number;
    ci_lower: number;
    ci_upper: number;
    n_clusters: number;
    passed: boolean;
    warning?: string;
  };
  cost_stress: Record<
    string,
    { multiplier: number; avg_net_return: number; profit_factor: number; passed: boolean }
  >;
  concentration: {
    passed: boolean;
    max_asset_pct: number;
    max_sector_pct: number;
    top_asset: string | null;
    top_sector: string | null;
  };
  evalue: {
    evalue: number;
    peak_evalue: number;
    threshold: number;
    rejected: boolean;
    n: number;
    series: EValuePoint[];
  };
}

export interface RuntimeSettingsResponse {
  llm: {
    provider: string;
    model: string;
    base_url: string;
    api_key_configured: boolean;
    api_key_masked: string;
  };
  market: {
    default_preset: string;
    default_symbols: string[];
  };
  notifications: {
    telegram_configured: boolean;
    telegram_chat_id: string;
    discord_configured: boolean;
    generic_webhook_configured: boolean;
  };
  scheduler: {
    enabled: boolean;
    shadow_cron: string;
    campaign_cron: string;
    runtime: {
      running: boolean;
      jobs: Array<{ id: string; next_run_time: string | null; trigger: string }>;
    };
  };
}

export interface MCPToolSchema {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export interface MCPServerItem {
  server_id: string;
  name: string;
  transport: string;
  url: string;
  headers_masked: Record<string, string>;
  command: string;
  args: string[];
  enabled: boolean;
  include_in_discovery: boolean;
  discovery_tools: Array<{ tool_name: string; arguments?: Record<string, unknown> }>;
  discovered_tools: MCPToolSchema[];
  tool_count: number;
  last_status: string;
  last_error: string;
  last_latency_ms: number | null;
  updated_at: string;
}

export interface MCPHubResponse {
  allow_stdio_mcp: boolean;
  servers: MCPServerItem[];
  quantseal_mcp_server: {
    http_endpoint: string;
    stdio_command: string;
    tools: MCPToolSchema[];
  };
}
