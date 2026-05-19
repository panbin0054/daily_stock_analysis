/**
 * 创新高股票相关类型定义
 */

/** 创新高周期类型 */
export type NewHighPeriod = 'history' | '20d' | '60d' | '120d';

/** 排序字段 */
export type NewHighSortBy = 'change_pct' | 'turnover_rate' | 'price';

/** 排序方向 */
export type SortOrder = 'asc' | 'desc';

/** 创新高股票条目 */
export interface NewHighStockItem {
  code: string;
  name: string;
  price: number | null;
  changePct: number | null;
  turnoverRate: number | null;
  prevHigh: number | null;
  prevHighDate: string | null;
  breakthroughPct: number | null;
}

/** 创新高股票响应 */
export interface NewHighResponse {
  items: NewHighStockItem[];
  total: number;
  period: string;
  updateTime: string;
}

/** 请求参数 */
export interface NewHighQuery {
  period?: NewHighPeriod;
  page?: number;
  pageSize?: number;
  sortBy?: NewHighSortBy;
  sortOrder?: SortOrder;
}
