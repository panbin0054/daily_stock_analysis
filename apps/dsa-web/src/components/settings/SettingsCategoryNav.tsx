import type React from 'react';
import { useMemo } from 'react';
import { Badge } from '../common';
import { getCategoryDescriptionZh, getCategoryTitleZh } from '../../utils/systemConfigI18n';
import type { SystemConfigCategorySchema, SystemConfigItem } from '../../types/systemConfig';
import { cn } from '../../utils/cn';

/**
 * Virtual categories are front-end-only nav entries that don't come from
 * the backend config registry.  They are injected into the sidebar at a
 * specific display order position.
 */
interface VirtualCategory {
  category: string;
  title: string;
  description: string;
  displayOrder: number;
  /** When set, this badge label replaces the numeric item count. */
  badgeLabel?: string;
}

const VIRTUAL_CATEGORIES: VirtualCategory[] = [
  {
    category: 'schedule',
    title: '定时任务',
    description: '管理定时分析、事件监控等周期任务。',
    displayOrder: 15, // between base(10) and ai_model(20)
    badgeLabel: '⏱',
  },
];

interface SettingsCategoryNavProps {
  categories: SystemConfigCategorySchema[];
  itemsByCategory: Record<string, SystemConfigItem[]>;
  activeCategory: string;
  onSelect: (category: string) => void;
}

export const SettingsCategoryNav: React.FC<SettingsCategoryNavProps> = ({
  categories,
  itemsByCategory,
  activeCategory,
  onSelect,
}) => {
  /* Merge real categories with virtual ones, sorted by displayOrder. */
  const mergedCategories = useMemo(() => {
    type NavEntry = {
      category: string;
      title: string;
      description: string;
      displayOrder: number;
      count: number | null;
      badgeLabel?: string;
    };

    const entries: NavEntry[] = categories.map((c) => ({
      category: c.category,
      title: getCategoryTitleZh(c.category, c.title),
      description: getCategoryDescriptionZh(c.category, c.description),
      displayOrder: c.displayOrder,
      count: (itemsByCategory[c.category] || []).length,
    }));

    for (const vc of VIRTUAL_CATEGORIES) {
      // Only inject if no real category shares the same key.
      if (!entries.some((e) => e.category === vc.category)) {
        entries.push({
          category: vc.category,
          title: vc.title,
          description: vc.description,
          displayOrder: vc.displayOrder,
          count: null,
          badgeLabel: vc.badgeLabel,
        });
      }
    }

    return entries.sort((a, b) => a.displayOrder - b.displayOrder);
  }, [categories, itemsByCategory]);

  return (
    <div className="h-full rounded-[1.5rem] border settings-border bg-card/94 p-4 shadow-soft-card-strong backdrop-blur-sm">
      <div className="mb-4">
        <p className="settings-accent-text text-xs font-semibold uppercase tracking-[0.3em]">配置分类</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-text">按模块整理系统设置与认证能力。</p>
      </div>

      <div className="space-y-2.5">
        {mergedCategories.map((entry) => {
          const isActive = entry.category === activeCategory;

          return (
            <button
              key={entry.category}
              type="button"
              className={cn(
                'w-full rounded-[1.1rem] border px-3 py-3 text-left transition-[background-color,border-color,box-shadow,transform] duration-200',
                isActive
                  ? 'settings-nav-item-active'
                  : 'border-[var(--settings-border)] bg-[var(--settings-surface)] hover:border-[hsl(var(--primary)/0.32)] hover:bg-[hsl(var(--primary)/0.045)]',
              )}
              onClick={() => onSelect(entry.category)}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className={cn('text-sm font-semibold tracking-tight', isActive ? 'text-foreground' : 'text-secondary-text')}>
                    {entry.title}
                  </p>
                  {entry.description ? (
                    <p className={cn('mt-1 line-clamp-2 text-xs leading-5', isActive ? 'text-secondary-text' : 'text-muted-text')}>{entry.description}</p>
                  ) : null}
                </div>
                <Badge
                  variant={isActive ? 'info' : 'default'}
                  size="sm"
                  className={isActive ? 'settings-accent-badge border-[hsl(var(--primary)/0.36)]' : 'border-[var(--settings-border)] bg-[var(--settings-surface-hover)] text-muted-text'}
                >
                  {entry.badgeLabel ?? entry.count ?? 0}
                </Badge>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
