# -*- coding: utf-8 -*-
"""
===================================
Market Data Endpoints
===================================

提供市场数据相关 API：
- 创历史新高股票
- 连续创新高股票（月新高/半年新高/一年新高）
- 大盘指数概览

数据源：
- 主数据源: akshare (stock_rank_cxg_ths, 来自同花顺)
- 备用数据源: 东方财富网 (push2.eastmoney.com) 概念板块
"""

import logging
import random
import time
from datetime import datetime
from typing import Optional

import requests
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------- 常量 ----------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

_EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"

# 东方财富字段映射
# f2=最新价, f3=涨跌幅, f4=涨跌额, f5=成交量(手), f6=成交额, f7=振幅
# f8=换手率, f9=市盈率, f12=代码, f14=名称, f15=最高价, f16=最低价
# f17=开盘价, f18=昨收, f109=历史新高距今天数, f124=更新时间
_FIELDS = "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f15,f16,f17,f18,f109,f124"

# akshare 周期映射
_AKSHARE_PERIOD_MAP = {
    "history": "历史新高",
    "20d": "创月新高",
    "60d": "半年新高",
    "120d": "一年新高",
}


# ---------- Schema ----------

class NewHighStockItem(BaseModel):
    """创新高股票条目"""
    code: str = Field(description="股票代码")
    name: str = Field(description="股票名称")
    price: Optional[float] = Field(None, description="最新价")
    change_pct: Optional[float] = Field(None, description="涨跌幅(%)")
    turnover_rate: Optional[float] = Field(None, description="换手率(%)")
    prev_high: Optional[float] = Field(None, description="前期高点价格")
    prev_high_date: Optional[str] = Field(None, description="前期高点日期")
    breakthrough_pct: Optional[float] = Field(None, description="突破涨幅(%)，最新价相对前期高点的涨幅")


class NewHighResponse(BaseModel):
    """创新高股票响应"""
    items: list[NewHighStockItem] = Field(default_factory=list, description="股票列表")
    total: int = Field(0, description="总数量")
    period: str = Field("", description="周期(history/20d/60d/120d)")
    update_time: str = Field("", description="数据更新时间")


# ---------- 内部工具函数 ----------

def _get_headers() -> dict:
    """获取随机 UA 请求头"""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Referer": "https://data.eastmoney.com/",
        "Accept": "application/json, text/plain, */*",
    }


def _safe_float(value) -> Optional[float]:
    """安全转换为浮点数"""
    if value is None or value == "-" or value == "":
        return None
    try:
        v = float(value)
        # 东方财富用极大数表示无数据
        if abs(v) > 1e15:
            return None
        return v
    except (ValueError, TypeError):
        return None


