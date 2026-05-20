import type React from 'react';
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

interface HelpTipProps {
  /** The help content to display in the popover */
  content: React.ReactNode;
  /** Optional className for the trigger button */
  className?: string;
  /** Preferred side for the popover */
  side?: 'top' | 'bottom';
}

type PopoverStyle = {
  top: number;
  left: number;
};

/**
 * A small "?" badge that opens a help popover on click.
 * Used to explain risk alert meanings and recommended actions.
 */
export const HelpTip: React.FC<HelpTipProps> = ({ content, className = '', side = 'bottom' }) => {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const popoverId = useId();
  const [open, setOpen] = useState(false);
  const [resolvedSide, setResolvedSide] = useState<'top' | 'bottom'>(side);
  const [style, setStyle] = useState<PopoverStyle>({ top: 0, left: 0 });

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const popover = popoverRef.current;
    if (!trigger || !popover) {
      return;
    }

    const triggerRect = trigger.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const gap = 8;
    const margin = 12;

    let nextSide = side;
    let top =
      side === 'bottom'
        ? triggerRect.bottom + gap
        : triggerRect.top - popoverRect.height - gap;

    if (side === 'bottom' && top + popoverRect.height > viewportHeight - margin) {
      nextSide = 'top';
      top = triggerRect.top - popoverRect.height - gap;
    } else if (side === 'top' && top < margin) {
      nextSide = 'bottom';
      top = triggerRect.bottom + gap;
    }

    let left = triggerRect.left + triggerRect.width / 2 - popoverRect.width / 2;
    left = Math.max(margin, Math.min(left, viewportWidth - popoverRect.width - margin));
    top = Math.max(margin, Math.min(top, viewportHeight - popoverRect.height - margin));

    setResolvedSide(nextSide);
    setStyle({ top, left });
  }, [side]);

  useLayoutEffect(() => {
    if (!open) {
      return;
    }
    const frameId = window.requestAnimationFrame(() => {
      updatePosition();
    });
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [open, content, updatePosition]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handleViewportChange = () => updatePosition();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);

    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [open, updatePosition]);

  // Close on outside click
  useEffect(() => {
    if (!open) {
      return;
    }
    const handleClickOutside = (e: MouseEvent) => {
      if (
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node) &&
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) {
      return;
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={cn(
          'inline-flex items-center justify-center w-4 h-4 rounded-full',
          'bg-secondary/20 text-secondary hover:bg-secondary/30 hover:text-foreground',
          'transition-colors text-[10px] font-bold leading-none cursor-pointer',
          'focus:outline-none focus:ring-1 focus:ring-cyan/50',
          className,
        )}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={open ? popoverId : undefined}
        aria-label="帮助说明"
      >
        ?
      </button>

      {typeof document !== 'undefined' && open
        ? createPortal(
            <div
              ref={popoverRef}
              id={popoverId}
              role="dialog"
              aria-label="帮助提示"
              style={{
                position: 'fixed',
                top: style.top,
                left: style.left,
              }}
              className={cn(
                'z-[130] w-72 max-h-80 overflow-y-auto rounded-xl',
                'border border-border/70 bg-elevated/98 backdrop-blur-xl',
                'px-4 py-3 text-xs leading-relaxed text-foreground',
                'shadow-[0_16px_40px_rgba(3,8,20,0.22)]',
                resolvedSide === 'top' ? 'origin-bottom' : 'origin-top',
              )}
            >
              {content}
            </div>,
            document.body,
          )
        : null}
    </>
  );
};
