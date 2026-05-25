import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import apiClient from '../../api/index';
import { systemConfigApi } from '../../api/systemConfig';
import { SettingsSectionCard } from './SettingsSectionCard';
import { Button } from '../common';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface SchedulerStatus {
  enabled: boolean;
  scheduleTime: string;
  runImmediately: boolean;
  stockList: string[];
  nextRun: string | null;
  lastRun: string | null;
  isRunning: boolean;
}

interface ScheduleCardProps {
  configVersion?: string;
  maskToken?: string;
  onSaved?: () => Promise<void> | void;
}

/* Helper: generic toggle switch */
const Toggle: React.FC<{
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}> = ({ checked, onChange, disabled }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary/40 focus:ring-offset-2 focus:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 ${
      checked ? 'bg-green-500' : 'bg-gray-500'
    }`}
  >
    <span
      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
        checked ? 'translate-x-5' : 'translate-x-0'
      }`}
    />
  </button>
);

/* Helper: status dot */
const StatusDot: React.FC<{ active: boolean; pulse?: boolean }> = ({ active, pulse }) => (
  <span
    className={`inline-block h-2 w-2 rounded-full ${
      active
        ? `bg-green-500 ${pulse ? 'animate-pulse' : ''}`
        : 'bg-gray-400'
    }`}
  />
);

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

