# QuantSeal

**Self-Hosted Anti-Overfitting Autonomous Quant Research Lab · by [berichlab](https://berich.cc/quantseal)**

[English](README.md) | [繁體中文](README.zh-TW.md) | [Official Website (berich.cc)](https://berich.cc/quantseal)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-10b981.svg?style=for-the-badge)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-38bdf8.svg?style=for-the-badge)](./pyproject.toml)
[![Zero Exec AST](https://img.shields.io/badge/AI_Safety-Zero_exec()_JSON_AST-f59e0b.svg?style=for-the-badge)](#the-7-anti-overfitting-invariants)
[![By berichlab](https://img.shields.io/badge/Maintained_by-berichlab-27272a.svg?style=for-the-badge)](https://berich.cc/quantseal)

<!-- Replace `YOUR_PARTNER_CODE` once approved on Hostinger Open-Source Partners -->
[![Deploy on Hostinger](https://assets.hostinger.com/vps/deploy.svg)](https://www.hostinger.com/deploy?template=berichlab/quantseal&ref=YOUR_PARTNER_CODE)

> **Most AI backtesters optimize until they fool you.**
> QuantSeal is a 24/7 self-hosted research operating system built to **stop LLMs—and yourself—from overfitting historical data**.

Every autonomous hypothesis is expressed as a **zero-`exec` bounded JSON AST**, sealed against a **SHA-256 frozen dataset snapshot**, forced to beat **three falsification control arms**, evaluated on a **single-shot frozen validation window** (automatically flagging prior-revision contamination), and promoted strictly via **anytime-valid test-martingale E-values** on forward out-of-sample returns.

![QuantSeal Research Governance Overview](docs/screenshots/01-overview.png)

---

## Visual Walkthrough & Usage Guide

When you deploy QuantSeal for the first time, it ships with an offline deterministic demo workspace (`QUANTSEAL_AUTO_DEMO=true`) so you can inspect every anti-overfitting safeguard within 60 seconds—even before connecting an LLM key or market data feed.

### 1. Research Governance Overview

![Research Governance Overview](docs/screenshots/01-overview.png)

- **Top KPI Strip**: Track sealed campaigns vs. pending single-shot seals, highest forward anytime-valid peak E-value, active vs. circuit-retired strategies on the forward ladder, and the cryptographic `engine_code_hash`.
- **Featured Forward E-Value Monitor**: Plots the log-scale test-martingale capital process $K(t)$ against the **20x Paper** ($\alpha = 0.05$) and **100x Live Candidate** ($\alpha = 0.01$) Ville inequality gates.
- **Governance Ledger**: Append-only audit log of campaign seals, shadow promotions, circuit-breaker retirements, and 24/7 scheduler runs.

---

### 2. Immutable Campaigns & 4-Arm Falsification Matrix

![Immutable Campaigns and 4-Arm Falsification Matrix](docs/screenshots/02-campaigns-4arm.png)

1. Click **New Campaign** to launch a bounded discovery run on **Demo**, **Yahoo Finance** (US ETFs/Equities), **Binance Public Spot** (Crypto), or local **CSV/Parquet** datasets.
2. Every campaign immediately locks three cryptographic hashes (`Config Hash`, `Frozen Data SHA-256`, `Engine Code Hash`) and freezes the temporal split (`Discovery 60%` / `Validation 20%` / `Sealed Holdout 20%`).
3. Every candidate hypothesis is tested on the exact same observable mask across **four paired arms**:
   - `full`: `context AND setup AND trigger`
   - `baseline`: `context` alone
   - `ablation`: removes `setup` (or `context`) to verify each component actually contributes edge
   - `reverse_control`: keeps `context` + `setup` identical while inverting `trigger`
   - As shown above, even a `+17.69%` discovery candidate is honestly **rejected** (`Failed ablation test`) if removing the setup filter performs equally well or better.
4. Click **JSON AST** to inspect the exact declarative rule tree (zero Python `exec()`).
5. When satisfied with discovery diagnostics, click **Unlock Single-Shot Validation** on a `Pending Seal` campaign. The seal is consumed atomically once—any subsequent revision referencing an exposed parent is permanently labeled `contaminated_development_from_prior_revision`.

---

### 3. Forward-Only Shadow Ladder & Anytime-Valid E-Value Tracking

![Forward-Only Shadow Ladder](docs/screenshots/03-shadow-ladder.png)

- **Backtests never promote a strategy.** Click **Track in Shadow** on a qualified candidate (or enroll via API) to start accumulating forward out-of-sample returns.
- **Continuous monitoring without peeking inflation**: Because $K(t)$ is a non-negative supermartingale under $H_0: \mathbb{E}[\Delta] \le \text{cost}$, you can inspect performance after every single day without inflating Type-I error:
  - `shadow -> paper`: requires `>= 30` forward observations, peak E-value `>= 20x`, positive excess return, and `MDD <= 15%`.
  - `paper -> live_candidate`: requires `>= 60` forward observations and peak E-value `>= 100x` (final live activation always requires explicit human sign-off).
  - **Automatic Circuit Breakers**: strategies breaching forward `MDD >= 20%`, `5` consecutive losses, or `-10%` cumulative benchmark lag are automatically demoted or retired (as shown on `High-Volume Oversold Rebound`).
- Use the **Record Forward Out-of-Sample Observation** bar—or `POST /api/shadow/{strategy_key}/observations`—to log new daily forward returns and watch the martingale recompute in real time.

---

### 4. Standalone Statistical Gate Auditor (Works with Any External Backtester)

![Standalone Statistical Gate Auditor](docs/screenshots/04-gate-auditor.png)

Already using **TradingView, Freqtrade, Backtrader, or VectorBT**? Paste any trade export CSV (`entry_date, symbol, sector, gross, net`) into **Gate Auditor** and click **Run Fail-Closed Audit** to obtain an independent verdict across:
- **Date-Clustered Bootstrap 95% CI** (resamples by trading date; fails closed when `< 5` distinct dates so same-day signals cannot masquerade as independent samples)
- **1.5x & 2.0x Cost Friction Stress Test**
- **Single-Asset & Single-Sector Profit Concentration Cap**
- **Anytime-Valid Test-Martingale E-Value Trajectory**

---

### 5. Bidirectional MCP Hub (Connect External MCPs & Expose QuantSeal to AI Agents)

![MCP Hub and External Connectors](docs/screenshots/06-mcp-hub.png)

QuantSeal natively speaks the **Model Context Protocol (JSON-RPC 2.0)** in both directions:

- **Connect External MCP Servers (Outbound Client)**: Register any third-party **Streamable HTTP / SSE** MCP server (macro indicators, on-chain telemetry, SEC filings, volatility term structure, news) directly from **MCP Hub**, click **Discover Tools**, test invocations in the **Live Tool Tester**, and toggle **Include in Discovery** to inject read-only context into the discovery evidence cards (strictly quarantined to the discovery partition with `pit_warning` and automatic secret redaction). Local `stdio` MCP subprocesses stay fail-closed (`QUANTSEAL_ALLOW_STDIO_MCP=false`) unless explicitly opted in.
- **Expose QuantSeal as an MCP Server (Inbound Server)**: Connect **Claude Desktop, Cursor, Claude Code, Codex, or OpenClaw** directly to QuantSeal over Streamable HTTP (`POST /api/mcp`) or local stdio (`python -m quantseal mcp`) to invoke 6 built-in governance tools:
  - `quantseal_audit_trades` — Run the full fail-closed statistical audit on external trade lists
  - `quantseal_compute_evalue` — Compute anytime-valid test-martingale E-values on paired return differences
  - `quantseal_list_campaigns` / `quantseal_get_campaign` — Inspect sealed SHA-256 campaigns and 4-arm falsification matrices
  - `quantseal_list_shadow_ladder` / `quantseal_record_shadow_observation` — Read forward ladder states or append new out-of-sample observations

```json
{
  "mcpServers": {
    "quantseal": {
      "url": "http://localhost:8000/api/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_QUANTSEAL_ADMIN_PASSWORD"
      }
    }
  }
}
```

---

### 6. BYOK LLM, 24/7 Scheduler & Alert Channels

![Lab Settings and 24/7 Automation](docs/screenshots/05-settings-automation.png)

- **BYOK LLM Proposal Engine**: Plug in your own API key for **OpenAI**, **Anthropic Claude**, **Google Gemini**, or any **OpenAI-Compatible** endpoint (OpenRouter, local Ollama, vLLM). Keys are redacted from audit logs and masked in API responses.
- **24/7 Background Scheduler (UTC)**: Configure cron schedules for daily shadow reconciliation (`0 22 * * 1-5`) and optional weekly autonomous discovery cycles.
- **Alert Channels**: Connect **Telegram Bot**, **Discord Webhook**, or a generic JSON webhook and verify delivery with **Test Alert**.

---

### 7. Native Bilingual Console (`English` & `繁體中文`)

![Traditional Chinese Research Console](docs/screenshots/07-overview-zh-tw.png)

Switch seamlessly between **English** and **Traditional Chinese (`繁體中文`)** using the sidebar `EN / 繁中` toggle, automatic browser locale detection, or `?lang=zh-TW` / `?lang=en` query parameter across every view, modal, chart, and MCP tool tester.

---

## Architecture

```mermaid
flowchart LR
    D["Public / CSV Market Data<br/>(Yahoo, Binance Spot, CSV/Parquet)"] --> S["SHA-256 Frozen Snapshot<br/>Warmup / Discovery 60% / Val 20% / Sealed 20%"]
    M["External MCP Servers<br/>(Streamable HTTP/SSE, Read-Only)"] --> E
    S --> E["Discovery-Only Evidence Cards<br/>(Validation physically excluded)"]
    E --> P["BYOK LLM Proposer<br/>(OpenAI / Claude / Gemini / Ollama)<br/>Pre-call quota reservation"]
    P --> G["Zero-exec Bounded JSON AST Validator<br/>lag >= 0, depth <= 4, NaN == False"]
    G --> F["4-Arm Falsification Evaluator<br/>Full vs Baseline / Ablation / Reverse<br/>t+1 open, fixed-slot ledger, cost stress"]
    F --> V{"Single-Shot Frozen Validation<br/>(Locked after 1 use; tracks contamination)"}
    V --> L["Forward-Only Shadow Ladder<br/>Anytime-Valid E-Value Martingale<br/>shadow -> paper (20x) -> live_candidate (100x)"]
    L --> N["24/7 Scheduler + Alerts<br/>(Telegram / Discord / Webhook)"]
    L --> MS["QuantSeal MCP Server<br/>(POST /api/mcp & stdio)<br/>Claude / Cursor / Codex / OpenClaw"]
```

---

## The 7 Anti-Overfitting Invariants

| # | Invariant | What It Prevents |
|---|---|---|
| **1** | **Zero-`exec` Bounded JSON AST** | LLMs never execute arbitrary Python (`src`, `exec`, `eval`, `__dunder__` rejected). Strictly bounded `lag >= 0`, `lag + window <= 60`, AST depth `<= 4`, max 32 nodes, static contradiction rejection, and `NaN` comparisons always evaluate `False`. |
| **2** | **Cryptographic Campaign Seal** | Every campaign freezes `config_hash`, `data_hash` (exact float + NaN mask SHA-256), and `code_hash`. Resuming after tampering raises `CampaignImmutableMismatchError`. |
| **3** | **Single-Shot Frozen Validation** | Validation can be unlocked **at most once** per campaign (`validation_evaluated_once = True`). Re-running returns sealed verdicts untouched. |
| **4** | **Prior-Revision Contamination Tracking** | Creating a new campaign referencing a parent whose validation window was already revealed automatically downgrades overlapping dates to `contaminated_development_from_prior_revision`. |
| **5** | **4-Arm Falsification Matrix** | Every candidate is simultaneously evaluated on the exact same observable mask across `full`, `baseline` (context only), `ablation` (setup removed), and `reverse_control` (inverted trigger). Sparse control arms fail closed as `inconclusive`. |
| **6** | **Causal Execution & Friction Realism** | Signals at close `t` execute strictly at next session open `t+1`. Open gaps are checked before intraday stops; trailing stop highs update **strictly after** exit checks; signals whose `max_hold_days` runway crosses a partition boundary are excluded before entry; missing bars lock capital and never backdate exits. Includes price-tiered slippage and `1.5x` / `2.0x` cost stress. |
| **7** | **Anytime-Valid E-Value Shadow Ladder** | Backtests **never** promote a strategy. Promotion (`shadow -> paper -> live_candidate`) uses Waudby-Smith & Ramdas test-martingale E-values (`P(sup K_t >= 1/alpha | H0) <= alpha`) with tail-safe bounded scaling verified against heavy left-skew nulls, plus automatic drawdown & losing-streak circuit breakers. |

---

## 60-Second Quickstart

### Option 1 — One-Click Deploy on Hostinger VPS (Recommended for 24/7 Self-Hosting)

1. Click the **Deploy on Hostinger** button at the top of this README (runs comfortably on a KVM 1 VPS with < 512MB RAM).
2. Set `QUANTSEAL_ADMIN_PASSWORD` in Hostinger Docker Manager's environment variables.
3. Open your deployment URL — QuantSeal boots with the pre-seeded demo workspace so you can explore immediately, then plug in your BYOK LLM key, external MCP connectors, and market universe.

### Option 2 — Docker Compose (Any Linux / macOS Server)

```bash
git clone https://github.com/berichlab/quantseal.git
cd quantseal
cp .env.example .env
# Edit QUANTSEAL_ADMIN_PASSWORD in .env

# Run prebuilt GHCR image:
docker compose up -d

# Or build locally from source:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Open `http://localhost:8000` (API Swagger docs at `http://localhost:8000/docs`, MCP Streamable HTTP endpoint at `http://localhost:8000/api/mcp`).

### Option 3 — Local Python + Frontend Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Build the static Research Console SPA (optional — API works standalone too)
cd frontend && npm install && npm run build && cd ..

# Run the server
QUANTSEAL_ADMIN_PASSWORD="" python -m quantseal serve

# Or run QuantSeal as a local stdio MCP server for Claude Desktop / Cursor
python -m quantseal mcp
```

---

## Programmatic Gate Auditor API

```bash
curl -X POST http://localhost:8000/api/audit/trades \
  -H "Authorization: Bearer $QUANTSEAL_ADMIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{
    "min_trades": 15,
    "trades": [
      {"entry_date": "2026-04-01", "symbol": "SPY", "sector": "Broad", "gross": 1.4, "net": 1.22},
      {"entry_date": "2026-04-02", "symbol": "QQQ", "sector": "Tech", "gross": 2.1, "net": 1.92}
    ]
  }'
```

---

## Supported Data Sources, Cost Presets, MCP & LLMs

- **Market Data Adapters**: `demo` (offline deterministic multi-sector OHLCV), `yahoo` (US equities/ETFs), `crypto` (Binance public spot daily OHLCV), `csv` (local `.csv` / `.parquet` with automatic custom numeric feature ingestion)
- **Market Cost Presets**: `us_equities`, `crypto_spot`, `tw_equities`, `custom`
- **BYOK LLMs**: `openai`, `anthropic`, `gemini`, `openai_compatible` (OpenRouter, local Ollama, vLLM, LiteLLM)
- **Bidirectional MCP**: Outbound Streamable HTTP / SSE (JSON-RPC 2.0) + opt-in local `stdio`; Inbound QuantSeal MCP Server at `POST /api/mcp` & `python -m quantseal mcp`
- **Bilingual Console UI**: Native **English** & **Traditional Chinese (`繁體中文`)** with instant switching
- **24/7 Alerts**: Telegram Bot, Discord Webhook, Generic JSON Webhook

---

## Running the Test Suite

```bash
pytest -v
ruff check quantseal tests
```

Includes unit, anti-leakage, causal exit-order, single-shot seal, prior-revision contamination, Monte Carlo symmetric + heavy left-skewed null E-value Type-I error checks, bidirectional MCP (JSON + SSE + fail-closed stdio + campaign discovery injection), and full FastAPI E2E tests.

---

## Built by berichlab

**QuantSeal** is open-sourced and maintained by **[berichlab](https://berich.cc)** — an independent quantitative research lab focused on reproducible trading systems, statistical falsification, and disciplined risk governance.

- Official Website: [berich.cc](https://berich.cc) · [QuantSeal Overview](https://berich.cc/quantseal)
- GitHub Organization: [github.com/berichlab](https://github.com/berichlab)
- Threads: [@berichlab](https://www.threads.com/@berichlab)
- Instagram: [@berichlab](https://www.instagram.com/berichlab/)

---

## Disclaimer & License

QuantSeal is a quantitative research governance and statistical falsification tool. It does **not** execute live brokerage orders, does **not** constitute financial or investment advice, and makes **no** guarantee of trading profitability.

Licensed under the [Apache License 2.0](./LICENSE).
