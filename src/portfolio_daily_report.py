"""Generate and deliver the daily portfolio image to Telegram."""

import argparse
import logging
from datetime import date, datetime

from src.core.trading_calendar import get_trading_dates
from src.notification import NotificationService
from src.portfolio_daily_image import render_report
from src.services.portfolio_risk_service import PortfolioRiskService
from src.services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)


def is_report_day(day):
    """Run on a session in either market; do not silently treat errors as sessions."""
    sessions = [get_trading_dates(market, day, day) for market in ('cn', 'hk')]
    if any(value is not None and len(value) for value in sessions):
        return True
    if any(value is None for value in sessions):
        raise RuntimeError('无法确定 A 股或港股交易日')
    return False


def build_report(service=None, risk_service_class=PortfolioRiskService):
    service = service or PortfolioService()
    today = date.today()
    fx_failed = False
    try:
        fx = service.refresh_fx_rates(as_of=today)
        fx_failed = not fx['refresh_enabled'] or bool(fx['stale_count'] or fx['error_count'])
    except Exception:
        logger.exception('刷新汇率失败，将标注已有汇率可能过期')
        fx_failed = True

    snapshot = service.get_portfolio_snapshot(as_of=today, include_realtime=True)
    original = service.get_portfolio_snapshot

    def snapshot_for_risk(*args, **kwargs):
        if not args and kwargs.get('account_id') is None and kwargs.get('as_of') == today:
            return snapshot
        return original(*args, **kwargs)

    service.get_portfolio_snapshot = snapshot_for_risk
    try:
        risk = risk_service_class(portfolio_service=service).get_risk_report(as_of=today, include_realtime=True)
    finally:
        service.get_portfolio_snapshot = original
    return {'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'snapshot': snapshot, 'risk': risk, 'fx_failed': fx_failed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='send even on a non-trading day')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if not args.force and not is_report_day(date.today()):
        logger.info('A 股和港股均休市，跳过持仓日报')
        return 0
    report = build_report()
    image = render_report(report)
    if not NotificationService()._send_telegram_photo(image):
        raise RuntimeError('持仓日报图片发送失败')
    logger.info('持仓日报图片已发送')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