export const ScheduleCard: React.FC<ScheduleCardProps> = ({
  configVersion,
  maskToken = '******',
  onSaved,
}) => {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [needsRestart, setNeedsRestart] = useState(false);
  const [restarting, setRestarting] = useState(false);

  /* Draft state for daily analysis config */
  const [draftEnabled, setDraftEnabled] = useState(false);
  const [draftTime, setDraftTime] = useState('18:00');
  const [draftRunImmediately, setDraftRunImmediately] = useState(true);
  const [isDirty, setIsDirty] = useState(false);

  /* Sub-task config (read from system config items) */
  const [marketReviewEnabled, setMarketReviewEnabled] = useState<boolean | null>(null);
  const [backtestEnabled, setBacktestEnabled] = useState<boolean | null>(null);
  const [eventMonitorEnabled, setEventMonitorEnabled] = useState<boolean | null>(null);
  const [eventMonitorInterval, setEventMonitorInterval] = useState<number | null>(null);

  /* ---- Fetch scheduler status ---- */
  const fetchStatus = useCallback(async () => {
    try {
      const resp = await apiClient.get<Record<string, unknown>>('/api/v1/system/scheduler/status');
      const data = resp.data;
      const newStatus: SchedulerStatus = {
        enabled: data.enabled as boolean,
        scheduleTime: data.schedule_time as string,
        runImmediately: data.run_immediately as boolean,
        stockList: (data.stock_list as string[]) || [],
        nextRun: (data.next_run as string) || null,
        lastRun: (data.last_run as string) || null,
        isRunning: (data.is_running as boolean) || false,
      };
      setStatus(newStatus);
      if (!isDirty) {
        setDraftEnabled(newStatus.enabled);
        setDraftTime(newStatus.scheduleTime || '18:00');
        setDraftRunImmediately(newStatus.runImmediately);
      }
    } catch {
      // Silently fail - non-critical UI
    } finally {
      setLoading(false);
    }
  }, [isDirty]);

  /* ---- Fetch sub-task config from system config ---- */
  const fetchSubTaskConfig = useCallback(async () => {
    try {
      const configResp = await systemConfigApi.getConfig(false);
      const items = configResp.items || [];
      for (const item of items) {
        switch (item.key) {
          case 'MARKET_REVIEW_ENABLED':
            setMarketReviewEnabled(item.value === 'true');
            break;
          case 'BACKTEST_ENABLED':
            setBacktestEnabled(item.value === 'true');
            break;
          case 'AGENT_EVENT_MONITOR_ENABLED':
            setEventMonitorEnabled(item.value === 'true');
            break;
          case 'AGENT_EVENT_MONITOR_INTERVAL_MINUTES':
            setEventMonitorInterval(Number(item.value) || 5);
            break;
        }
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
    void fetchSubTaskConfig();
    const interval = setInterval(() => {
      void fetchStatus();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchStatus, fetchSubTaskConfig]);

  /* ---- Dirty tracking ---- */
  useEffect(() => {
    if (!status) return;
    const dirty =
      draftEnabled !== status.enabled ||
      draftTime !== (status.scheduleTime || '18:00') ||
      draftRunImmediately !== status.runImmediately;
    setIsDirty(dirty);
  }, [draftEnabled, draftTime, draftRunImmediately, status]);

  /* ---- Save ---- */
  const handleSave = async () => {
    setSaving(true);
    setSaveMessage(null);
    setSaveError(null);
    setNeedsRestart(false);
    try {
      let version = configVersion;
      if (!version) {
        const configResp = await systemConfigApi.getConfig(false);
        version = configResp.configVersion;
      }
      await systemConfigApi.update({
        configVersion: version || '',
        maskToken,
        reloadNow: true,
        items: [
          { key: 'SCHEDULE_ENABLED', value: draftEnabled ? 'true' : 'false' },
          { key: 'SCHEDULE_TIME', value: draftTime },
          { key: 'SCHEDULE_RUN_IMMEDIATELY', value: draftRunImmediately ? 'true' : 'false' },
        ],
      });
      // Determine which configs changed and whether a restart is needed
      const enabledChanged = status && draftEnabled !== status.enabled;
      const runImmediatelyChanged = status && draftRunImmediately !== status.runImmediately;
      const timeOnlyChanged = status && draftTime !== (status.scheduleTime || '18:00')
        && !enabledChanged && !runImmediatelyChanged;

      if (timeOnlyChanged) {
        // SCHEDULE_TIME supports hot-reload, no restart needed
        setSaveMessage('执行时间已更新，将在下一轮调度中自动生效（约30秒内）');
      } else if (enabledChanged || runImmediatelyChanged) {
        // These require a restart
        setSaveMessage('配置已保存，需要重启服务后生效');
        setNeedsRestart(true);
      } else {
        setSaveMessage('定时任务配置已保存');
      }
      setIsDirty(false);
      setTimeout(() => void fetchStatus(), 1000);
      if (onSaved) await onSaved();
    } catch (err: unknown) {
      const error = err as { message?: string; response?: { data?: { detail?: { message?: string } } } };
      setSaveError(
        error?.response?.data?.detail?.message || error?.message || '保存失败，请重试'
      );
    } finally {
      setSaving(false);
    }
  };

  /* ---- Restart service ---- */
  const handleRestart = async () => {
    setRestarting(true);
    setSaveError(null);
    try {
      await apiClient.post('/api/v1/system/scheduler/restart');
      setSaveMessage('服务正在重启，请等待几秒后页面会自动刷新...');
      setNeedsRestart(false);
      // Wait a few seconds then reload the page
      setTimeout(() => {
        window.location.reload();
      }, 5000);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: { message?: string } } } };
      setSaveError(
        error?.response?.data?.detail?.message || '重启请求失败，请手动重启服务'
      );
      setRestarting(false);
    }
  };

  /* ---- Manual trigger ---- */
  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerMessage(null);
    setTriggerError(null);
    try {
      const resp = await apiClient.post<Record<string, unknown>>('/api/v1/system/scheduler/trigger');
      setTriggerMessage((resp.data.message as string) || '分析任务已触发');
      setTimeout(() => void fetchStatus(), 2000);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: { message?: string } } } };
      setTriggerError(
        error?.response?.data?.detail?.message || '触发失败，请查看后端日志'
      );
    } finally {
      setTriggering(false);
    }
  };

  /* ---- Render ---- */
  if (loading) {
    return (
      <SettingsSectionCard title="定时任务" description="管理系统中所有定时和周期任务。">
        <div className="flex items-center justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="ml-2 text-sm text-muted-text">加载中...</span>
        </div>
      </SettingsSectionCard>
    );
  }

  return (
    <div className="space-y-4">
      {/* ===== Task 1: Daily Full Analysis (Main Scheduled Task) ===== */}
      <SettingsSectionCard
        title="📊 每日全量分析"
        description="定时分析自选股 → 大盘复盘 → 生成报告 → 推送通知。这是系统的主定时任务。"
        actions={
          <div className="flex items-center gap-2">
            {isDirty && (
              <Button
                type="button"
                variant="settings-primary"
                onClick={() => void handleSave()}
                disabled={saving}
                isLoading={saving}
                loadingText="保存中..."
              >
                保存配置
              </Button>
            )}
            <Button
              type="button"
              variant={isDirty ? 'settings-secondary' : 'settings-primary'}
              onClick={() => void handleTrigger()}
              disabled={triggering || (status?.isRunning ?? false)}
              isLoading={triggering}
              loadingText="触发中..."
            >
              {status?.isRunning ? '分析执行中...' : '立即执行分析'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          {/* Editable config */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Enable/disable toggle */}
            <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
              <label className="flex cursor-pointer items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                    调度状态
                  </p>
                  <p className="mt-1 text-sm text-foreground">
                    {draftEnabled ? '已启用' : '未启用'}
                  </p>
                </div>
                <Toggle checked={draftEnabled} onChange={setDraftEnabled} />
              </label>
            </div>

            {/* Schedule time */}
            <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                执行时间
              </p>
              <div className="mt-1 flex items-center gap-2">
                <span className="text-sm text-muted-text">每日</span>
                <input
                  type="time"
                  value={draftTime}
                  onChange={(e) => setDraftTime(e.target.value)}
                  className="rounded-lg border settings-border bg-background/60 px-2 py-1 text-sm font-mono text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
                />
              </div>
            </div>

            {/* Run immediately on start */}
            <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
              <label className="flex cursor-pointer items-center justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                    启动立即执行
                  </p>
                  <p className="mt-1 text-xs text-muted-text">
                    启动时先执行一次
                  </p>
                </div>
                <Toggle checked={draftRunImmediately} onChange={setDraftRunImmediately} />
              </label>
            </div>
          </div>

          {/* Runtime status (read-only) */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                上次执行
              </p>
              <p className="mt-2 font-mono text-sm text-foreground">
                {status?.lastRun || '暂无记录'}
              </p>
            </div>

            <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                执行状态
              </p>
              <p className="mt-2 flex items-center gap-2 text-sm text-foreground">
                {status?.isRunning ? (
                  <>
                    <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                    <span className="font-medium text-blue-400">执行中</span>
                  </>
                ) : (
                  <>
                    <span className="inline-block h-2 w-2 rounded-full bg-gray-400" />
                    空闲
                  </>
                )}
              </p>
            </div>

            <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                自选股（{status?.stockList?.length || 0} 只）
              </p>
              <p className="mt-2 font-mono text-xs leading-relaxed text-foreground truncate" title={status?.stockList?.join('、')}>
                {status?.stockList?.length ? status.stockList.join('、') : '未配置'}
              </p>
            </div>
          </div>

          {/* Messages */}
          {saveMessage && (
            <div className="rounded-xl border border-green-500/30 bg-green-500/10 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-green-400">{saveMessage}</p>
                {needsRestart && (
                  <Button
                    type="button"
                    variant="settings-primary"
                    onClick={() => void handleRestart()}
                    disabled={restarting}
                    isLoading={restarting}
                    loadingText="重启中..."
                    className="shrink-0"
                  >
                    🔄 重启服务
                  </Button>
                )}
              </div>
            </div>
          )}
          {saveError && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
              <p className="text-sm text-red-400">{saveError}</p>
            </div>
          )}
          {triggerMessage && (
            <div className="rounded-xl border border-green-500/30 bg-green-500/10 px-4 py-3">
              <p className="text-sm text-green-400">{triggerMessage}</p>
            </div>
          )}
          {triggerError && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
              <p className="text-sm text-red-400">{triggerError}</p>
            </div>
          )}
          {isDirty && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
              <p className="text-sm text-amber-400">⚠️ 配置已修改但未保存，点击「保存配置」生效。</p>
            </div>
          )}
        </div>
      </SettingsSectionCard>

      {/* ===== Sub-tasks included in daily analysis ===== */}
      <SettingsSectionCard
        title="子任务"
        description="每日全量分析执行时会按顺序运行以下子任务（在对应设置分类中开启/关闭）。"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {/* 个股分析 */}
          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                📈 个股分析
              </p>
              <StatusDot active pulse={status?.isRunning} />
            </div>
            <p className="mt-2 text-sm text-foreground font-medium">始终启用</p>
            <p className="mt-1 text-xs text-muted-text">
              分析自选股，生成个股报告并推送通知
            </p>
          </div>

          {/* 大盘复盘 */}
          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                🌍 大盘复盘
              </p>
              <StatusDot active={marketReviewEnabled === true} />
            </div>
            <p className="mt-2 text-sm text-foreground font-medium">
              {marketReviewEnabled === null ? '加载中...' : marketReviewEnabled ? '已启用' : '未启用'}
            </p>
            <p className="mt-1 text-xs text-muted-text">
              复盘 A 股 / 港股 / 美股大盘走势
            </p>
            <p className="mt-1 text-[10px] text-muted-text/70">
              配置项：基础设置 → MARKET_REVIEW_ENABLED
            </p>
          </div>

          {/* 自动回测 */}
          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                🔄 自动回测
              </p>
              <StatusDot active={backtestEnabled === true} />
            </div>
            <p className="mt-2 text-sm text-foreground font-medium">
              {backtestEnabled === null ? '加载中...' : backtestEnabled ? '已启用' : '未启用'}
            </p>
            <p className="mt-1 text-xs text-muted-text">
              评估历史分析结果准确性
            </p>
            <p className="mt-1 text-[10px] text-muted-text/70">
              配置项：回测配置 → BACKTEST_ENABLED
            </p>
          </div>

          {/* 飞书云文档 */}
          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                📄 飞书云文档
              </p>
              <StatusDot active={false} />
            </div>
            <p className="mt-2 text-sm text-foreground font-medium">按配置自动触发</p>
            <p className="mt-1 text-xs text-muted-text">
              配置飞书应用凭据后自动生成每日云文档
            </p>
            <p className="mt-1 text-[10px] text-muted-text/70">
              配置项：通知渠道 → FEISHU_APP_ID / SECRET
            </p>
          </div>
        </div>
      </SettingsSectionCard>

      {/* ===== Task 2: Event Monitor (Independent Periodic Task) ===== */}
      <SettingsSectionCard
        title="🔔 Agent 事件监控"
        description="独立周期任务 — 按固定间隔轮询实时行情，监控价格突破、成交量异常等告警规则。"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                  监控状态
                </p>
                <p className="mt-1 text-sm text-foreground">
                  {eventMonitorEnabled === null ? '加载中...' : eventMonitorEnabled ? '已启用' : '未启用'}
                </p>
              </div>
              <StatusDot active={eventMonitorEnabled === true} pulse={eventMonitorEnabled === true} />
            </div>
          </div>

          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
              轮询间隔
            </p>
            <p className="mt-1 text-sm font-mono text-foreground">
              每 {eventMonitorInterval ?? 5} 分钟
            </p>
          </div>

          <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
              支持的告警类型
            </p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {['价格穿越', '涨跌幅', '量能异常'].map((tag) => (
                <span key={tag} className="rounded-lg bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-text">
          💡 在 <strong>Agent 设置</strong> 分类中配置 AGENT_EVENT_MONITOR_ENABLED 和告警规则。
        </p>
      </SettingsSectionCard>

      {/* ===== Architecture Overview ===== */}
      <SettingsSectionCard
        title="调度架构"
        description="系统定时任务运行全景。"
      >
        <div className="rounded-2xl border settings-border bg-background/30 px-5 py-4 font-mono text-xs leading-6 text-muted-text overflow-x-auto">
          <pre className="whitespace-pre">{`Scheduler
├── Daily Job (${draftTime || '18:00'})
│   └── run_full_analysis()
│       ├── 1. 个股分析       ✅ 始终启用
│       ├── 2. 大盘复盘       ${marketReviewEnabled ? '✅ 已启用' : '⬚ 未启用'}
│       ├── 3. 合并推送       ✅ 始终启用
│       ├── 4. 飞书云文档     ⚙️ 按配置触发
│       └── 5. 自动回测       ${backtestEnabled ? '✅ 已启用' : '⬚ 未启用'}
│
└── Event Monitor (每 ${eventMonitorInterval ?? 5} 分钟)
    └── AlertWorker     ${eventMonitorEnabled ? '✅ 已启用' : '⬚ 未启用'}`}</pre>
        </div>
      </SettingsSectionCard>
    </div>
  );
};
