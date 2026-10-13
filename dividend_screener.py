#!/usr/bin/env python3
"""
A-share high-dividend stock screener.

Runs entirely offline on a CSV you export from your broker or data terminal
(e.g. akshare/tushare/东方财富/同花顺 exports). No network access and no
third-party dependencies required — standard library only.

It can:
  - filter by recent price fluctuation (N-day % change range)
  - sort by dividend payout (yield or dividend-per-share)
  - exclude ST / *ST stocks
  - exclude stocks below a minimum market cap
  - exclude stocks flagged with a risk warning

This is a research/screening utility. It does NOT constitute investment advice.
Dividend yields can be "traps" (high because the price fell); always verify
payout sustainability, cash flow and debt before acting on any result.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, field


# --- Column name resolution -------------------------------------------------
# Different data sources use different headers (Chinese or English). We map a
# set of logical fields to a list of candidate header names, case-insensitive.

COLUMN_ALIASES: dict[str, list[str]] = {
    "code": ["code", "ts_code", "symbol", "代码", "股票代码", "证券代码"],
    "name": ["name", "sec_name", "名称", "股票名称", "证券简称", "简称"],
    "yield": [
        "dividend_yield", "div_yield", "yield", "股息率", "股息率(%)",
        "股息收益率", "股利收益率",
    ],
    "dps": [
        "dps", "dividend_per_share", "每股股利", "每股分红", "每股派息",
        "分红", "每股现金分红",
    ],
    "market_cap": [
        "market_cap", "mkt_cap", "total_mv", "总市值", "市值", "总市值(亿)",
        "流通市值",
    ],
    "pct_change": [
        "pct_change", "pct_chg", "change_pct", "涨跌幅", "涨跌幅(%)",
        "区间涨跌幅", "近期涨跌幅", "n日涨跌幅", "阶段涨跌幅",
    ],
    "risk_flag": [
        "risk_flag", "risk", "risk_warning", "风险", "风险警示",
        "风险提示", "重大风险", "is_risk",
    ],
}


def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("　", "")


def resolve_columns(headers: list[str]) -> dict[str, str | None]:
    """Map logical field -> actual header present in the file (or None)."""
    normalized = {_norm(h): h for h in headers}
    resolved: dict[str, str | None] = {}
    for logical, candidates in COLUMN_ALIASES.items():
        found = None
        for cand in candidates:
            if _norm(cand) in normalized:
                found = normalized[_norm(cand)]
                break
        resolved[logical] = found
    return resolved


# --- Parsing helpers --------------------------------------------------------

def parse_number(raw: str | None) -> float | None:
    """Parse a numeric cell, tolerating %, commas, 亿/万 suffixes, blanks."""
    if raw is None:
        return None
    s = raw.strip()
    if s == "" or s in {"-", "--", "N/A", "nan", "None"}:
        return None
    s = s.replace(",", "").replace("%", "").replace("，", "")
    mult = 1.0
    # Order matters: check compound suffixes (万亿) before single ones.
    if s.endswith("万亿"):
        mult, s = 1e12, s[:-2]
    elif s.endswith("亿"):
        mult, s = 1e8, s[:-1]
    elif s.endswith("万"):
        mult, s = 1e4, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def is_truthy_flag(raw: str | None) -> bool:
    """Interpret a risk-flag cell as a boolean."""
    if raw is None:
        return False
    s = raw.strip().lower()
    return s in {"1", "true", "yes", "y", "是", "有", "风险", "警示", "t"}


# --- Core screening ---------------------------------------------------------

@dataclass
class Filters:
    min_pct_change: float | None = None
    max_pct_change: float | None = None
    min_market_cap: float | None = None
    exclude_st: bool = True
    exclude_risk: bool = True
    sort_by: str = "yield"  # "yield" or "dps"
    top: int | None = None


@dataclass
class ScreenResult:
    rows: list[dict] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)
    total_in: int = 0


ST_MARKERS = ("st", "*st", "ｓｔ", "s*st", "退")


def looks_like_st(name: str) -> bool:
    n = name.replace(" ", "").lower()
    return any(m in n for m in ST_MARKERS)


def screen(records: list[dict], cols: dict[str, str | None],
           f: Filters) -> ScreenResult:
    result = ScreenResult(total_in=len(records))
    excluded = {
        "st": 0, "risk": 0, "low_market_cap": 0,
        "price_out_of_range": 0, "missing_sort_key": 0,
    }

    def get(rec, logical):
        col = cols.get(logical)
        return rec.get(col) if col else None

    kept = []
    for rec in records:
        name = (get(rec, "name") or "").strip()

        if f.exclude_st and name and looks_like_st(name):
            excluded["st"] += 1
            continue

        if f.exclude_risk and is_truthy_flag(get(rec, "risk_flag")):
            excluded["risk"] += 1
            continue

        mcap = parse_number(get(rec, "market_cap"))
        if f.min_market_cap is not None:
            if mcap is None or mcap < f.min_market_cap:
                excluded["low_market_cap"] += 1
                continue

        pct = parse_number(get(rec, "pct_change"))
        if f.min_pct_change is not None or f.max_pct_change is not None:
            if pct is None:
                excluded["price_out_of_range"] += 1
                continue
            if f.min_pct_change is not None and pct < f.min_pct_change:
                excluded["price_out_of_range"] += 1
                continue
            if f.max_pct_change is not None and pct > f.max_pct_change:
                excluded["price_out_of_range"] += 1
                continue

        sort_val = parse_number(get(rec, f.sort_by))
        if sort_val is None:
            excluded["missing_sort_key"] += 1
            continue

        kept.append({
            "code": (get(rec, "code") or "").strip(),
            "name": name,
            "yield": parse_number(get(rec, "yield")),
            "dps": parse_number(get(rec, "dps")),
            "market_cap": mcap,
            "pct_change": pct,
            "_sort": sort_val,
        })

    kept.sort(key=lambda r: r["_sort"], reverse=True)
    if f.top is not None:
        kept = kept[: f.top]

    result.rows = kept
    result.excluded = excluded
    return result


# --- I/O --------------------------------------------------------------------

def read_csv(path: str) -> tuple[list[dict], list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        rows = list(reader)
    return rows, list(headers)


def fmt(v, pct=False):
    if v is None:
        return "-"
    if pct:
        return f"{v:.2f}%"
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}亿"
    return f"{v:,.2f}"


def print_report(res: ScreenResult, f: Filters) -> None:
    print(f"\nScanned {res.total_in} rows; {len(res.rows)} passed filters.\n")
    print("Excluded:")
    labels = {
        "st": "ST / *ST", "risk": "risk-flagged",
        "low_market_cap": "below min market cap",
        "price_out_of_range": "price change out of range",
        "missing_sort_key": f"missing {f.sort_by}",
    }
    for k, label in labels.items():
        if res.excluded.get(k):
            print(f"  - {label}: {res.excluded[k]}")

    if not res.rows:
        print("\nNo stocks matched. Loosen filters or check column names.")
        return

    print(f"\nTop results (sorted by {f.sort_by}, desc):\n")
    header = f"{'Code':<12}{'Name':<14}{'Yield':>9}{'DPS':>9}{'MktCap':>12}{'ΔPrice':>9}"
    print(header)
    print("-" * len(header))
    for r in res.rows:
        print(
            f"{r['code']:<12}{r['name']:<14}"
            f"{fmt(r['yield'], pct=True):>9}"
            f"{fmt(r['dps']):>9}"
            f"{fmt(r['market_cap']):>12}"
            f"{fmt(r['pct_change'], pct=True):>9}"
        )
    print("\nResearch tool only — not investment advice. Verify payout "
          "sustainability (payout ratio, free cash flow, debt) yourself.")


def write_csv(res: ScreenResult, path: str) -> None:
    fields = ["code", "name", "yield", "dps", "market_cap", "pct_change"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in res.rows:
            w.writerow({k: r.get(k) for k in fields})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Offline A-share high-dividend screener (no network, no deps).",
    )
    p.add_argument("input", help="Path to input CSV")
    p.add_argument("--min-change", type=float, default=None,
                   help="Min recent price change %% (e.g. -10)")
    p.add_argument("--max-change", type=float, default=None,
                   help="Max recent price change %% (e.g. 5)")
    p.add_argument("--min-market-cap", type=float, default=None,
                   help="Min market cap in RAW units of your data "
                        "(e.g. 5e9 for 50亿 if data is in 元)")
    p.add_argument("--sort-by", choices=["yield", "dps"], default="yield",
                   help="Sort key: dividend yield (default) or dividend/share")
    p.add_argument("--top", type=int, default=20, help="Show top N (default 20)")
    p.add_argument("--keep-st", action="store_true",
                   help="Do NOT exclude ST/*ST stocks")
    p.add_argument("--keep-risk", action="store_true",
                   help="Do NOT exclude risk-flagged stocks")
    p.add_argument("--out", default=None, help="Optional path to write results CSV")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        records, headers = read_csv(args.input)
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"Error reading CSV: {e}", file=sys.stderr)
        return 1

    cols = resolve_columns(headers)
    missing_required = [k for k in ("name",) if cols.get(k) is None]
    if missing_required:
        print(f"Error: could not find a 'name' column in {headers}",
              file=sys.stderr)
        return 1
    if cols.get(args.sort_by) is None:
        print(f"Error: sort key '{args.sort_by}' column not found. "
              f"Available columns: {headers}", file=sys.stderr)
        return 1

    print("Resolved columns:")
    for logical, actual in cols.items():
        print(f"  {logical:<12} -> {actual or '(not found)'}")

    f = Filters(
        min_pct_change=args.min_change,
        max_pct_change=args.max_change,
        min_market_cap=args.min_market_cap,
        exclude_st=not args.keep_st,
        exclude_risk=not args.keep_risk,
        sort_by=args.sort_by,
        top=args.top,
    )
    res = screen(records, cols, f)
    print_report(res, f)

    if args.out:
        write_csv(res, args.out)
        print(f"\nWrote {len(res.rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
