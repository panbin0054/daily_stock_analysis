#!/usr/bin/env python3
"""Backfill HKD/CNY from ECB reference rates; dry-run unless --apply is set."""

import argparse
import csv
import io
import math
import sqlite3
from datetime import date
from pathlib import Path

import requests

ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.CNY+HKD.EUR.SP00.A"


def fetch_rates(start: date, end: date) -> list[tuple[str, float]]:
    response = requests.get(
        ECB_URL,
        params={"startPeriod": start.isoformat(), "endPeriod": end.isoformat(), "format": "csvdata"},
        timeout=30,
    )
    response.raise_for_status()
    values: dict[str, dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(response.text)):
        currency = row.get("CURRENCY")
        if currency not in {"CNY", "HKD"} or row.get("CURRENCY_DENOM") != "EUR":
            continue
        day = date.fromisoformat(row["TIME_PERIOD"])
        value = float(row["OBS_VALUE"])
        if start <= day <= end and math.isfinite(value) and value > 0:
            values.setdefault(day.isoformat(), {})[currency] = value
    result = sorted((day, pair["CNY"] / pair["HKD"]) for day, pair in values.items() if len(pair) == 2)
    if not result:
        raise ValueError("ECB response contained no complete HKD/CNY reference rates")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.start > args.end or args.end > date.today() or not args.database.is_file():
        parser.error("check date range and database path")
    rates = fetch_rates(args.start, args.end)
    with sqlite3.connect(args.database) as connection:
        existing = {row[0] for row in connection.execute(
            "SELECT rate_date FROM portfolio_fx_rates WHERE from_currency = ? AND to_currency = ?",
            ("HKD", "CNY"),
        )}
        missing = [(day, rate) for day, rate in rates if day not in existing]
        if args.apply:
            connection.executemany(
                "INSERT INTO portfolio_fx_rates (from_currency, to_currency, rate_date, rate, source, is_stale, updated_at) "
                "VALUES ('HKD', 'CNY', ?, ?, 'ecb_reference', 0, CURRENT_TIMESTAMP)",
                missing,
            )
    print(f"ECB dates: {len(rates)} ({rates[0][0]} to {rates[-1][0]}); "
          f"new rates: {len(missing)}; existing preserved: {len(rates) - len(missing)}; applied: {args.apply}")


if __name__ == "__main__":
    main()
