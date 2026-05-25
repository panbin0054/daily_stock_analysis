import React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AnalysisResult, AnalysisReport } from '../../types/analysis';
import { ReportOverview } from './ReportOverview';
import { ReportStrategy } from './ReportStrategy';
import { ReportNews } from './ReportNews';
import { ReportDetails } from './ReportDetails';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';

interface ReportSummaryProps {
  data: AnalysisResult | AnalysisReport;
  isHistory?: boolean;
}

/**
 * 完整报告展示组件
 * 整合概览、策略、资讯、详情四个区域
 */
export const ReportSummary: React.FC<ReportSummaryProps> = ({
  data,
  isHistory = false,
}) => {
  // 兼容 AnalysisResult 和 AnalysisReport 两种数据格式
  const report: AnalysisReport = 'report' in data ? data.report : data;
  // 使用 report id，因为 queryId 在批量分析时可能重复，且历史报告详情接口需要 recordId 来获取关联资讯和详情数据
  const recordId = report.meta.id;

  const { meta, summary, strategy, details } = report;
  const reportLanguage = normalizeReportLanguage(meta.reportLanguage);
  const text = getReportText(reportLanguage);
  const modelUsed = (meta.modelUsed || '').trim();
  const shouldShowModel = Boolean(
    modelUsed && !['unknown', 'error', 'none', 'null', 'n/a'].includes(modelUsed.toLowerCase()),
  );
  const isMarketReview = meta.reportType === 'market_review';
  const marketReviewContent = (details?.newsContent || summary.analysisSummary || '').trim();

  if (isMarketReview) {
    return (
      <div className="space-y-5 pb-8 animate-fade-in">
        <Card variant="bordered" padding="md" className="home-panel-card text-left">
          <DashboardPanelHeader
            eyebrow={meta.stockCode}
            title={meta.stockName || text.fullReport}
            className="mb-3"
          />
          {marketReviewContent ? (
            <div
              className="home-markdown-prose prose prose-invert prose-sm max-w-none
                prose-headings:text-foreground prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
                prose-h1:text-xl
                prose-h2:text-lg
                prose-h3:text-base
                prose-p:leading-relaxed prose-p:mb-3 prose-p:last:mb-0
                prose-strong:text-foreground prose-strong:font-semibold
                prose-ul:my-2 prose-ol:my-2 prose-li:my-1
                prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none
                prose-pre:border
                prose-table:border-collapse
                prose-hr:my-4
                prose-a:no-underline hover:prose-a:underline
                prose-blockquote:text-secondary-text
                whitespace-pre-line break-words"
              data-testid="market-review-history-content"
            >
              <Markdown remarkPlugins={[remarkGfm]}>
                {marketReviewContent}
              </Markdown>
            </div>
          ) : (
            <p className="text-sm text-secondary-text">{text.noAnalysisSummary}</p>
          )}
        </Card>

        {shouldShowModel && (
          <p className="px-1 text-xs text-muted-text">
            {text.analysisModel}: {modelUsed}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-8 animate-fade-in">
      {/* 概览区（首屏） */}
      <ReportOverview
        meta={meta}
        summary={summary}
        details={details}
        isHistory={isHistory}
      />

      {/* 策略点位区 */}
      <ReportStrategy strategy={strategy} language={reportLanguage} />

      {/* 资讯区 */}
      <ReportNews recordId={recordId} limit={8} language={reportLanguage} />

      {/* 透明度与追溯区 */}
      <ReportDetails details={details} recordId={recordId} language={reportLanguage} />

      {/* 分析模型标记（Issue #528）— 报告末尾 */}
      {shouldShowModel && (
        <p className="px-1 text-xs text-muted-text">
          {text.analysisModel}: {modelUsed}
        </p>
      )}
    </div>
  );
};
