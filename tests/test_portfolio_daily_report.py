from datetime import date
from unittest.mock import patch

import pytest

from src.portfolio_daily_report import build_report, is_report_day
from src.portfolio_daily_image import position_pnl


def test_position_pnl_uses_unrealized_cost_basis_and_excludes_cash():
    snapshot = {'total_market_value': 1200, 'unrealized_pnl': 200, 'total_cash': 9000,
                'accounts': [{'positions': [{'quantity': 1, 'last_price': 1200, 'price_available': True}]}]}
    assert position_pnl(snapshot) == (200, 20)


def test_position_pnl_degrades_if_any_position_is_unpriced():
    snapshot = {'total_market_value': 1200, 'unrealized_pnl': 200,
                'accounts': [{'positions': [{'quantity': 1, 'last_price': 0, 'price_available': False}]}]}
    assert position_pnl(snapshot) == (None, None)


def test_position_pnl_has_no_ratio_when_cost_is_zero():
    assert position_pnl({'total_market_value': 0, 'unrealized_pnl': 0, 'accounts': []}) == (0, None)


@pytest.mark.parametrize('sessions,expected', [
    (([], []), False),
    (([1], []), True),
    (([], [1]), True),
    ((None, [1]), True),
])
def test_report_day_uses_either_market(sessions, expected):
    with patch('src.portfolio_daily_report.get_trading_dates', side_effect=sessions):
        assert is_report_day(date(2026, 11, 10)) is expected


def test_unknown_calendar_does_not_silently_send():
    with patch('src.portfolio_daily_report.get_trading_dates', side_effect=[None, []]):
        with pytest.raises(RuntimeError):
            is_report_day(date(2026, 11, 10))


def test_refresh_precedes_snapshot_and_risk_uses_same_snapshot():
    class Portfolio:
        def __init__(self):
            self.calls = []
        def refresh_fx_rates(self, **kwargs):
            self.calls.append('fx')
            return {'refresh_enabled': True, 'stale_count': 0, 'error_count': 0}
        def get_portfolio_snapshot(self, **kwargs):
            self.calls.append('snapshot')
            return {'identity': object()}

    class Risk:
        def __init__(self, portfolio_service):
            self.service = portfolio_service
        def get_risk_report(self, as_of, **kwargs):
            return {'snapshot': self.service.get_portfolio_snapshot(account_id=None, as_of=as_of)}

    service = Portfolio()
    result = build_report(service, Risk)
    assert service.calls == ['fx', 'snapshot']
    assert result['risk']['snapshot'] is result['snapshot']
    assert result['fx_failed'] is False


def test_refresh_failure_is_marked_in_report():
    class Portfolio:
        def refresh_fx_rates(self, **kwargs):
            raise RuntimeError('unavailable')
        def get_portfolio_snapshot(self, **kwargs):
            return {}

    class Risk:
        def __init__(self, portfolio_service):
            pass
        def get_risk_report(self, **kwargs):
            return {}

    assert build_report(Portfolio(), Risk)['fx_failed'] is True
