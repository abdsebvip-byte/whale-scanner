# whale-scanner2 — Charterji Clone — Design

**Date:** 2026-08-05
**Status:** Draft for approval (HARD-GATE: no implementation before design approval)
**Target repo:** `whale-scanner2` (new repo/project — sibling of `whale-scanner`, which stays untouched)
**Future:** merge into `whale-scannerpro` later

## 1. Objective

Build a fully working clone of the **Charterji** platform (by developer
**Abdulrahman Al-Ghabban**) — same identity, sections, technology, and
intelligence — serving the **Saudi (Tadawul)** and **US** markets.

Source of truth: the developer's YouTube channel
`https://www.youtube.com/@a.alghabban` (37 videos) + the 4 strategic videos
extracted this session (`1.16.0`, CSL, Market Radar `1.14.0`, Gate `1.7.0`)
+ the full `1.19.0` analysis.

### 1.1 Honesty rule (carries from the project)
Anything not documented in the source videos is stated as **undocumented /
assumed** — never invented as fact. Conflicting evidence is kept, not hidden.

---

## 2. Product Identity

- **Name:** whale-scanner2 (working title). Charterji's own identity: an
  Arabic-first market-data platform named after the founder.
- **Philosophy:** the platform is **UX-first**. The developer explicitly said
  versions `1.20+` focus on **user-experience polish over new functionality**.
  Charts, scanners, workspaces, keyboard-driven flows.
- **Keyboard model:** `Alt` is the **super-key** across the network —
  shortcuts are consistent and discoverable via the shortcuts menu (`Alt+F2`).

### 2.1 Core principles extracted from the videos
1. **Charts are interactive + synced, not static.** Up to 8 charts in a
   workspace, fully synchronized (symbol, drawings, crosshair, zoom/range,
   indicator settings, display settings, trades, timeframe navigation).
2. **Indicators are an engine, not a list.** Every indicator derives from
   **5 inputs**: high / low / close / open / volumes (+ the timeframe).
3. **Server-side heavy lifting.** Pattern detection, volumes, activity, and
   liquidity are computed **server-side with caching** (hourly refresh /
   auto-rebuild), not on the client.
4. **One data source.** Financial Modeling Prep (**FMP**) — confirmed 100%.
5. **Reality-first backtesting.** Fix TradingView's flaw (assumes the same
   capital per symbol, ignores open positions) — the roadmap target is
   market-wide backtests with real portfolio/capital allocation.

---

## 3. Sections (feature map)

### 3.1 Visual market summary (from 1.19.0)
- Market summary rendered visually: **gold = up**, **red = down**,
  **gray = flat**.
- Shows liquidity and number of trades.
- Period tabs: **1 month / 3 months / 6 months / 1 year**.

### 3.2 Financial analysis section (from 1.19.0)
- Saudi market: **268 companies**.
- Market-cap map.
- Comparison tooling: **P/E, P/B, ROE, dividend yield** side-by-side.
- Data table per company: **historical / expected / actual / surprise**.

### 3.3 Financial analysis center (from 1.19.0)
- **5 engines**: growth / profitability / dividends / financial strength /
  valuation.
- Charts from **2006** onward.
- **Fair-price** computation.
- Analyst opinions (consensus).
- Ownership breakdown: **BlackRock, UBS, JPMorgan, Vanguard, iShares**.

### 3.4 Charting workspace (from 1.16.0)
- Drawing tools are **static** (~50–60 known tools: Trend Line, Ray, Channel,
  Fibonacci, Gann Boxes, Cycle Times, Fractal Patterns, Candlestick…).
- **Clean-chart mode**: hide status line, trading buttons, candle box.
- Multi-chart splits up to **8** charts with per-chart width/height control.
- Full **synchronization** across splits (see §2.1).
- Automatic save + **session restore** (down to the last symbol & timeframe).
- Indicator added from the chart screen itself, applied to **all** splits.
- Company logos/names in lists instead of raw numbers.

### 3.5 Indicators engine (from CSL video)
- All of TradingView's common indicators (~100–110, many duplicates) converted
  into Charterji's own engine: **MACD, RSI, %R, EMA/SMA**, etc.
