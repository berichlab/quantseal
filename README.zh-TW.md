# QuantSeal

**可 24/7 自架的防過擬合 AI 量化研究實驗室 · 由 [berichlab](https://berich.cc/quantseal) 開源打造**

[English](README.md) | [繁體中文](README.zh-TW.md) | [官方網站 (berich.cc)](https://berich.cc/quantseal)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-10b981.svg?style=for-the-badge)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-38bdf8.svg?style=for-the-badge)](./pyproject.toml)
[![Zero Exec AST](https://img.shields.io/badge/AI_Safety-Zero_exec()_JSON_AST-f59e0b.svg?style=for-the-badge)](#七大防過擬合不變量)
[![By berichlab](https://img.shields.io/badge/Maintained_by-berichlab-27272a.svg?style=for-the-badge)](https://berich.cc/quantseal)

<!-- 通過 Hostinger Open-Source Partners 後，將 YOUR_PARTNER_CODE 換成你的分潤代碼 -->
[![Deploy on Hostinger](https://assets.hostinger.com/vps/deploy.svg)](https://www.hostinger.com/deploy?template=berichlab/quantseal&ref=YOUR_PARTNER_CODE)

> **多數 AI 回測框架都在不斷最佳化直到把你自己騙倒。**
> QuantSeal 是一套可 24/7 自架的研究治理系統，從底層制度**阻止 LLM 與人類靠反覆偷看驗證集來偽造 Alpha**。

每個策略假說都必須寫成**零 `exec()` 的有界 JSON AST**，鎖定 **SHA-256 不可變資料快照**，同步擊敗**三組證偽對照臂（Baseline / Ablation / Reverse Control）**，在**單次凍結驗證期**接受一次性檢驗（前代已揭曉區間自動標記為污染），最後嚴格依靠前瞻樣本外報酬的 **Anytime-Valid Test-Martingale E-Value** 決定天梯晉升與熔斷。

![QuantSeal 研究治理總覽（繁體中文介面）](docs/screenshots/07-overview-zh-tw.png)

---

## 畫面導覽與操作介紹

首次啟動 QuantSeal 時（`QUANTSEAL_AUTO_DEMO=true`），系統會自動建立離線示範工作區，不需先填任何 API Key 即可在 60 秒內體驗全部防自欺流程。控制台原生內建 **繁體中文／English 雙語介面**，點擊側邊欄底部 `EN / 繁中` 即可即時切換（亦支援瀏覽器語系自動偵測與 `?lang=zh-TW` 參數）。

### 1. 研究治理總覽（Overview）

![研究治理總覽（繁體中文）](docs/screenshots/07-overview-zh-tw.png)

- **頂部 KPI 卡片**：即時掌握已封印活動數、待解鎖單次驗證數、前瞻最高峰值 E-Value、天梯運行中與風控退役數，以及當前引擎 `engine_code_hash`。
- **前瞻 E-Value 監控圖**：以對數座標繪製 Test-Martingale 資本曲線 $K(t)$，對照 **20x 模擬盤 (Paper)**（$\alpha = 0.05$）與 **100x 實盤候選 (Live)**（$\alpha = 0.01$）門檻線。
- **治理事件帳本（Governance Ledger）**：唯讀紀錄每次封印、天梯晉升、風控熔斷與 24/7 背景排程事件。

---

### 2. 不可變研究活動與四臂證偽矩陣（Campaigns）

![不可變研究活動與四臂證偽矩陣](docs/screenshots/02-campaigns-4arm.png)

1. 點擊右上角 **建立研究活動（New Campaign）**，選擇資料來源（`Demo`、`Yahoo Finance` 美股/ETF、`Binance Public Spot` 加密貨幣、或本地 `CSV/Parquet`）、市場成本預設，並可勾選是否注入已串接的外部 MCP 唯讀探索上下文。
2. 建立瞬間鎖死三道 SHA-256 雜湊（`Config Hash`、`Frozen Data SHA-256`、`Engine Code Hash`）與時間分區（`Discovery 60%` / `Validation 20%` / `Sealed Holdout 20%`）。
3. 每個候選策略在完全相同的可觀測母體上同步跑 **四臂對照（4-Arm Falsification Matrix）**：
   - `full`：完整機制（`context AND setup AND trigger`）
   - `baseline`：僅背景脈絡（`context`）
   - `ablation`：移除 `setup`（或 `context`），驗證每個元件是否真的帶來增量優勢
   - `reverse_control`：保留相同的 `context` 與 `setup`，僅反轉 `trigger` 方向
   - 如圖所示，即使完整臂在開發期累積報酬達 `+17.69%`，只要移除 `setup` 的消融組表現更好，系統依然誠實淘汰（`Failed ablation test`）。
4. 點擊 **檢視 JSON AST** 可檢視完整宣告式語法樹（絕不執行任意 Python 字串）。
5. 檢視完開發期報告後，可對待驗證活動點擊 **解鎖單次凍結驗證** 執行唯一一次歷史驗證；一旦解鎖即永久封印，任何參照已揭曉父代的新版本皆會自動降級標記為 `contaminated_development_from_prior_revision`。

---

### 3. 純前瞻影子天梯與 Anytime-Valid E-Value（Shadow Ladder）

![純前瞻影子天梯](docs/screenshots/03-shadow-ladder.png)

- **歷史回測永遠不具備晉升資格。** 點擊 **加入影子天梯（Track in Shadow）**（或透過 API／MCP 註冊）後，策略從 `shadow` 開始累積真實前瞻樣本外觀察。
- **隨時監看、不膨脹型一錯誤**：依據 Ville 不等式 $P(\sup_t K_t \ge 1/\alpha \mid H_0) \le \alpha$，每天看盤都不會像傳統 p-value 因反覆窺探而失真：
  - `shadow -> paper`：至少 30 筆前瞻觀察、峰值 E-value $\ge 20\text{x}$、累積超額為正且 `MDD <= 15%`。
  - `paper -> live_candidate`：至少 60 筆前瞻觀察且峰值 E-value $\ge 100\text{x}$（正式實盤永遠保留人工核准關卡）。
  - **自動風控熔斷**：前瞻 `MDD >= 20%`、連損 5 筆、或落後基準達 `-10%` 時自動降級或退役（如左側 `High-Volume Oversold Rebound`）。
- 底部表單（或呼叫 `POST /api/shadow/{strategy_key}/observations`／MCP 工具）可逐日登錄新觀察並即時重算 E-Value 曲線。

---

### 4. 獨立統計閘門審計器（Gate Auditor）

![獨立統計閘門審計器](docs/screenshots/04-gate-auditor.png)

如果你平常使用 **TradingView、Freqtrade、Backtrader 或 VectorBT**，可直接貼上交易明細 CSV（`entry_date, symbol, sector, gross, net`），按下 **執行嚴格審計** 立即產出獨立審計報告：
- **日期分群 Bootstrap 95% CI**（以交易日為群體抽樣；少於 5 個獨立交易日一律 fail-closed 拒絕）
- **1.5x / 2.0x 成本壓力測試**
- **單一標的與單一產業獲利集中度上限審查**
- **Test-Martingale E-Value 累積軌跡**

---

### 5. 雙向 MCP 擴充中心（串接外部 MCP ＋ 對外開放 QuantSeal MCP Server）

![MCP 擴充中心與雙向橋接（繁體中文）](docs/screenshots/08-mcp-hub-zh-tw.png)

QuantSeal 原生支援雙向 **Model Context Protocol (JSON-RPC 2.0)**：

- **對外串接第三方 MCP（Outbound MCP Client）**：在 **MCP 擴充中心** 直接註冊任意 **Streamable HTTP / SSE** 外部 MCP 伺服器（總經指標、鏈上數據、SEC 財報、波動率結構、新聞工具），一鍵 **探索工具列表** 並在 **即時工具呼叫測試台** 實測回傳結果。勾選 **納入探索期上下文** 後，發起研究活動時會將唯讀證據注入探索期卡片（嚴格限定開發期、附帶 `pit_warning` 並自動對密鑰脫敏，絕不污染驗證期）。基於 VPS 安全，本機 `stdio` 子行程預設 fail-closed 停用（`QUANTSEAL_ALLOW_STDIO_MCP=false`）。
- **對外開放 QuantSeal 成為 MCP Server（Inbound MCP Server）**：透過 Streamable HTTP（`POST /api/mcp`）或本機 stdio（`python -m quantseal mcp`），讓 **Claude Desktop、Cursor、Claude Code、Codex 或 OpenClaw** 直接呼叫 6 個內建研究治理工具：
  - `quantseal_audit_trades` — 對外部交易明細執行嚴格統計閘門審計
  - `quantseal_compute_evalue` — 計算 Anytime-Valid Test-Martingale E-Value
  - `quantseal_list_campaigns` / `quantseal_get_campaign` — 查詢不可變研究活動與四臂證偽矩陣
  - `quantseal_list_shadow_ladder` / `quantseal_record_shadow_observation` — 查詢前瞻影子天梯或寫入前瞻樣本外觀察值

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

### 6. BYOK LLM、24/7 排程與通知設定（Settings）

![設定與 24/7 自動化](docs/screenshots/05-settings-automation.png)

- **BYOK LLM 提案引擎**：支援 OpenAI、Anthropic Claude、Google Gemini，以及任何 OpenAI-Compatible 端點（OpenRouter、自架 Ollama、vLLM）。金鑰於日誌自動脫敏、API 回傳自動遮罩。
- **24/7 背景排程（UTC）**：設定每日影子對帳 Cron（預設 `0 22 * * 1-5`）與選配每週自動探索排程。
- **通知渠道**：支援 Telegram Bot、Discord Webhook 與通用 Webhook，可按 **發送測試通知** 即時驗證。

---

## 七大防過擬合不變量

1. **零 `exec()` 有界 JSON AST**：拒絕 `src` / `exec` / `eval` / `__dunder__`，強制 `lag >= 0`、`lag + window <= 60`、靜態矛盾檢查與 `NaN` 比較恆為 `False`。
2. **三雜湊加密封印**：鎖定 `config_hash`、`data_hash`、`code_hash`，竄改後續跑直接拋出 `CampaignImmutableMismatchError`。
3. **單次凍結驗證**：每個 Campaign 最多解鎖驗證期一次，重跑直接回傳已封存結果。
4. **前代污染追蹤**：子代若與已揭曉驗證期的父代日期重疊，自動標為 `contaminated_development_from_prior_revision`。
5. **四臂配對證偽**：`full` 必須同時擊敗 `baseline`、`ablation`、`reverse_control`，稀疏對照臂強制判 `inconclusive`。
6. **嚴格因果執行與真實成本**：次日開盤進場、跳空優先檢查、移動停損高點嚴格於當根檢查結束後更新、跨邊界訊號進場前預先排除、缺資料鎖倉不回溯平倉，並套用分層滑價與 1.5x / 2.0x 成本壓測。
7. **Anytime-Valid E-Value 天梯**：以有界對沖資本過程檢驗前瞻超額，附帶左偏重尾零假設蒙地卡羅防線與自動熔斷機制。

---

## 快速啟動

```bash
git clone https://github.com/berichlab/quantseal.git
cd quantseal
cp .env.example .env
# 編輯 .env 設定 QUANTSEAL_ADMIN_PASSWORD

docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

啟動後開啟 `http://localhost:8000`（Swagger API 文件位於 `http://localhost:8000/docs`，MCP Streamable HTTP 端點位於 `http://localhost:8000/api/mcp`）。本機亦可使用 `python -m quantseal mcp` 以 stdio 模式掛載給 Claude Desktop 或 Cursor。

---

## 關於 berichlab

**QuantSeal** 由 **[berichlab](https://berich.cc)** 開源打造並長期維護，致力於將機構級的防過擬合檢驗、嚴謹因果回測與前瞻風控天梯普及給每一位獨立量化研究者。

- 官方網站：[berich.cc](https://berich.cc) · [QuantSeal 專頁](https://berich.cc/quantseal)
- GitHub 組織：[github.com/berichlab](https://github.com/berichlab)
- Threads：[@berichlab](https://www.threads.com/@berichlab)
- Instagram：[@berichlab](https://www.instagram.com/berichlab/)

---

## 免責聲明與授權

QuantSeal 為量化研究治理與統計證偽工具，**不執行任何實盤券商下單、不構成投資建議，亦不保證任何獲利**。

本專案採用 [Apache License 2.0](./LICENSE) 授權。
