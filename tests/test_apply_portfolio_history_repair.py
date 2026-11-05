import json
import shutil
import sqlite3

import pytest

from scripts.apply_portfolio_history_repair import apply_repair


def make_database(path):
    with sqlite3.connect(path) as c:
        for table in ("portfolio_accounts", "portfolio_trades", "portfolio_cash_ledger", "portfolio_corporate_actions"):
            c.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")
        c.execute("INSERT INTO portfolio_accounts VALUES (1, 'account')")
        c.execute("CREATE TABLE portfolio_fx_rates (from_currency TEXT,to_currency TEXT,rate_date TEXT,rate REAL,source TEXT,is_stale INTEGER,updated_at TEXT, UNIQUE(from_currency,to_currency,rate_date))")
        c.execute("CREATE TABLE stock_daily (code TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,amount REAL,data_source TEXT,canonical_id TEXT,created_at TEXT,updated_at TEXT, UNIQUE(code,date))")
        c.execute("CREATE TABLE portfolio_daily_snapshots (id INTEGER PRIMARY KEY,account_id INTEGER,snapshot_date TEXT,cost_method TEXT,base_currency TEXT,total_cash REAL,total_market_value REAL,total_equity REAL,unrealized_pnl REAL,realized_pnl REAL,fee_total REAL,tax_total REAL,fx_stale INTEGER,payload TEXT,created_at TEXT,updated_at TEXT)")
        payload = json.dumps({"positions": [{"symbol": "00700", "market": "hk", "currency": "HKD", "quantity": 1}]})
        c.execute("INSERT INTO portfolio_daily_snapshots VALUES (1,1,'2026-05-15','fifo','HKD',10,0,10,0,0,0,0,0,?,'old','old')", (payload,))


def test_apply_is_atomic_and_rejects_concurrent_ledger_changes(tmp_path):
    baseline, target, repaired = (tmp_path / name for name in ("baseline.db", "target.db", "repaired.db"))
    make_database(baseline)
    shutil.copy(baseline, target)
    shutil.copy(baseline, repaired)
    with sqlite3.connect(repaired) as c:
        c.execute("CREATE TABLE portfolio_repair_manifest (snapshot_id INTEGER PRIMARY KEY)")
        c.execute("INSERT INTO portfolio_repair_manifest VALUES (1)")
        c.execute("UPDATE portfolio_daily_snapshots SET total_market_value=100,total_equity=110,updated_at='new' WHERE id=1")
        c.execute("INSERT INTO portfolio_fx_rates VALUES ('HKD','CNY','2026-05-15',0.9,'ecb_reference',0,'new')")
        c.execute("INSERT INTO stock_daily VALUES ('00700','2026-05-15',100,101,99,100,1000,100000,'akshare_sina_unadjusted','hk00700','new','new')")

    with sqlite3.connect(target) as c:
        c.execute("UPDATE portfolio_accounts SET value='changed' WHERE id=1")
    with pytest.raises(RuntimeError, match="portfolio_accounts changed"):
        apply_repair(target, baseline, repaired)
    with sqlite3.connect(target) as c:
        assert c.execute("SELECT count(*) FROM portfolio_fx_rates").fetchone()[0] == 0
        c.execute("UPDATE portfolio_accounts SET value='account' WHERE id=1")
    assert apply_repair(target, baseline, repaired) == (1, 1, 1)
    with sqlite3.connect(target) as c:
        assert c.execute("SELECT total_equity FROM portfolio_daily_snapshots WHERE id=1").fetchone()[0] == 110
