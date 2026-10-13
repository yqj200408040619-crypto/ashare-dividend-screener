# A-share High-Dividend Stock Screener

An **offline**, dependency-free Python tool to screen Chinese A-share stocks for
high dividends. It runs on a CSV you export yourself (broker, data terminal, or
an `akshare`/`tushare` export) — no network access and no third-party packages
needed, just Python 3.10+.

> ⚠️ **Not investment advice.** This is a research/screening utility. A high
> dividend yield can be a "trap" (the price fell, pushing the yield up). Always
> verify payout sustainability — payout ratio, free cash flow, debt — before
> acting on any result, and consult a licensed advisor for decisions about your
> own money.

## Why offline / CSV-based?

Live-data libraries like `akshare` and `tushare` need internet access to fetch
from their servers. This tool deliberately works on a CSV you provide, so it's
portable, reproducible, and runs anywhere. The usual workflow:

1. Export a stock list to CSV (from your broker, 东方财富/同花顺, or a short
   `akshare`/`tushare` script on a machine with internet).
2. Run this screener on that CSV.

## What it does

- **Filter by recent price fluctuation** — keep stocks whose N-day % change is
  within `[--min-change, --max-change]`.
- **Sort by dividend payout** — by dividend **yield** (default) or dividend
  **per share** (`--sort-by dps`).
- **Exclude ST / \*ST stocks** — by name (on by default; `--keep-st` to disable).
- **Exclude low market cap** — drop anything below `--min-market-cap`.
- **Exclude risk-flagged stocks** — drop rows whose risk column is truthy
  (on by default; `--keep-risk` to disable).

## Input format

A CSV with a header row. Column names can be Chinese or English — the tool
auto-detects common aliases. Recognized fields:

| Field          | Example headers                                  | Required?           |
|----------------|--------------------------------------------------|---------------------|
| code           | `代码`, `股票代码`, `code`, `ts_code`             | optional            |
| name           | `名称`, `股票名称`, `证券简称`, `name`            | **required**        |
| dividend yield | `股息率(%)`, `股息率`, `dividend_yield`, `yield`  | required to sort by yield |
| dividend/share | `每股股利`, `每股分红`, `dps`                      | required to sort by dps   |
| market cap     | `总市值`, `市值`, `market_cap`, `total_mv`        | needed for `--min-market-cap` |
| price change   | `涨跌幅(%)`, `区间涨跌幅`, `pct_change`            | needed for change filters |
| risk flag      | `风险警示`, `风险`, `risk_flag`                    | needed for risk exclusion |

Number cells tolerate `%`, thousands commas, and `万` / `亿` / `万亿` suffixes.
Risk flags treat `是 / 有 / 1 / true / yes` as flagged.

## Usage

```bash
# Top 10 by dividend yield, cap ≥ 50亿 (5e9 if data is in 元),
# recent change between -12% and +10%, excluding ST and risk-flagged (defaults)
python dividend_screener.py sample_ashares.csv \
    --min-change -12 --max-change 10 --min-market-cap 5e9 \
    --sort-by yield --top 10

# Sort by dividend per share and save results
python dividend_screener.py sample_ashares.csv --sort-by dps --out results.csv
```

### Options

| Option              | Description                                               |
|---------------------|-----------------------------------------------------------|
| `--min-change`      | Minimum recent price change % (e.g. `-10`)                |
| `--max-change`      | Maximum recent price change % (e.g. `5`)                  |
| `--min-market-cap`  | Minimum market cap in the **raw units of your data**      |
| `--sort-by`         | `yield` (default) or `dps`                                |
| `--top`             | Show top N (default 20)                                   |
| `--keep-st`         | Do **not** exclude ST/\*ST stocks                          |
| `--keep-risk`       | Do **not** exclude risk-flagged stocks                     |
| `--out`             | Write results to a CSV (UTF-8 BOM, opens cleanly in Excel)|

> **Market-cap units:** `--min-market-cap` is compared in the same units as your
> data. If 总市值 is in 元, `50亿` = `5e9`. If your export is already in 亿, pass
> `50`. The tool prints which columns it matched so you can sanity-check.

## Example

`sample_ashares.csv` is included for a quick demo. Running the first command
above scans 16 rows and returns 10, excluding 2 ST stocks, 1 risk-flagged stock,
1 below the cap threshold, and 2 outside the price range.
