import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, RefreshCw, TrendingUp } from 'lucide-react';
import { marketApi } from '../api/market';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Card, Loading, PageHeader } from '../components/common';
import type { NewHighPeriod, NewHighResponse, NewHighSortBy, SortOrder } from '../types/market';

/** 周期选项 */
const PERIOD_OPTIONS: { value: NewHighPeriod; label: string; description: string }[] = [
  { value: 'history', label: '历史新高', description: '创历史最高价' },
  { value: '20d', label: '近20日新高', description: '创近20个交易日新高' },
  { value: '60d', label: '近60日新高', description: '创近60个交易日新高' },
  { value: '120d', label: '近120日新高', description: '创近120个交易日新高' },
];

/** 排序选项 */
const SORT_OPTIONS: { value: NewHighSortBy; label: string }[] = [
  { value: 'change_pct', label: '涨跌幅' },
  { value: 'turnover_rate', label: '换手率' },
  { value: 'price', label: '最新价' },
];

/** 格式化数字 */
function formatNum(value: number | null, decimals = 2): string {
  if (value === null || value === undefined) return '-';
  return value.toFixed(decimals);
}


/** 涨跌颜色 */
function changeColor(value: number | null): string {
  if (value === null || value === undefined) return 'text-secondary-text';
  if (value > 0) return 'text-red-400';
  if (value < 0) return 'text-green-400';
  return 'text-secondary-text';
}