def _fetch_new_high_stocks_akshare(
    period: str = "history",
    page: int = 1,
    page_size: int = 50,
    sort_field: str = "f3",
    sort_order: int = 0,
) -> Optional[NewHighResponse]:
    """
    通过 akshare (同花顺数据源) 获取创新高股票数据

    Args:
        period: 周期类型
            - "history": 历史新高
            - "20d": 创月新高
            - "60d": 半年新高
            - "120d": 一年新高
        page: 页码
        page_size: 每页条数
        sort_field: 排序字段 (f3=涨跌幅, f8=换手率, f2=最新价)
        sort_order: 排序方式 (0=降序, 1=升序)

    Returns:
        NewHighResponse or None if failed
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warning("[market] akshare 未安装, 跳过同花顺数据源")
        return None

    symbol = _AKSHARE_PERIOD_MAP.get(period, "历史新高")

    try:
        df = ak.stock_rank_cxg_ths(symbol=symbol)
    except Exception as e:
        logger.warning(f"[market] akshare 获取创新高失败 (symbol={symbol}): {e}")
        return None

    if df is None or df.empty:
        return NewHighResponse(items=[], total=0, period=period, update_time="")

    # 排序
    sort_col_map = {
        "f3": "涨跌幅",
        "f8": "换手率",
        "f2": "最新价",
    }
    sort_col = sort_col_map.get(sort_field, "涨跌幅")
    ascending = sort_order == 1  # 0=降序, 1=升序

    if sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")

    total = len(df)

    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]

    items: list[NewHighStockItem] = []
    for _, row in page_df.iterrows():
        code = str(row.get("股票代码", ""))
        name = str(row.get("股票简称", ""))
        if not code or not name:
            continue
        price = _safe_float(row.get("最新价"))
        prev_high = _safe_float(row.get("前期高点"))
        prev_high_date = None
        if "前期高点日期" in row.index and row.get("前期高点日期") is not None:
            prev_high_date = str(row.get("前期高点日期"))

        # 计算突破涨幅：(最新价 - 前期高点) / 前期高点 * 100
        breakthrough_pct = None
        if price is not None and prev_high is not None and prev_high > 0:
            breakthrough_pct = round((price - prev_high) / prev_high * 100, 2)

        items.append(NewHighStockItem(
            code=code,
            name=name,
            price=price,
            change_pct=_safe_float(row.get("涨跌幅")),
            turnover_rate=_safe_float(row.get("换手率")),
            prev_high=prev_high,
            prev_high_date=prev_high_date,
            breakthrough_pct=breakthrough_pct,
        ))

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return NewHighResponse(
        items=items,
        total=total,
        period=period,
        update_time=update_time,
    )


def _fetch_new_high_stocks_eastmoney(
    period: str = "history",
    page: int = 1,
    page_size: int = 50,
    sort_field: str = "f3",
    sort_order: int = 0,
) -> Optional[NewHighResponse]:
    """
    从东方财富概念板块获取创新高股票数据 (备用数据源)

    仅在国内服务器可用, 海外 IP 会被 502 拦截。
    """
    period_map = {
        "history": "BK1675",
        "20d": "BK1674",
        "60d": "BK1676",
        "120d": "BK0815",
    }

    bk_code = period_map.get(period, "BK1675")

    params = {
        "fid": sort_field,
        "po": str(sort_order),
        "pz": str(page_size),
        "pn": str(page),
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "fs": f"b:{bk_code}",
        "fields": _FIELDS,
    }

    try:
        resp = requests.get(
            _EASTMONEY_LIST_URL,
            params=params,
            headers=_get_headers(),
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"[market] 东方财富获取创新高失败: {e}")
        return None

    if not data or data.get("data") is None:
        return None

    result_data = data["data"]
    total = result_data.get("total", 0)
    diff_list = result_data.get("diff", [])

    items: list[NewHighStockItem] = []
    for item in diff_list:
        if not item:
            continue
        code = str(item.get("f12", ""))
        name = str(item.get("f14", ""))
        if not code or not name:
            continue
        price = _safe_float(item.get("f2"))
        items.append(NewHighStockItem(
            code=code,
            name=name,
            price=price,
            change_pct=_safe_float(item.get("f3")),
            turnover_rate=_safe_float(item.get("f8")),
            prev_high=None,
            prev_high_date=None,
            breakthrough_pct=None,
        ))

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return NewHighResponse(
        items=items,
        total=total,
        period=period,
        update_time=update_time,
    )


def _fetch_new_high_stocks(
    period: str = "history",
    page: int = 1,
    page_size: int = 50,
    sort_field: str = "f3",
    sort_order: int = 0,
) -> NewHighResponse:
    """
    获取创新高股票数据 (多数据源 fallback)

    优先使用 akshare (同花顺), 失败则 fallback 到东方财富概念板块。

    Args:
        period: 周期类型
            - "history": 历史新高
            - "20d": 创月新高 / 近期新高
            - "60d": 半年新高 / 百日新高
            - "120d": 一年新高 / 阶段新高
        page: 页码
        page_size: 每页条数
        sort_field: 排序字段 (f3=涨跌幅, f6=成交额, f8=换手率)
        sort_order: 排序方式 (0=降序, 1=升序)

    Returns:
        NewHighResponse
    """
    # 优先 akshare
    result = _fetch_new_high_stocks_akshare(
        period=period, page=page, page_size=page_size,
        sort_field=sort_field, sort_order=sort_order,
    )
    if result and result.items:
        return result

    # fallback: 东方财富
    result = _fetch_new_high_stocks_eastmoney(
        period=period, page=page, page_size=page_size,
        sort_field=sort_field, sort_order=sort_order,
    )
    if result and result.items:
        return result

    logger.warning(f"[market] 所有数据源均未获取到创新高数据 (period={period})")
    return NewHighResponse(items=[], total=0, period=period, update_time="")


# ---------- API 端点 ----------

@router.get(
    "/new-highs",
    response_model=NewHighResponse,
    summary="获取创新高股票列表",
    description="获取 A 股创新高股票列表。主数据源：同花顺（akshare），备用数据源：东方财富。",
)
async def get_new_high_stocks(
    period: str = Query("history", description="周期: history(历史新高), 20d(20日新高), 60d(60日新高), 120d(120日新高)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100, description="每页条数"),
    sort_by: str = Query("change_pct", description="排序字段: change_pct(涨跌幅), turnover_rate(换手率), price(最新价)"),
    sort_order: str = Query("desc", description="排序方式: asc(升序), desc(降序)"),
):
    """获取创新高股票列表"""
    # 映射排序字段
    sort_field_map = {
        "change_pct": "f3",
        "turnover_rate": "f8",
        "price": "f2",
    }
    field = sort_field_map.get(sort_by, "f3")
    order = 0 if sort_order == "desc" else 1

    return _fetch_new_high_stocks(
        period=period,
        page=page,
        page_size=page_size,
        sort_field=field,
        sort_order=order,
    )