- Custom indicator authoring via **CSL** (see §4.1).

### 3.6 Market radar — مرصاد السوق (from 1.14.0)
Equates to TradingView's **Scanner** + ThinkorSwim/Interactive Brokers
scanner + ThinkorSwim **workspace**. **8 tools in one workspace:**

| # | Tool | Description |
|---|------|-------------|
| 1 | Stock table | No filtering; dynamic columns from indicators/logical results; custom coloring |
| 2 | Market scanner | Same data as the table + filtering + editable columns + numeric results |
| 3 | Numeric result | Count-of-stocks / counter / ratio with changeable colors |
| 4 | Market chart | Breadth: how many stocks rose vs fell |
| 5 | Stock chart | Live chart; focus follows the clicked symbol |
| 6 | Stock details | Market-hours snapshot (positive vs flat vs negative count) |
| 7 | Watchlist | From the charts |
| 8 | Notes | Free text per workspace |

- **Templates**: ready-made defaults + share a template + copy link +
  **JSON export/import** (community gallery planned later).
- Scanner filters are expressive: e.g. *"daily low > output of an indicator"
  + "close > open"* → 59 results; candle-pattern searches by conditions
  (doji, dragonfly, gravestone, morning star, engulfing: close=high and
  low=open).

### 3.7 Market detector — كاشف السوق (from 1.16.0)
- **Pattern detection runs server-side** with caching (hourly refresh /
  auto-rebuild). Same for volumes, activity, liquidity.
- Candle buttons merged into the options menu.

### 3.8 Stock lists (from 1.16.0)
- **Sharia-compliant lists:** الراجحي الشرعية (Al-Rajhi), البلاد الشرعية
  (Al-Bilad), د. محمد العصيمي الشرعية (Dr. Mohammed Al-Osaimi).
- Top movers: **highest volume / highest rise / highest fall**.
- Gaps: **price gaps (up) / gap downs** (e.g. Saudi Electric Industries +13% on a gap-up).

### 3.9 Portfolio network — شبكة المحافظ (from network video + 1.7.0)
- **Portfolio feed** pulls public portfolios and renders them on the UI with
  "load more".
- Portfolio page: daily chart + stats + **discipline indicator** + recent
  events + CRUD + open/closed trades + history.
- Public portfolios only. Follow/unfollow + **events** (like / dislike /
  no-action; tapping like again removes it).
- Homepage may become the portfolios network; trading journal becomes a
  secondary page.
- Backend already built in the source videos: Node.js
  (`Subscription.find where user=X and portfolio=Y and active=true`), no
  permission exception on failure.

### 3.10 Export (from 1.19.0)
- **Excel / CSV** export — summary and detailed — with **absolute / relative**
  change options.

### 3.11 Roadmap features (declared by the developer, not yet shipped)
- Tie financial statements to **CSL**.
- **All global markets** data (beyond Saudi + US).
- **Strategy building in code** (CSL already has the runtime functions +
  indicators + drawings to support it).
- **Market-wide realistic backtests** with true capital allocation across the
  whole market (fixing the TV/ThinkorSwim single-symbol-capital flaw).

---

## 4. Technology & Architecture

### 4.1 CSL — Charterji Scripting Language (from CSL video)
- **Not** a full programming language — a **scripting language**.
- Pipeline: user script → **Parser** (instruction tree) → **Runtime**
  (loads functions/sources: close, RSI, volumes, …) → **Plots/points** →
  **Canvas** (rendering).
- Simple editor (Markdown with a custom theme).
- **Solves TradingView's indicator-to-indicator gap:** instead of copying an
  entire indicator's code inside another, CSL references an indicator from the
  library ("take the value from Charterji") — including other users' libraries.
- **Solves ThinkorSwim's documentation gap:** search is built into the editor
  (functions, pre-defined ones, drawings: candles / gaps / boxes / price
  labels above-below / horizontal line / fill between two series / offset /
  Fibonacci level / colors / up-down colors / thickness).
