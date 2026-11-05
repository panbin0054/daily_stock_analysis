#!/usr/bin/env python3
"""Apply a verified repair from a database copy, checking for concurrent changes."""

import argparse
import json
import sqlite3
from pathlib import Path


def apply_repair(database: Path, baseline: Path, repaired: Path) -> tuple[int, int, int]:
    paths = [path.resolve() for path in (database, baseline, repaired)]
    if len(set(paths)) != 3 or any(not path.is_file() for path in paths):
        raise ValueError("Provide three distinct existing databases")
    with sqlite3.connect(database, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("ATTACH DATABASE ? AS baseline", (str(baseline),))
        connection.execute("ATTACH DATABASE ? AS repaired", (str(repaired),))
        connection.execute("BEGIN IMMEDIATE")
        for table in ("portfolio_accounts", "portfolio_trades", "portfolio_cash_ledger",
                      "portfolio_corporate_actions", "portfolio_fx_rates", "stock_daily"):
            for left, right in (("main", "baseline"), ("baseline", "main")):
                query = f"SELECT EXISTS(SELECT * FROM {left}.{table} EXCEPT SELECT * FROM {right}.{table})"
                if connection.execute(query).fetchone()[0]:
                    raise RuntimeError(f"{table} changed since the backup; rebuild and verify the repair")

        snapshot_ids = [row[0] for row in connection.execute(
            "SELECT snapshot_id FROM repaired.portfolio_repair_manifest"
        )]
        for snapshot_id in snapshot_ids:
            old = connection.execute("SELECT * FROM baseline.portfolio_daily_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            current = connection.execute("SELECT * FROM main.portfolio_daily_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            new = connection.execute("SELECT * FROM repaired.portfolio_daily_snapshots WHERE id=?", (snapshot_id,)).fetchone()
            if old is None or current != old or new is None:
                raise RuntimeError(f"Snapshot {snapshot_id} changed or is missing; aborting")
            # Snapshot identity, cash and held quantities must remain unchanged.
            old_payload, new_payload = json.loads(old["payload"]), json.loads(new["payload"])
            positions = lambda payload: sorted((p.get("symbol"), p.get("market"), p.get("currency"), p.get("quantity")) for p in payload.get("positions", []))
            identity = ("account_id", "snapshot_date", "cost_method", "base_currency")
            if (tuple(old[key] for key in identity) != tuple(new[key] for key in identity)
                    or abs(float(old["total_cash"]) - float(new["total_cash"])) > 0.0001
                    or positions(old_payload) != positions(new_payload)):
                raise RuntimeError(f"Snapshot {snapshot_id} changed holdings or cash; aborting")

        before = connection.total_changes
        connection.execute("INSERT OR IGNORE INTO main.portfolio_fx_rates "
                           "(from_currency,to_currency,rate_date,rate,source,is_stale,updated_at) "
                           "SELECT from_currency,to_currency,rate_date,rate,source,is_stale,updated_at "
                           "FROM repaired.portfolio_fx_rates WHERE source='ecb_reference'")
        fx_count = connection.total_changes - before
        before = connection.total_changes
        connection.execute("INSERT OR IGNORE INTO main.stock_daily "
                           "(code,date,open,high,low,close,volume,amount,data_source,canonical_id,created_at,updated_at) "
                           "SELECT code,date,open,high,low,close,volume,amount,data_source,canonical_id,created_at,updated_at FROM repaired.stock_daily "
                           "WHERE data_source='akshare_sina_unadjusted'")
        price_count = connection.total_changes - before
        columns = ("total_cash", "total_market_value", "total_equity", "unrealized_pnl", "realized_pnl",
                   "fee_total", "tax_total", "fx_stale", "payload", "updated_at")
        assignments = ", ".join(f"{column}=(SELECT {column} FROM repaired.portfolio_daily_snapshots r WHERE r.id=portfolio_daily_snapshots.id)" for column in columns)
        before = connection.total_changes
        connection.execute(f"UPDATE main.portfolio_daily_snapshots SET {assignments} "
                           "WHERE id IN (SELECT snapshot_id FROM repaired.portfolio_repair_manifest)")
        snapshot_count = connection.total_changes - before
        return fx_count, price_count, snapshot_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--repaired", type=Path, required=True)
    args = parser.parse_args()
    fx, prices, snapshots = apply_repair(args.database, args.baseline, args.repaired)
    print(f"Imported FX rates: {fx}; historical closes: {prices}; repaired snapshots: {snapshots}")


if __name__ == "__main__":
    main()
