from datetime import date
from unittest.mock import MagicMock, patch

from src.services.portfolio_risk_service import PortfolioRiskService
from src.services.portfolio_service import PortfolioService


def test_etf_sector_uses_position_name_when_fund_data_unavailable():
    service = PortfolioRiskService.__new__(PortfolioRiskService)
    service.portfolio_service = MagicMock(spec=PortfolioService)
    service.portfolio_service._is_cn_etf_position.side_effect = PortfolioService._is_cn_etf_position
    service.portfolio_service.convert_amount.side_effect = lambda **kwargs: (kwargs["amount"], False, None)
    service._fetch_industry_from_tushare = MagicMock(return_value=None)
    service._fetch_etf_sector = MagicMock(return_value=None)
    service._fetch_belong_boards = MagicMock(return_value=[])
    service._fetch_baostock_industry = MagicMock(return_value=None)
    snapshot = {"total_market_value": 300, "accounts": [{"positions": [
        {"symbol": "515790", "market": "cn", "name": "光伏ETF", "market_value_base": 100},
        {"symbol": "159999", "market": "cn", "name": "", "market_value_base": 100},
        {"symbol": "600001", "market": "cn", "name": "光伏股份", "market_value_base": 100},
    ]}]}

    result = service._build_sector_concentration(snapshot, 35, as_of_date=date(2026, 1, 1))

    sectors = {row["sector"]: row for row in result["top_sectors"]}
    assert sectors["光伏"]["market_value_base"] == 100
    assert sectors["UNCLASSIFIED"]["market_value_base"] == 200
    assert result["coverage"]["classified_count"] == 1
    assert result["coverage"]["unclassified_count"] == 2


def test_industry_lookup_retries_after_failure_and_caches_success():
    service = PortfolioRiskService.__new__(PortfolioRiskService)
    service._load_tushare_industry_map = MagicMock(side_effect=[{}, {"600160": "化工原料", "688795": "半导体"}])
    with patch.object(PortfolioRiskService, "_tushare_industry_cache", None), \
         patch.object(PortfolioRiskService, "_tushare_industry_retry_at", 0.0), \
         patch("src.services.portfolio_risk_service.time.monotonic", side_effect=[100, 100, 120, 176, 176, 177]):
        assert service._fetch_industry_from_tushare("600160") is None
        assert service._fetch_industry_from_tushare("688795") is None
        assert service._fetch_industry_from_tushare("600160") == "化工原料"
        assert service._fetch_industry_from_tushare("688795") == "半导体"
        assert service._load_tushare_industry_map.call_count == 2


def test_stock_uses_baostock_when_other_industry_sources_fail():
    service = PortfolioRiskService.__new__(PortfolioRiskService)
    service.portfolio_service = MagicMock(spec=PortfolioService)
    service.portfolio_service._is_cn_etf_position.side_effect = PortfolioService._is_cn_etf_position
    service._fetch_industry_from_tushare = MagicMock(return_value=None)
    service._fetch_etf_sector = MagicMock(return_value=None)
    service._fetch_belong_boards = MagicMock(return_value=[])
    service._fetch_baostock_industry = MagicMock(return_value="证监会：C26化学原料和化学制品制造业")
    coverage = {"classified_count": 0, "unclassified_count": 0, "failed_count": 0}
    sector = service._resolve_primary_sector(symbol="600160", market="cn", name="巨化股份", board_cache={}, coverage=coverage, errors=[])
    assert sector == "证监会：C26化学原料和化学制品制造业"
    assert coverage["classified_count"] == 1
    service._fetch_belong_boards.assert_not_called()