- Sample model indicator built on **ATR**: ATR(22) × 2, from 1 to 5000 points,
  colorable.

### 4.2 Backend / stack
- **Confirmed by video hashtags:** NextJS · TypeScript · MongoDB · RabbitMQ,
  plus Node.js backend code (confirmed in the 1.7.0 video).
- **Contradiction to record:** the legacy `app.js` from the old bitwarden
  CharterHTML snapshot documents **PostgreSQL / Redis**. This conflict is kept
  visible; the modern hashtags are treated as the current stack.

### 4.3 Data sources
- **FMP (Financial Modeling Prep)** — confirmed as the single data source.
- Markets: **Saudi (Tadawul, 268 companies)** + **US** first, all global
  markets later (roadmap).

### 4.4 Competitive reference points
- TradingView (~92 markets) — the chart/indicator benchmark.
- StrategyDesk, ThinkorSwim, Interactive Brokers — scanner/workspace
  references. The radar explicitly addresses ThinkorSwim's annoyances and
  TradingView's missing features.

---

## 5. Data Flow (high level)

```
User input (chart/scanner/CSL)
        │
        ▼
┌─────────────────────┐   cached, refreshed hourly / auto-rebuild
│ Server-side engines │──► patterns, volumes, activity, liquidity
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ CSL Runtime + Plots │──► indicators, strategies, backtests
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Canvas renderer     │──► synced multi-chart workspace
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Portfolio network   │──► feed, follow, events, exports
└─────────────────────┘
```

---

## 6. Scope decisions for whale-scanner2 (first build)

Proposed MVP slice (to be confirmed at design approval):

1. **Data:** FMP for US + Saudi.
2. **Charts:** OHLCV chart with the common indicators (MACD/RSI/%R/EMA/SMA),
   drawing tools, and single-workspace persistence.
3. **Market radar:** stock table + scanner + breadth chart + watchlist
   (tools 1, 2, 4, 7 of §3.6) with JSON template export/import.
4. **Stock lists:** movers + gaps (Sharia lists depend on an external data
   source — flagged as a dependency).
5. **Portfolio network:** public feed + follow + like (server-side events).
6. **Export:** CSV/Excel summary + detailed.

Explicitly deferred (roadmap): CSL full runtime, strategy backtester with
capital allocation, financial-analysis center, global markets.

---

## 7. Decisions to confirm (open questions at approval)

1. New repo `whale-scanner2` (NextJS+TS) — **separate directory** alongside
   `whale-scanner`, no shared code this phase. ✅/❌
2. Data: FMP via REST — confirm API key provisioning + Saudi coverage in the
   chosen FMP plan. (FMP's Saudi coverage is assumed from the videos.)
3. Sharia lists (Al-Rajhi / Al-Bilad / Al-Osaimi) — external source? assumed
   to require a dedicated data feed.
4. Auth for the portfolio network — minimal local auth first, or none (public
   feed only) for the MVP?
5. UI language: Arabic-first (RTL) with English toggle.

---

## 8. Verification

- Each slice is verified against its source video section (map: feature →
  video ID + lines).
- Honesty rule: undocumented features are labeled `[assumed]` in the codebase
  README and in this spec.

---

## 9. Reference map (source videos)

| Feature | Source |
|---|---|
| 1.19.0 analysis (financial center, market summary, export, FMP, roadmap) | `vd3_clean.txt` (662 lines) |
| 1.16.0 (lists, shortcuts, workspaces, server-side cache, UX polish) | `vd4_clean.txt` (268 lines) |
| CSL language + indicators philosophy + strategy/backtest roadmap | `vd5_clean.txt` (567 lines) |
| Market radar 1.14.0 (8 tools, templates, candle searches) | `vd6_clean.txt` (279 lines) |
| Gate 1.7.0 (portfolio network, events, Node.js backend) | `vd7_clean.txt` (198 lines) |
| Portfolio network walkthrough | `vd2` / `nnZbElUU_1E` |
| Legacy `app.js` (PostgreSQL/Redis — conflicting evidence) | bitwarden CharterHTML snapshot |
