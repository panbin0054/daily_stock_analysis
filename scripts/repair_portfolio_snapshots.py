#!/usr/bin/env python3
"""Repair unpriced historical snapshots in an explicitly supplied database copy."""

import argparse
import math
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import akshare as ak


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if not args.database.is_file() or args.start > args.end or args.end >= date.today():
        parser.error("provide an existing database copy and a historical date range")

    os.environ["DATABASE_PATH"] = str(args.database.resolve())
    from src.services.portfolio_risk_service import PortfolioRiskService
    from src.services.portfolio_service import PortfolioService

    with sqlite3.connect(args.database) as connection:
        codes = [row[0] for row in connection.execute(
            "SELECT DISTINCT symbol FROM portfolio_trades WHERE lower(market) = 'hk'"
        ) if len(row[0]) == 5 and row[0].isdigit()]
        etfs = [row[0] for row in connection.execute(
            "SELECT DISTINCT symbol FROM portfolio_trades WHERE lower(market) = 'cn'"
        ) if len(row[0]) == 6 and row[0].isdigit() and row[0].startswith(("51", "52", "56", "58", "15", "16", "18"))]
        connection.execute("CREATE TABLE IF NOT EXISTS portfolio_repair_manifest (snapshot_id INTEGER PRIMARY KEY)")
        connection.execute("DELETE FROM portfolio_repair_manifest")
        added = 0
        for code in codes:
            frame = ak.stock_hk_daily(symbol=code, adjust="")
            rows = []
            for item in frame.itertuples(index=False):
                day = item.date if isinstance(item.date, date) else date.fromisoformat(str(item.date)[:10])
                prices = tuple(float(getattr(item, name)) for name in ("open", "high", "low", "close"))
                volume, amount = float(item.volume), float(item.amount)
                if (args.start - timedelta(days=14) <= day <= args.end
                        and all(math.isfinite(value) and value > 0 for value in prices)
                        and math.isfinite(volume) and volume >= 0 and math.isfinite(amount) and amount >= 0):
                    rows.append((code, day.isoformat(), *prices, volume, amount, f"hk{code}"))
            if not rows:
                raise ValueError(f"No valid unadjusted HK closes for {code}")
            before = connection.total_changes
            connection.executemany(
                "INSERT OR IGNORE INTO stock_daily (code,date,open,high,low,close,volume,amount,data_source,canonical_id,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,'akshare_sina_unadjusted',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", rows,
            )
            added += connection.total_changes - before
        for code in etfs:
            prefix = "sh" if code.startswith(("51", "52", "56", "58")) else "sz"
            symbol = f"{prefix}{code}"
            frame = ak.fund_etf_hist_sina(symbol=symbol)
            rows = []
            for item in frame.itertuples(index=False):
                day = item.date if isinstance(item.date, date) else date.fromisoformat(str(item.date)[:10])
                prices = tuple(float(getattr(item, name)) for name in ("open", "high", "low", "close"))
                volume, amount = float(item.volume), float(item.amount)
                if (args.start - timedelta(days=14) <= day <= args.end
                        and all(math.isfinite(value) and value > 0 for value in prices)
                        and math.isfinite(volume) and volume >= 0 and math.isfinite(amount) and amount >= 0):
                    rows.append((code, day.isoformat(), *prices, volume, amount, symbol))
            if not rows:
                raise ValueError(f"No valid unadjusted ETF closes for {code}")
            before = connection.total_changes
            connection.executemany(
                "INSERT OR IGNORE INTO stock_daily (code,date,open,high,low,close,volume,amount,data_source,canonical_id,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,'akshare_sina_unadjusted',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", rows,
            )
            added += connection.total_changes - before

    service = PortfolioService()
    risk = PortfolioRiskService(portfolio_service=service)
    rows = []
    for method in ("fifo", "avg"):
        rows.extend(risk.repo.list_daily_snapshots_for_risk(
            as_of=args.end, cost_method=method, account_id=None,
            lookback_days=(args.end - args.start).days + 1,
        ))
    candidates = [(int(row.id), int(row.account_id), row.snapshot_date, row.cost_method)
                  for row in rows if args.start <= row.snapshot_date <= args.end
                  and risk._snapshot_has_unpriced_positions(row)]
    repaired = []
    for snapshot_id, account_id, day, method in candidates:
        service.get_portfolio_snapshot(account_id=account_id, as_of=day, cost_method=method, include_realtime=False)
        with sqlite3.connect(args.database) as connection:
            payload = connection.execute("SELECT payload FROM portfolio_daily_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if payload:
            from types import SimpleNamespace
            if not risk._snapshot_has_unpriced_positions(SimpleNamespace(snapshot_date=day, payload=payload[0])):
                repaired.append((snapshot_id,))
    with sqlite3.connect(args.database) as connection:
        connection.executemany("INSERT INTO portfolio_repair_manifest (snapshot_id) VALUES (?)", repaired)
    print(f"HK symbols: {len(codes)}; ETF symbols: {len(etfs)}; new closes: {added}; incomplete snapshots: {len(candidates)}; repaired: {len(repaired)}")


if __name__ == "__main__":
    main()
