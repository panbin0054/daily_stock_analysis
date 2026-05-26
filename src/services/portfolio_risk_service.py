# -*- coding: utf-8 -*-
"""Portfolio risk service for concentration, drawdown and stop-loss proximity."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.config import Config, get_config
from src.repositories.portfolio_repo import PortfolioRepository
from src.services.portfolio_service import PortfolioService


class PortfolioRiskService:
    """Compute portfolio risk blocks on top of replayed snapshot data."""

    def __init__(
        self,
        *,
        repo: Optional[PortfolioRepository] = None,
        portfolio_service: Optional[PortfolioService] = None,
        config: Optional[Config] = None,
    ):
        self.repo = repo or PortfolioRepository()
        self.portfolio_service = portfolio_service or PortfolioService(repo=self.repo)
        self.config = config or get_config()
        self._data_manager = None
        self._data_manager_init_error = ""

    def get_risk_report(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        snapshot = self.portfolio_service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=cost_method,
        )

        thresholds = {
            "concentration_alert_pct": float(getattr(self.config, "portfolio_risk_concentration_alert_pct", 35.0)),
            "drawdown_alert_pct": float(getattr(self.config, "portfolio_risk_drawdown_alert_pct", 15.0)),
            "stop_loss_alert_pct": float(getattr(self.config, "portfolio_risk_stop_loss_alert_pct", 10.0)),
            "stop_loss_near_ratio": float(getattr(self.config, "portfolio_risk_stop_loss_near_ratio", 0.8)),
            "lookback_days": int(getattr(self.config, "portfolio_risk_lookback_days", 180)),
        }

        concentration = self._build_concentration(
            snapshot,
            thresholds["concentration_alert_pct"],
            as_of_date=as_of_date,
        )
        sector_concentration = self._build_sector_concentration(
            snapshot,
            thresholds["concentration_alert_pct"],
            as_of_date=as_of_date,
        )
        self._ensure_drawdown_snapshot_window(
            account_id=account_id,
            as_of_date=as_of_date,
            cost_method=cost_method,
            lookback_days=thresholds["lookback_days"],
        )
        drawdown = self._build_drawdown(
            account_id=account_id,
            as_of_date=as_of_date,
            cost_method=cost_method,
            threshold_pct=thresholds["drawdown_alert_pct"],
            lookback_days=thresholds["lookback_days"],
        )
        stop_loss = self._build_stop_loss(snapshot, thresholds)

        return {
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "cost_method": cost_method,
            "currency": snapshot["currency"],
            "thresholds": thresholds,
            "concentration": concentration,
            "sector_concentration": sector_concentration,
            "drawdown": drawdown,
            "stop_loss": stop_loss,
        }

    def _ensure_drawdown_snapshot_window(
        self,
        *,
        account_id: Optional[int],
        as_of_date: date,
        cost_method: str,
        lookback_days: int,
    ) -> None:
        if lookback_days <= 0:
            return

        start_date = self._resolve_backfill_start_date(
            account_id=account_id,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
        )
        if start_date > as_of_date:
            return

        existing_rows = self.repo.list_daily_snapshots_for_risk(
            as_of=as_of_date,
            cost_method=cost_method,
            account_id=account_id,
            lookback_days=lookback_days,
        )
        if account_id is not None:
            existing_dates = {row.snapshot_date for row in existing_rows if int(row.account_id) == int(account_id)}
            current_date = start_date
            while current_date <= as_of_date:
                if current_date not in existing_dates:
                    self.portfolio_service.get_portfolio_snapshot(
                        account_id=account_id,
                        as_of=current_date,
                        cost_method=cost_method,
                    )
                    existing_dates.add(current_date)
                current_date += timedelta(days=1)
            return

        account_ids = [int(account.id) for account in self.repo.list_accounts(include_inactive=False)]
        if not account_ids:
            return
        existing_pairs = {(int(row.account_id), row.snapshot_date) for row in existing_rows}
        current_date = start_date
        while current_date <= as_of_date:
            if not all((aid, current_date) in existing_pairs for aid in account_ids):
                self.portfolio_service.get_portfolio_snapshot(
                    account_id=None,
                    as_of=current_date,
                    cost_method=cost_method,
                )
                for aid in account_ids:
                    existing_pairs.add((aid, current_date))
            current_date += timedelta(days=1)

    def _resolve_backfill_start_date(
        self,
        *,
        account_id: Optional[int],
        as_of_date: date,
        lookback_days: int,
    ) -> date:
        window_start = as_of_date - timedelta(days=lookback_days)
        if account_id is not None:
            first_activity = self.repo.get_first_activity_date(account_id=account_id, as_of=as_of_date)
            return max(window_start, first_activity or as_of_date)

        first_activity_candidates: List[date] = []
        for account in self.repo.list_accounts(include_inactive=False):
            first_activity = self.repo.get_first_activity_date(account_id=int(account.id), as_of=as_of_date)
            if first_activity is not None:
                first_activity_candidates.append(first_activity)
        if not first_activity_candidates:
            return as_of_date
        return max(window_start, min(first_activity_candidates))

    def _build_concentration(self, snapshot: Dict[str, Any], threshold_pct: float, *, as_of_date: date) -> Dict[str, Any]:
        total_mv = float(snapshot.get("total_market_value", 0.0) or 0.0)
        exposure_by_symbol: Dict[str, float] = {}
        for account in snapshot.get("accounts", []):
            for pos in account.get("positions", []):
                symbol = str(pos.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                market_value = float(pos.get("market_value_base") or 0.0)
                valuation_currency = str(pos.get("valuation_currency") or account.get("base_currency") or "CNY")
                converted, _, _ = self.portfolio_service.convert_amount(
                    amount=market_value,
                    from_currency=valuation_currency,
                    to_currency="CNY",
                    as_of_date=as_of_date,
                )
                exposure_by_symbol[symbol] = exposure_by_symbol.get(symbol, 0.0) + converted

        rows = []
        for symbol, exposure in exposure_by_symbol.items():
            weight = (exposure / total_mv * 100.0) if total_mv > 0 else 0.0
            rows.append(
                {
                    "symbol": symbol,
                    "market_value_base": round(exposure, 6),
                    "weight_pct": round(weight, 4),
                    "is_alert": bool(weight >= threshold_pct),
                }
            )
        rows.sort(key=lambda item: item["market_value_base"], reverse=True)

        top_weight = rows[0]["weight_pct"] if rows else 0.0
        return {
            "total_market_value": round(total_mv, 6),
            "top_weight_pct": round(float(top_weight), 4),
            "alert": bool(top_weight >= threshold_pct),
            "top_positions": rows[:10],
        }

    def _build_sector_concentration(
        self,
        snapshot: Dict[str, Any],
        threshold_pct: float,
        *,
        as_of_date: date,
    ) -> Dict[str, Any]:
        total_mv = float(snapshot.get("total_market_value", 0.0) or 0.0)
        sector_exposure: Dict[str, float] = {}
        sector_symbols: Dict[str, set] = {}
        coverage = {
            "classified_count": 0,
            "unclassified_count": 0,
            "failed_count": 0,
        }
        errors: List[str] = []
        board_cache: Dict[Tuple[str, str], str] = {}

        for account in snapshot.get("accounts", []):
            for pos in account.get("positions", []):
                symbol = str(pos.get("symbol") or "").strip().upper()
                market = str(pos.get("market") or account.get("market") or "").strip().lower()
                if not symbol:
                    continue

                market_value = float(pos.get("market_value_base") or 0.0)
                valuation_currency = str(pos.get("valuation_currency") or account.get("base_currency") or "CNY")
                converted, _, _ = self.portfolio_service.convert_amount(
                    amount=market_value,
                    from_currency=valuation_currency,
                    to_currency="CNY",
                    as_of_date=as_of_date,
                )

                sector = self._resolve_primary_sector(
                    symbol=symbol,
                    market=market,
                    board_cache=board_cache,
                    coverage=coverage,
                    errors=errors,
                )
                sector_exposure[sector] = sector_exposure.get(sector, 0.0) + converted
                sector_symbols.setdefault(sector, set()).add(symbol)

        rows = []
        for sector, exposure in sector_exposure.items():
            weight = (exposure / total_mv * 100.0) if total_mv > 0 else 0.0
            rows.append(
                {
                    "sector": sector,
                    "market_value_base": round(exposure, 6),
                    "weight_pct": round(weight, 4),
                    "symbol_count": len(sector_symbols.get(sector, set())),
                    "is_alert": bool(weight >= threshold_pct),
                }
            )
        rows.sort(key=lambda item: item["market_value_base"], reverse=True)
        top_weight = rows[0]["weight_pct"] if rows else 0.0

        return {
            "total_market_value": round(total_mv, 6),
            "top_weight_pct": round(float(top_weight), 4),
            "alert": bool(top_weight >= threshold_pct),
            "top_sectors": rows[:10],
            "coverage": coverage,
            "errors": errors[:20],
        }

    def _resolve_primary_sector(
        self,
        *,
        symbol: str,
        market: str,
        board_cache: Dict[Tuple[str, str], str],
        coverage: Dict[str, int],
        errors: List[str],
    ) -> str:
        cache_key = (symbol, market)
        if cache_key in board_cache:
            return board_cache[cache_key]

        sector_name: Optional[str] = None
        try:
            if market == "cn":
                # 1. tushare stock_basic industry (best for A-shares)
                sector_name = self._fetch_industry_from_tushare(symbol)
                # 2. ETF: tushare fund_basic name → infer sector
                if not sector_name:
                    sector_name = self._fetch_etf_sector(symbol)
                # 3. efinance get_belong_board (fallback)
                if not sector_name:
                    boards = self._fetch_belong_boards(symbol)
                    sector_name = self._pick_primary_board_name(boards)
            elif market in ("hk", "hongkong", "hong_kong"):
                sector_name = self._fetch_hk_sector(symbol)
        except Exception as exc:
            coverage["failed_count"] += 1
            errors.append(f"{symbol}: {exc}")
            board_cache[cache_key] = "UNCLASSIFIED"
            return board_cache[cache_key]

        if sector_name:
            coverage["classified_count"] += 1
            board_cache[cache_key] = sector_name
        else:
            coverage["unclassified_count"] += 1
            board_cache[cache_key] = "UNCLASSIFIED"
        return board_cache[cache_key]

    # ---- Sector data fetchers ----

    _tushare_industry_cache: Optional[Dict[str, str]] = None

    def _fetch_industry_from_tushare(self, symbol: str) -> Optional[str]:
        """Get industry from tushare stock_basic (A-shares, batch-cached)."""
        if PortfolioRiskService._tushare_industry_cache is None:
            PortfolioRiskService._tushare_industry_cache = self._load_tushare_industry_map()
        return PortfolioRiskService._tushare_industry_cache.get(symbol)

    def _load_tushare_industry_map(self) -> Dict[str, str]:
        """Load full A-share industry mapping from tushare (one API call)."""
        try:
            import tushare as ts
            import os
            token = os.environ.get("TUSHARE_TOKEN", "")
            if not token:
                return {}
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,industry")
            if df is None or df.empty:
                return {}
            result: Dict[str, str] = {}
            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code", ""))
                industry = str(row.get("industry", "")).strip()
                if ts_code and industry:
                    code = ts_code.split(".")[0]
                    result[code] = industry
            return result
        except Exception:
            return {}

    _tushare_etf_cache: Optional[Dict[str, str]] = None

    # ETF name → sector keyword mapping
    _ETF_SECTOR_KEYWORDS = (
        ("光伏", "光伏"), ("新能源", "新能源"), ("半导体", "半导体"),
        ("芯片", "半导体"), ("医药", "医药"), ("医疗", "医疗"),
        ("消费", "消费"), ("白酒", "白酒"), ("食品", "食品饮料"),
        ("银行", "银行"), ("证券", "证券"), ("券商", "证券"),
        ("保险", "保险"), ("金融", "金融"), ("地产", "房地产"),
        ("军工", "军工"), ("科技", "科技"), ("信息", "信息技术"),
        ("通信", "通信"), ("电子", "电子"), ("计算机", "计算机"),
        ("互联网", "互联网"), ("传媒", "传媒"), ("汽车", "汽车"),
        ("锂电", "锂电池"), ("电池", "锂电池"), ("储能", "储能"),
        ("钢铁", "钢铁"), ("煤炭", "煤炭"), ("有色", "有色金属"),
        ("化工", "化工"), ("电力", "电力"), ("环保", "环保"),
        ("农业", "农业"), ("家电", "家电"), ("机械", "机械"),
        ("机器人", "机器人"), ("人工智能", "人工智能"),
        ("红利", "红利/价值"), ("央企", "央国企"), ("国企", "央国企"),
        ("沪深300", "大盘综合"), ("中证500", "中盘综合"),
        ("上证50", "大盘综合"), ("恒生", "港股综合"),
    )

    def _fetch_etf_sector(self, symbol: str) -> Optional[str]:
        """Infer ETF sector from fund name via tushare fund_basic."""
        if PortfolioRiskService._tushare_etf_cache is None:
            PortfolioRiskService._tushare_etf_cache = self._load_tushare_etf_map()
        return PortfolioRiskService._tushare_etf_cache.get(symbol)

    def _load_tushare_etf_map(self) -> Dict[str, str]:
        """Load ETF sector mapping from tushare fund_basic."""
        try:
            import tushare as ts
            import os
            token = os.environ.get("TUSHARE_TOKEN", "")
            if not token:
                return {}
            ts.set_token(token)
            pro = ts.pro_api()
            df = pro.fund_basic(market="E", status="L")
            if df is None or df.empty:
                return {}
            result: Dict[str, str] = {}
            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code", ""))
                name = str(row.get("name", "")).strip()
                if not ts_code or not name:
                    continue
                code = ts_code.split(".")[0]
                for keyword, sector in self._ETF_SECTOR_KEYWORDS:
                    if keyword in name:
                        result[code] = sector
                        break
            return result
        except Exception:
            return {}

    # Well-known HK stock → sector mapping
    _HK_SECTOR_MAP: Dict[str, str] = {
        "00700": "互联网", "09988": "互联网", "09618": "互联网",
        "03690": "互联网", "01024": "互联网", "09888": "互联网",
        "00388": "金融", "01299": "保险", "02318": "保险",
        "02628": "保险", "00005": "银行", "03988": "银行",
        "01398": "银行", "00939": "银行", "03968": "银行",
        "00941": "通信", "00728": "通信", "06060": "通信",
        "02382": "电子", "01810": "电子", "09999": "医疗",
        "02269": "医疗", "06098": "汽车", "01211": "汽车",
        "02015": "汽车", "09868": "汽车", "00175": "汽车",
        "02333": "消费", "02020": "教育", "06862": "医疗",
        "01177": "医疗", "06618": "金融", "06082": "半导体",
        "00241": "科技", "09961": "物流", "02688": "消费",
        "01919": "航运", "00883": "石油化工", "00857": "石油化工",
        "02899": "新能源", "01347": "软件", "00981": "半导体",
        "00020": "地产", "01109": "地产", "02007": "地产",
        "09626": "电商", "01833": "消费", "06969": "消费",
    }

    def _fetch_hk_sector(self, symbol: str) -> Optional[str]:
        """Get HK stock sector from static mapping."""
        padded = symbol.zfill(5)
        return self._HK_SECTOR_MAP.get(padded)

    def _fetch_us_sector(self, symbol: str) -> Optional[str]:
        """Placeholder for US stock sector lookup."""
        return None

    def _fetch_belong_boards(self, symbol: str) -> List[Dict[str, Any]]:
        manager = self._get_data_manager()
        if manager is None:
            return []
        result = manager.get_belong_boards(symbol)
        if isinstance(result, list):
            return result
        return []

    # Keywords that indicate a board is NOT an industry sector
    _NON_INDUSTRY_KEYWORDS = (
        "概念", "板块", "沪股通", "深股通", "融资融券", "证金持股",
        "机构重仓", "百元股", "破净股", "大盘股", "小盘股", "中盘股",
        "周期股", "成长股", "价值股", "HS300", "上证", "深证",
        "MSCI", "标准普尔", "富时罗素", "GDR", "AH股",
        "做市商", "参股", "持股", "重仓",
    )

    @staticmethod
    def _pick_primary_board_name(boards: List[Dict[str, Any]]) -> Optional[str]:
        if not boards:
            return None

        # If any board has explicit type "行业" or "industry", use it directly
        for item in boards:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            type_text = str(item.get("type") or "").strip().lower()
            if "行业" in type_text or "industry" in type_text:
                return name

        # Otherwise, find the first board that looks like an industry sector
        # (i.e., exclude concept/region/index boards by keywords)
        fallback: Optional[str] = None
        for item in boards:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            if fallback is None:
                fallback = name
            # Skip boards whose names contain non-industry keywords
            if any(kw in name for kw in PortfolioRiskService._NON_INDUSTRY_KEYWORDS):
                continue
            # Skip region boards (ending with 板块 is already caught above)
            # The remaining board is likely an industry sector
            return name

        return fallback

    def _get_data_manager(self):
        if self._data_manager is not None:
            return self._data_manager
        if self._data_manager_init_error:
            return None
        try:
            from data_provider import DataFetcherManager

            self._data_manager = DataFetcherManager()
            return self._data_manager
        except Exception as exc:  # pragma: no cover - fail-open initialization
            self._data_manager_init_error = str(exc)
            return None

    def _build_drawdown(
        self,
        *,
        account_id: Optional[int],
        as_of_date: date,
        cost_method: str,
        threshold_pct: float,
        lookback_days: int,
    ) -> Dict[str, Any]:
        rows = self.repo.list_daily_snapshots_for_risk(
            as_of=as_of_date,
            cost_method=cost_method,
            account_id=account_id,
            lookback_days=lookback_days,
        )
        if not rows:
            return {
                "series_points": 0,
                "max_drawdown_pct": 0.0,
                "current_drawdown_pct": 0.0,
                "alert": False,
                "fx_stale": False,
            }

        grouped: Dict[str, float] = {}
        incomplete_dates: set[str] = set()
        carried_forward_dates: set[str] = set()
        last_valid_equity_by_account: Dict[int, float] = {}
        stale_flag = False
        for row in rows:
            key = row.snapshot_date.isoformat()
            if self._snapshot_has_unpriced_positions(row):
                account_key = int(row.account_id)
                if account_key in last_valid_equity_by_account:
                    grouped[key] = grouped.get(key, 0.0) + last_valid_equity_by_account[account_key]
                    carried_forward_dates.add(key)
                    stale_flag = stale_flag or bool(row.fx_stale)
                else:
                    incomplete_dates.add(key)
                continue
            converted, stale, _ = self.portfolio_service.convert_amount(
                amount=float(row.total_equity or 0.0),
                from_currency=str(row.base_currency or "CNY"),
                to_currency="CNY",
                as_of_date=row.snapshot_date,
            )
            grouped[key] = grouped.get(key, 0.0) + converted
            last_valid_equity_by_account[int(row.account_id)] = converted
            stale_flag = stale_flag or stale or bool(row.fx_stale)

        for key in incomplete_dates:
            grouped.pop(key, None)

        series: List[Tuple[str, float]] = sorted(grouped.items(), key=lambda item: item[0])
        peak = 0.0
        max_drawdown = 0.0
        current_drawdown = 0.0
        for _, equity in series:
            peak = max(peak, equity)
            if peak <= 0:
                drawdown = 0.0
            else:
                drawdown = (peak - equity) / peak * 100.0
            max_drawdown = max(max_drawdown, drawdown)
            current_drawdown = drawdown

        return {
            "series_points": len(series),
            "skipped_points": len(incomplete_dates),
            "carried_forward_points": len(carried_forward_dates),
            "max_drawdown_pct": round(max_drawdown, 4),
            "current_drawdown_pct": round(current_drawdown, 4),
            "alert": bool(max_drawdown >= threshold_pct),
            "fx_stale": stale_flag,
        }

    @staticmethod
    def _snapshot_has_unpriced_positions(row: Any) -> bool:
        """Identify valuation snapshots where active holdings were priced as unavailable."""
        if float(getattr(row, "total_market_value", 0.0) or 0.0) > 0:
            return False
        payload_text = getattr(row, "payload", None)
        if not payload_text:
            return False
        try:
            payload = json.loads(payload_text)
        except (TypeError, ValueError):
            return False
        if not isinstance(payload, dict):
            return False

        positions = payload.get("positions")
        if not isinstance(positions, list):
            return False
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            quantity = float(pos.get("quantity") or 0.0)
            if quantity > 0 and pos.get("price_available") is False:
                return True
        return False

    @staticmethod
    def _build_stop_loss(snapshot: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
        stop_loss_pct = float(thresholds["stop_loss_alert_pct"])
        near_ratio = float(thresholds["stop_loss_near_ratio"])
        near_threshold = stop_loss_pct * near_ratio

        warnings: List[Dict[str, Any]] = []
        for account in snapshot.get("accounts", []):
            for pos in account.get("positions", []):
                if pos.get("price_available") is False:
                    continue
                avg_cost = float(pos.get("avg_cost", 0.0) or 0.0)
                last_price = float(pos.get("last_price", 0.0) or 0.0)
                if avg_cost <= 0 or last_price <= 0:
                    continue
                loss_pct = max(0.0, (avg_cost - last_price) / avg_cost * 100.0)
                if loss_pct < near_threshold:
                    continue
                warnings.append(
                    {
                        "account_id": account.get("account_id"),
                        "account_name": account.get("account_name"),
                        "symbol": pos.get("symbol"),
                        "market": pos.get("market"),
                        "currency": pos.get("currency"),
                        "avg_cost": round(avg_cost, 8),
                        "last_price": round(last_price, 8),
                        "loss_pct": round(loss_pct, 4),
                        "near_threshold_pct": round(near_threshold, 4),
                        "is_triggered": bool(loss_pct >= stop_loss_pct),
                    }
                )

        warnings.sort(key=lambda item: item["loss_pct"], reverse=True)
        return {
            "near_alert": len(warnings) > 0,
            "triggered_count": sum(1 for item in warnings if item["is_triggered"]),
            "near_count": len(warnings),
            "items": warnings[:20],
        }
