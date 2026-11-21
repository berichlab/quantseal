import React, { createContext, useContext, useEffect, useState } from "react";

export type Locale = "en" | "zh-TW";

const STORAGE_KEY = "quantseal_locale";

const DICT: Record<Locale, Record<string, string>> = {
  en: {
    // Nav & Chrome
    "app.tagline": "Anti-Overfitting Quant Research Lab",
    "nav.overview": "Overview",
    "nav.campaigns": "Campaigns",
    "nav.shadow": "Shadow Ladder",
    "nav.auditor": "Gate Auditor",
    "nav.mcp": "MCP Hub",
    "nav.settings": "Settings",
    "nav.lock": "Lock Console",
    "app.initializing": "Initializing QuantSeal...",

    // Login
    "login.label": "Admin Password",
    "login.placeholder": "Enter QUANTSEAL_ADMIN_PASSWORD",
    "login.submit": "Unlock Research Console",
    "login.verifying": "Verifying...",

    // Overview
    "overview.title": "Research Governance Overview",
    "overview.subtitle":
      "Zero-exec bounded discovery, single-shot validation seals, and anytime-valid forward tracking.",
    "overview.auditCta": "Audit External Trades",
    "overview.newCampaign": "New Campaign",
    "overview.openAuthPrefix": "Dashboard authentication is currently open. Set",
    "overview.openAuthSuffix": "before exposing this server publicly.",
    "overview.kpi.sealed": "Sealed Campaigns",
    "overview.kpi.total": "total",
    "overview.kpi.awaitingSeal": "awaiting single-shot seal",
    "overview.kpi.peakE": "Highest Peak E-Value",
    "overview.kpi.martingale": "martingale",
    "overview.kpi.gatesNote": "Paper gate 20x · Live candidate 100x",
    "overview.kpi.ladder": "Forward Ladder",
    "overview.kpi.active": "active",
    "overview.kpi.promoted": "promoted",
    "overview.kpi.retired": "circuit-retired",
    "overview.kpi.integrity": "Engine Integrity",
    "overview.kpi.byokUnset": "BYOK not configured",
    "overview.featuredFallback": "Forward Shadow Monitor",
    "overview.ladderBtn": "Ladder",
    "overview.ledgerTitle": "Governance Ledger",
    "overview.schedActive": "24/7 Active",
    "overview.schedManual": "Manual",
    "overview.noEvents": "No events logged yet.",
    "overview.obs": "obs",
    "overview.mcpBtn": "MCP Hub",

    // E-Value Chart
    "chart.title": "Test-Martingale Capital K(t) — Log Scale",
    "chart.paper": "Paper",
    "chart.live": "Live",
    "chart.empty": "No forward observations recorded yet.",
    "chart.ville": "Ville inequality: P(sup K(t) >= 1/alpha | H0) <= alpha",
    "chart.peak": "Peak",

    // Campaigns
    "campaigns.title": "Immutable Research Campaigns",
    "campaigns.subtitle":
      "Every campaign locks config, data, and code SHA-256 hashes and enforces single-shot frozen validation.",
    "campaigns.sealed": "Sealed",
    "campaigns.pending": "Pending Seal",
    "campaigns.contaminated": "Contaminated",
    "campaigns.loading": "Loading sealed ledger...",
    "campaigns.selectPrompt": "Select a campaign to inspect.",
    "campaigns.unlockBtn": "Unlock Single-Shot Validation",
    "campaigns.unlocking": "Evaluating & Sealing...",
    "campaigns.contamTitle": "Prior-Revision Contamination Detected:",
    "campaigns.contamBody1": "Parent campaign",
    "campaigns.contamBody2": "already exposed this validation window. Results are permanently downgraded to",
    "campaigns.configHash": "Config Hash",
    "campaigns.dataHash": "Frozen Data SHA-256",
    "campaigns.codeHash": "Engine Code Hash",
    "campaigns.discPart": "Discovery (60%):",
    "campaigns.valPart": "Validation (20%, Single-Shot):",
    "campaigns.sealedPart": "Sealed Holdout (20%):",
    "campaigns.jsonAst": "JSON AST",
    "campaigns.hideAst": "Hide AST",
    "campaigns.trackShadow": "Track in Shadow",
    "campaigns.enrolling": "Enrolling...",
    "campaigns.armHeader": "Arm (Discovery)",
    "campaigns.trades": "Trades",
    "campaigns.avgNet": "Avg Net %",
    "campaigns.cumPort": "Cum Port %",
    "campaigns.pf": "PF",
    "campaigns.stress15": "1.5x Stress",
    "campaigns.beatsRef": "Beats Ref",
    "campaigns.yes": "Yes",
    "campaigns.no": "No",
    "campaigns.target": "target",
    "campaigns.singleShotVal": "SINGLE-SHOT VALIDATION:",
    "campaigns.novelty": "Novelty:",
    "campaigns.boundaryExcluded": "Boundary-excluded:",
    "campaigns.assets": "assets",
    "campaigns.status": "Status:",
    "campaigns.devShort": "dev",
    "campaigns.verdictLabel": "verdict:",

    // New Campaign Modal
    "newCamp.title": "Launch Bounded Research Campaign",
    "newCamp.subtitle": "Freezes dataset snapshot SHA-256 before evaluating any candidate.",
    "newCamp.id": "Campaign ID",
    "newCamp.source": "Market Data Source",
    "newCamp.sourceDemo": "Demo Synthetic Multi-Sector (Offline)",
    "newCamp.sourceYahoo": "Yahoo Finance (US ETFs / Equities)",
    "newCamp.sourceCrypto": "Binance Public Spot (Crypto Daily)",
    "newCamp.costPreset": "Cost Friction Preset",
    "newCamp.costUs": "US Equities (1bp fee + 8bp slip)",
    "newCamp.costCrypto": "Crypto Spot (10bp fee + 10bp slip)",
    "newCamp.costTw": "Taiwan Equities (3.99bp + 30bp tax)",
    "newCamp.costCustom": "Custom Neutral (5bp + 10bp)",
    "newCamp.symbols": "Symbols (Comma-Separated)",
    "newCamp.prior": "Prior Campaign Lineage (Optional — Enforces Contamination Check)",
    "newCamp.priorNone": "None (Fresh Cohort)",
    "newCamp.devOnly": "Discovery-only first (keep single-shot validation sealed until reviewed)",
    "newCamp.useLlm": "Enable BYOK LLM bounded-JSON proposals",
    "newCamp.llmUnset": "(configure API key in Settings first)",
    "newCamp.useMcp": "Attach enabled External MCP discovery tools (read-only context)",
    "newCamp.cancel": "Cancel",
    "newCamp.run": "Run Campaign",
    "newCamp.running": "Running Discovery...",

    // Shadow Ladder
    "shadow.title": "Forward-Only Shadow Ladder",
    "shadow.subtitle":
      "Promotions depend strictly on forward out-of-sample E-values (20x Paper / 100x Live Candidate); backtest scores never promote.",
    "shadow.reconcile": "Run Reconcile",
    "shadow.peakE": "Peak E",
    "shadow.excess": "Excess",
    "shadow.mdd": "MDD",
    "shadow.peakLabel": "Peak Anytime E-Value",
    "shadow.forwardObs": "forward obs",
    "shadow.selectPrompt": "Select a strategy on the ladder.",
    "shadow.recordTitle": "Record Forward Out-of-Sample Observation",
    "shadow.date": "Date",
    "shadow.stratPct": "Strategy %",
    "shadow.benchPct": "Benchmark %",
    "shadow.note": "Note",
    "shadow.optional": "optional",
    "shadow.append": "Append",
    "shadow.saving": "Saving...",
    "shadow.savedMsg": "Forward observation recorded and E-value martingale recomputed.",
    "shadow.reconciled": "Reconciled",
    "shadow.strategies": "strategies",
    "shadow.transitions": "transitions",

    // Gate Auditor
    "auditor.title": "Standalone Statistical Gate Auditor",
    "auditor.subtitle":
      "Paste trade exports from TradingView, Freqtrade, Backtrader, or VectorBT to test Cluster Bootstrap CI, 1.5x/2.0x Cost Stress, Concentration, and E-values.",
    "auditor.run": "Run Fail-Closed Audit",
    "auditor.running": "Auditing...",
    "auditor.minTrades": "Min Trades",
    "auditor.maxAsset": "Max Single Asset %",
    "auditor.csvLabel": "Trades CSV (entry_date, symbol, sector, gross, net)",
    "auditor.emptyPrompt":
      'Click "Run Fail-Closed Audit" to evaluate the sample trade ledger or paste your own CSV.',
    "auditor.verdict": "Verdict:",
    "auditor.avgNet": "Avg Net",
    "auditor.win": "Win",
    "auditor.bootCi": "Cluster Bootstrap 95% CI",
    "auditor.clusters": "date clusters",
    "auditor.costStress": "Cost Stress (1.5x / 2.0x)",
    "auditor.topAsset": "Top Asset Concentration",
    "auditor.top": "top:",

    // MCP Hub
    "mcp.title": "MCP Hub & External Connectors",
    "mcp.subtitle":
      "Connect QuantSeal to external MCP servers (macro, on-chain, news, filings) or expose QuantSeal's own statistical gates to Claude, Cursor, Codex, and OpenClaw.",
    "mcp.addBtn": "Add External MCP",
    "mcp.externalTitle": "Connected External MCP Servers",
    "mcp.empty": "No external MCP servers connected yet. Add any Streamable HTTP / JSON-RPC 2.0 MCP endpoint.",
    "mcp.discover": "Discover Tools",
    "mcp.discovering": "Connecting...",
    "mcp.delete": "Remove",
    "mcp.includeDiscovery": "Include in Discovery",
    "mcp.toolsCount": "tools",
    "mcp.invokeTitle": "Live Tool Tester",
    "mcp.selectTool": "Select discovered tool",
    "mcp.argsJson": "Arguments (JSON)",
    "mcp.runTool": "Call Tool",
    "mcp.runningTool": "Calling...",
    "mcp.serverTitle": "Expose QuantSeal as an MCP Server",
    "mcp.serverDesc":
      "Connect Claude Desktop, Cursor, Claude Code, Codex, or OpenClaw directly to QuantSeal via Streamable HTTP or local stdio.",
    "mcp.httpEndpoint": "Streamable HTTP Endpoint (JSON-RPC 2.0)",
    "mcp.stdioCmd": "Local Stdio Command",
    "mcp.copy": "Copy",
    "mcp.copied": "Copied",
    "mcp.builtinTools": "Built-in QuantSeal MCP Tools",
    "mcp.modalTitle": "Register External MCP Server",
    "mcp.modalSubtitle": "Supports MCP Streamable HTTP / SSE (JSON-RPC 2.0). Auth headers are masked at rest.",
    "mcp.serverId": "Server ID",
    "mcp.serverName": "Display Name",
    "mcp.transport": "Transport",
    "mcp.url": "MCP Endpoint URL",
    "mcp.authHeader": "Authorization Header (Optional)",
    "mcp.discoveryTool": "Auto-Query Tool in Discovery (Optional tool name)",
    "mcp.stdioDisabled": "Local stdio transport is disabled on this server (set QUANTSEAL_ALLOW_STDIO_MCP=true to enable).",
    "mcp.register": "Register Connector",
    "mcp.registering": "Registering...",

    // Settings
    "settings.title": "Lab Settings & 24/7 Automation",
    "settings.subtitle":
      "Bring your own LLM key, configure default markets, cron schedules, and alert channels.",
    "settings.testAlert": "Test Alert",
    "settings.save": "Save Settings",
    "settings.saving": "Saving...",
    "settings.savedMsg": "Settings saved and 24/7 scheduler reloaded.",
    "settings.testSent": "Test alert dispatched to:",
    "settings.testNone": "No alert sent. Configure Telegram or Discord first.",
    "settings.llmTitle": "BYOK LLM Proposal Engine",
    "settings.provider": "Provider",
    "settings.disabled": "Disabled (Seeds Only)",
    "settings.openaiCompat": "OpenAI-Compatible (Ollama)",
    "settings.model": "Model",
    "settings.apiKey": "API Key",
    "settings.apiKeyHint": "Leave blank to keep existing key",
    "settings.baseUrl": "Custom Base URL (OpenRouter / Local Ollama)",
    "settings.schedTitle": "24/7 Background Scheduler (UTC)",
    "settings.schedEnable": "Enable automated VPS background jobs",
    "settings.shadowCron": "Shadow Reconcile Cron",
    "settings.campaignCron": "Autonomous Campaign Cron",
    "settings.marketPreset": "Default Market Preset",
    "settings.symbols": "Default Universe Symbols",
    "settings.notifTitle": "Telegram & Discord Alert Channels",
    "settings.tgToken": "Telegram Bot Token",
    "settings.tgChat": "Telegram Chat ID",
    "settings.discord": "Discord Webhook URL",
    "settings.configured": "(configured)",
    "settings.stored": "stored:",
  },

  "zh-TW": {
    // Nav & Chrome
    "app.tagline": "防過擬合 AI 量化研究實驗室",
    "nav.overview": "研究總覽",
    "nav.campaigns": "研究活動",
    "nav.shadow": "前瞻影子天梯",
    "nav.auditor": "統計閘門審計",
    "nav.mcp": "MCP 擴充中心",
    "nav.settings": "系統設定",
    "nav.lock": "鎖定控制台",
    "app.initializing": "正在初始化 QuantSeal...",

    // Login
    "login.label": "管理員密碼",
    "login.placeholder": "請輸入 QUANTSEAL_ADMIN_PASSWORD",
    "login.submit": "解鎖研究控制台",
    "login.verifying": "驗證中...",

    // Overview
    "overview.title": "研究治理總覽",
    "overview.subtitle":
      "零 exec() 有界策略探索、單次凍結驗證封印與隨時有效的 Test-Martingale 前瞻追蹤。",
    "overview.auditCta": "審計外部交易",
    "overview.newCampaign": "建立研究活動",
    "overview.openAuthPrefix": "控制台目前未啟用密碼驗證。公開部署前請務必設定",
    "overview.openAuthSuffix": "以保護研究資料與 API。",
    "overview.kpi.sealed": "已封印活動",
    "overview.kpi.total": "總計",
    "overview.kpi.awaitingSeal": "筆等待單次驗證封印",
    "overview.kpi.peakE": "最高峰值 E-Value",
    "overview.kpi.martingale": "鞅資本倍數",
    "overview.kpi.gatesNote": "模擬盤門檻 20x · 實盤候選 100x",
    "overview.kpi.ladder": "前瞻天梯策略",
    "overview.kpi.active": "運行中",
    "overview.kpi.promoted": "已晉升",
    "overview.kpi.retired": "風控退役",
    "overview.kpi.integrity": "引擎完整性雜湊",
    "overview.kpi.byokUnset": "尚未設定 BYOK 金鑰",
    "overview.featuredFallback": "前瞻影子追蹤監控",
    "overview.ladderBtn": "前往天梯",
    "overview.ledgerTitle": "治理事件帳本",
    "overview.schedActive": "24/7 排程運作中",
    "overview.schedManual": "手動模式",
    "overview.noEvents": "目前尚無治理事件紀錄。",
    "overview.obs": "筆觀察",
    "overview.mcpBtn": "MCP 擴充中心",

    // E-Value Chart
    "chart.title": "Test-Martingale 資本曲線 K(t) — 對數座標",
    "chart.paper": "模擬盤 (Paper)",
    "chart.live": "實盤候選 (Live)",
    "chart.empty": "尚未登錄前瞻樣本外觀察資料。",
    "chart.ville": "Ville 不等式保證：P(sup K(t) >= 1/alpha | H0) <= alpha",
    "chart.peak": "峰值",

    // Campaigns
    "campaigns.title": "不可變研究活動帳本",
    "campaigns.subtitle":
      "每次活動建立時即鎖死設定、資料快照與引擎程式碼 SHA-256 雜湊，並強制單次凍結驗證。",
    "campaigns.sealed": "已封印",
    "campaigns.pending": "待解鎖驗證",
    "campaigns.contaminated": "前代已污染",
    "campaigns.loading": "正在載入不可變帳本...",
    "campaigns.selectPrompt": "請從左側選擇一個研究活動進行檢視。",
    "campaigns.unlockBtn": "解鎖單次凍結驗證",
    "campaigns.unlocking": "驗證並永久封印中...",
    "campaigns.contamTitle": "偵測到前代驗證期污染：",
    "campaigns.contamBody1": "父代活動",
    "campaigns.contamBody2": "已揭曉重疊的驗證期區間，本次結果將永久降級標記為",
    "campaigns.configHash": "設定雜湊 (Config)",
    "campaigns.dataHash": "凍結資料 SHA-256",
    "campaigns.codeHash": "引擎程式碼雜湊",
    "campaigns.discPart": "開發探索期 (60%)：",
    "campaigns.valPart": "單次驗證期 (20%)：",
    "campaigns.sealedPart": "封存留出期 (20%)：",
    "campaigns.jsonAst": "檢視 JSON AST",
    "campaigns.hideAst": "隱藏 AST",
    "campaigns.trackShadow": "加入影子天梯",
    "campaigns.enrolling": "註冊中...",
    "campaigns.armHeader": "對照臂（開發期）",
    "campaigns.trades": "交易數",
    "campaigns.avgNet": "均筆淨報酬",
    "campaigns.cumPort": "累積組合報酬",
    "campaigns.pf": "獲利因子",
    "campaigns.stress15": "1.5x 壓測",
    "campaigns.beatsRef": "勝過對照",
    "campaigns.yes": "通過",
    "campaigns.no": "未過",
    "campaigns.target": "主策略",
    "campaigns.singleShotVal": "單次凍結驗證結論：",
    "campaigns.novelty": "新穎度審計：",
    "campaigns.boundaryExcluded": "跨邊界預先排除訊號：",
    "campaigns.assets": "檔標的",
    "campaigns.status": "狀態：",
    "campaigns.devShort": "開發通過",
    "campaigns.verdictLabel": "裁決：",

    // New Campaign Modal
    "newCamp.title": "發起有界研究活動",
    "newCamp.subtitle": "執行任何候選策略前先凍結資料快照並計算 SHA-256 指紋。",
    "newCamp.id": "活動識別碼 (Campaign ID)",
    "newCamp.source": "市場資料來源",
    "newCamp.sourceDemo": "內建多產業合成範例資料（離線）",
    "newCamp.sourceYahoo": "Yahoo Finance（美股 ETF／個股）",
    "newCamp.sourceCrypto": "Binance 公開現貨（加密貨幣日線）",
    "newCamp.costPreset": "交易成本模型預設",
    "newCamp.costUs": "美股現貨（1bp 手續費 + 8bp 滑價）",
    "newCamp.costCrypto": "加密現貨（10bp 手續費 + 10bp 滑價）",
    "newCamp.costTw": "台股現貨（3.99bp 手續費 + 30bp 交易稅）",
    "newCamp.costCustom": "中性自訂（5bp + 10bp）",
    "newCamp.symbols": "標的清單（逗號分隔）",
    "newCamp.prior": "父代血緣參照（選填 — 自動啟用驗證期污染檢查）",
    "newCamp.priorNone": "無（全新研究世代）",
    "newCamp.devOnly": "先僅跑開發期（檢視四臂對照後再手動解鎖唯一一次驗證）",
    "newCamp.useLlm": "啟用 BYOK LLM 有界 JSON 策略提案",
    "newCamp.llmUnset": "（請先到系統設定填入 API Key）",
    "newCamp.useMcp": "注入已啟用的外部 MCP 探索工具上下文（唯讀、限開發期）",
    "newCamp.cancel": "取消",
    "newCamp.run": "執行研究活動",
    "newCamp.running": "執行開發期評估中...",

    // Shadow Ladder
    "shadow.title": "純前瞻影子天梯",
    "shadow.subtitle":
      "策略晉升完全取決於註冊後的前瞻樣本外 E-Value（20x 升模擬盤／100x 升實盤候選），歷史回測永遠不予晉升。",
    "shadow.reconcile": "立即執行對帳",
    "shadow.peakE": "峰值 E",
    "shadow.excess": "累積超額",
    "shadow.mdd": "最大回撤",
    "shadow.peakLabel": "前瞻隨時有效峰值 E-Value",
    "shadow.forwardObs": "筆前瞻觀察",
    "shadow.selectPrompt": "請從左側選擇一支天梯策略。",
    "shadow.recordTitle": "登錄前瞻樣本外觀察值",
    "shadow.date": "交易日期",
    "shadow.stratPct": "策略報酬 %",
    "shadow.benchPct": "基準報酬 %",
    "shadow.note": "備註",
    "shadow.optional": "選填",
    "shadow.append": "寫入觀察",
    "shadow.saving": "儲存中...",
    "shadow.savedMsg": "已寫入前瞻觀察並即時重算 E-Value 鞅曲線與天梯狀態。",
    "shadow.reconciled": "已完成對帳：",
    "shadow.strategies": "支策略",
    "shadow.transitions": "次狀態轉移",

    // Gate Auditor
    "auditor.title": "獨立統計閘門審計器",
    "auditor.subtitle":
      "直接貼上 TradingView、Freqtrade、Backtrader 或 VectorBT 匯出的交易明細 CSV，立即執行日期分群 Bootstrap 95% CI、1.5x/2.0x 成本壓測、集中度與 E-Value 審計。",
    "auditor.run": "執行嚴格審計",
    "auditor.running": "審計計算中...",
    "auditor.minTrades": "最低交易筆數",
    "auditor.maxAsset": "單一標的獲利上限 %",
    "auditor.csvLabel": "交易紀錄 CSV（entry_date, symbol, sector, gross, net）",
    "auditor.emptyPrompt": "點擊右上角「執行嚴格審計」即可檢驗範例交易帳本，或貼上您自己的回測匯出資料。",
    "auditor.verdict": "審計裁決：",
    "auditor.avgNet": "均筆淨報酬",
    "auditor.win": "勝率",
    "auditor.bootCi": "日期分群 Bootstrap 95% CI",
    "auditor.clusters": "個獨立交易日",
    "auditor.costStress": "成本壓測 (1.5x / 2.0x)",
    "auditor.topAsset": "單一標的獲利集中度",
    "auditor.top": "最大來源：",

    // MCP Hub
    "mcp.title": "MCP 擴充中心與雙向橋接",
    "mcp.subtitle":
      "對外串接任意第三方 MCP 伺服器（總經、鏈上、財報、新聞工具），同時將 QuantSeal 自身的統計閘門與影子天梯開放給 Claude、Cursor、Codex 或 OpenClaw 呼叫。",
    "mcp.addBtn": "新增外部 MCP",
    "mcp.externalTitle": "已串接的外部 MCP 伺服器",
    "mcp.empty": "尚未串接外部 MCP 伺服器。點擊右上角即可新增 Streamable HTTP / JSON-RPC 2.0 MCP 端點。",
    "mcp.discover": "探索工具列表",
    "mcp.discovering": "連線探索中...",
    "mcp.delete": "移除",
    "mcp.includeDiscovery": "納入探索期上下文",
    "mcp.toolsCount": "個工具",
    "mcp.invokeTitle": "即時工具呼叫測試台",
    "mcp.selectTool": "選擇已探索工具",
    "mcp.argsJson": "呼叫參數 (JSON)",
    "mcp.runTool": "呼叫工具",
    "mcp.runningTool": "執行中...",
    "mcp.serverTitle": "將 QuantSeal 作為 MCP Server 對外開放",
    "mcp.serverDesc":
      "讓 Claude Desktop、Cursor、Claude Code、Codex 或 OpenClaw 透過 Streamable HTTP 或本機 stdio 直接呼叫 QuantSeal 統計閘門與天梯工具。",
    "mcp.httpEndpoint": "Streamable HTTP 端點 (JSON-RPC 2.0)",
    "mcp.stdioCmd": "本機 Stdio 啟動指令",
    "mcp.copy": "複製",
    "mcp.copied": "已複製",
    "mcp.builtinTools": "內建 QuantSeal MCP 工具清單",
    "mcp.modalTitle": "註冊外部 MCP 伺服器",
    "mcp.modalSubtitle": "支援標準 MCP Streamable HTTP / SSE (JSON-RPC 2.0)，驗證標頭會自動遮罩保存。",
    "mcp.serverId": "伺服器識別碼 (Server ID)",
    "mcp.serverName": "顯示名稱",
    "mcp.transport": "傳輸協定",
    "mcp.url": "MCP 端點網址 (URL)",
    "mcp.authHeader": "Authorization 標頭（選填，如 Bearer xxx）",
    "mcp.discoveryTool": "探索期自動查詢工具名稱（選填，唯讀）",
    "mcp.stdioDisabled": "基於 VPS 安全預設停用本機 stdio 傳輸（需設定 QUANTSEAL_ALLOW_STDIO_MCP=true 方可啟用）。",
    "mcp.register": "新增連接器",
    "mcp.registering": "儲存中...",

    // Settings
    "settings.title": "實驗室設定與 24/7 自動化",
    "settings.subtitle": "自帶 LLM API Key、設定預設市場與交易成本、排程 Cron 與通知渠道。",
    "settings.testAlert": "發送測試通知",
    "settings.save": "儲存設定",
    "settings.saving": "儲存中...",
    "settings.savedMsg": "設定已儲存並重新載入 24/7 背景排程器。",
    "settings.testSent": "已發送測試通知至：",
    "settings.testNone": "尚未發送通知，請先設定 Telegram 或 Discord。",
    "settings.llmTitle": "BYOK LLM 假說提案引擎",
    "settings.provider": "模型供應商",
    "settings.disabled": "停用（僅使用內建種子策略）",
    "settings.openaiCompat": "OpenAI 相容端點（Ollama／OpenRouter）",
    "settings.model": "模型名稱",
    "settings.apiKey": "API 金鑰",
    "settings.apiKeyHint": "留空則沿用已保存的金鑰",
    "settings.baseUrl": "自訂 Base URL（OpenRouter / 本機 Ollama）",
    "settings.schedTitle": "24/7 背景排程器 (UTC)",
    "settings.schedEnable": "啟用 VPS 自動化背景排程",
    "settings.shadowCron": "影子天梯對帳 Cron",
    "settings.campaignCron": "自動策略探索 Cron",
    "settings.marketPreset": "預設市場成本模型",
    "settings.symbols": "預設追蹤標的清單",
    "settings.notifTitle": "Telegram 與 Discord 通知渠道",
    "settings.tgToken": "Telegram Bot Token",
    "settings.tgChat": "Telegram Chat ID",
    "settings.discord": "Discord Webhook 網址",
    "settings.configured": "（已設定）",
    "settings.stored": "已保存：",
  },
};

function detectInitialLocale(): Locale {
  if (typeof window !== "undefined") {
    const param = new URLSearchParams(window.location.search).get("lang");
    if (param === "zh-TW" || param === "zh" || param === "zh-Hant") return "zh-TW";
    if (param === "en") return "en";
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "zh-TW" || stored === "en") return stored;
    const nav = (window.navigator.language || "").toLowerCase();
    if (nav.startsWith("zh-tw") || nav.startsWith("zh-hant") || nav.startsWith("zh-hk")) {
      return "zh-TW";
    }
  }
  return "en";
}

interface I18nCtx {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nCtx>({
  locale: "en",
  setLocale: () => {},
  t: (k) => k,
});

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(detectInitialLocale);

  const setLocale = (next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore storage failure
    }
  };

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = (key: string): string => DICT[locale][key] ?? DICT.en[key] ?? key;

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
};

export const useI18n = () => useContext(I18nContext);
