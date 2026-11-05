from datetime import date
from unittest.mock import Mock, patch

from scripts.backfill_portfolio_hkd_cny import fetch_rates


def test_ecb_cross_rate_uses_matching_dates_and_ignores_incomplete_pairs():
    response = Mock()
    response.text = (
        "CURRENCY,CURRENCY_DENOM,TIME_PERIOD,OBS_VALUE\n"
        "HKD,EUR,2026-05-15,8\nCNY,EUR,2026-05-15,7\n"
        "HKD,EUR,2026-05-18,9\nCNY,EUR,2026-05-19,8\n"
        "CNY,EUR,2026-05-20,0\nHKD,EUR,2026-05-20,8\n"
    )
    with patch("scripts.backfill_portfolio_hkd_cny.requests.get", return_value=response):
        assert fetch_rates(date(2026, 5, 15), date(2026, 5, 20)) == [("2026-05-15", 0.875)]
