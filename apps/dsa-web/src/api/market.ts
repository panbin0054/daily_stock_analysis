import apiClient from './index';
import { toCamelCase } from './utils';
import type { NewHighQuery, NewHighResponse } from '../types/market';

/**
 * 市场数据 API
 */
export const marketApi = {
  /**
   * 获取创新高股票列表
   */
  getNewHighStocks: async (query: NewHighQuery = {}): Promise<NewHighResponse> => {
    const params: Record<string, string | number> = {};
    if (query.period) params.period = query.period;
    if (query.page) params.page = query.page;
    if (query.pageSize) params.page_size = query.pageSize;
    if (query.sortBy) params.sort_by = query.sortBy;
    if (query.sortOrder) params.sort_order = query.sortOrder;

    const response = await apiClient.get('/api/v1/market/new-highs', { params });
    return toCamelCase<NewHighResponse>(response.data);
  },
};