const NewHighsPage: React.FC = () => {
  useEffect(() => {
    document.title = '创新高 - DSA';
  }, []);

  const [data, setData] = useState<NewHighResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const [period, setPeriod] = useState<NewHighPeriod>('history');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [sortBy, setSortBy] = useState<NewHighSortBy>('change_pct');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await marketApi.getNewHighStocks({
        period,
        page,
        pageSize,
        sortBy,
        sortOrder,
      });
      setData(result);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, [period, page, pageSize, sortBy, sortOrder]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handlePeriodChange = (newPeriod: NewHighPeriod) => {
    setPeriod(newPeriod);
    setPage(1);
  };

  const handleSort = (field: NewHighSortBy) => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
    setPage(1);
  };

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  return (
    <AppPage className="space-y-5">
      <PageHeader
        eyebrow="Market · New Highs"
        title="创新高股票"
        description="A 股市场创新高股票实时统计。数据来源：同花顺。"
        actions={
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-1.5 text-sm"
            onClick={() => void fetchData()}
            disabled={loading}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        }
      />

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}

      {/* 周期选择 Tab */}
      <div className="flex flex-wrap gap-2">
        {PERIOD_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={`rounded-xl border px-4 py-2 text-sm font-medium transition-all ${
              period === opt.value
                ? 'border-cyan/50 bg-cyan/10 text-cyan shadow-sm shadow-cyan/10'
                : 'border-border/50 bg-card/50 text-secondary-text hover:border-border hover:bg-hover hover:text-foreground'
            }`}
            onClick={() => handlePeriodChange(opt.value)}
          >
            <span>{opt.label}</span>
          </button>
        ))}
      </div>

      {/* 信息栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {data ? (
            <>
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-cyan/10 px-3 py-1.5 text-xs font-medium text-cyan">
                <TrendingUp className="h-3.5 w-3.5" />
                共 {data.total} 只
              </span>
              <span className="text-xs text-secondary-text">
                更新于 {data.updateTime}
              </span>
            </>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-secondary-text">排序：</span>
          <select
            className="rounded-lg border border-border/50 bg-card/80 px-2 py-1 text-xs text-foreground"
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value as NewHighSortBy); setPage(1); }}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            type="button"
            className="rounded-lg border border-border/50 bg-card/80 p-1.5 text-secondary-text hover:text-foreground transition-colors"
            onClick={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
            title={sortOrder === 'desc' ? '降序' : '升序'}
          >
            {sortOrder === 'desc' ? <ArrowDown className="h-3.5 w-3.5" /> : <ArrowUp className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* 数据表格 */}
      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/30 text-xs text-secondary-text">
                <th className="whitespace-nowrap px-3 py-3 text-left font-medium">#</th>
                <th className="whitespace-nowrap px-3 py-3 text-left font-medium">代码</th>
                <th className="whitespace-nowrap px-3 py-3 text-left font-medium">名称</th>
                <th
                  className="whitespace-nowrap px-3 py-3 text-right font-medium cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => handleSort('price')}
                >
                  <span className="inline-flex items-center gap-1">
                    最新价
                    {sortBy === 'price' ? (sortOrder === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                  </span>
                </th>
                <th
                  className="whitespace-nowrap px-3 py-3 text-right font-medium cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => handleSort('change_pct')}
                >
                  <span className="inline-flex items-center gap-1">
                    涨跌幅
                    {sortBy === 'change_pct' ? (sortOrder === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                  </span>
                </th>
                <th className="whitespace-nowrap px-3 py-3 text-right font-medium">
                  <span className="inline-flex items-center gap-1" title="最新价相对前期高点的涨幅">
                    突破涨幅
                  </span>
                </th>
                <th
                  className="whitespace-nowrap px-3 py-3 text-right font-medium cursor-pointer hover:text-foreground transition-colors"
                  onClick={() => handleSort('turnover_rate')}
                >
                  <span className="inline-flex items-center gap-1">
                    换手率
                    {sortBy === 'turnover_rate' ? (sortOrder === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && !data ? (
                <tr>
                  <td colSpan={7} className="py-12">
                    <Loading className="mx-auto" />
                  </td>
                </tr>
              ) : data && data.items.length > 0 ? (
                data.items.map((item, idx) => (
                  <tr
                    key={item.code}
                    className="border-b border-border/10 transition-colors hover:bg-hover/50"
                  >
                    <td className="whitespace-nowrap px-3 py-2.5 text-secondary-text">
                      {(page - 1) * pageSize + idx + 1}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-secondary-text">
                      {item.code}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium text-foreground">
                      {item.name}
                    </td>
                    <td className={`whitespace-nowrap px-3 py-2.5 text-right font-mono ${changeColor(item.changePct)}`}>
                      {formatNum(item.price)}
                    </td>
                    <td className={`whitespace-nowrap px-3 py-2.5 text-right font-mono font-medium ${changeColor(item.changePct)}`}>
                      {item.changePct !== null ? `${item.changePct > 0 ? '+' : ''}${formatNum(item.changePct)}%` : '-'}
                    </td>
                    <td className={`whitespace-nowrap px-3 py-2.5 text-right font-mono ${item.breakthroughPct !== null && item.breakthroughPct > 0 ? 'text-red-400' : 'text-secondary-text'}`}>
                      {item.breakthroughPct !== null ? `${item.breakthroughPct > 0 ? '+' : ''}${formatNum(item.breakthroughPct)}%` : '-'}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-secondary-text">
                      {item.turnoverRate !== null ? `${formatNum(item.turnoverRate)}%` : '-'}
                    </td>
                  </tr>
                ))
              ) : !loading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-secondary-text">
                    暂无数据。可能当前非交易时段或无股票创新高。
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {/* 分页 */}
        {totalPages > 1 ? (
          <div className="flex items-center justify-between border-t border-border/20 px-4 py-3">
            <span className="text-xs text-secondary-text">
              第 {page} / {totalPages} 页，共 {data?.total ?? 0} 条
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn-secondary px-3 py-1 text-xs"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                上一页
              </button>
              <button
                type="button"
                className="btn-secondary px-3 py-1 text-xs"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </button>
            </div>
          </div>
        ) : null}
      </Card>

      {/* 数据加载中的半透明遮罩 */}
      {loading && data ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/20 backdrop-blur-[1px]">
          <div className="rounded-2xl bg-elevated/90 p-4 shadow-xl">
            <Loading />
          </div>
        </div>
      ) : null}
    </AppPage>
  );
};

export default NewHighsPage;
