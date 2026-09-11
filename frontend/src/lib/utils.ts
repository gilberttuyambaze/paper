import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

const customTwMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'bg-color': [
        'bg-surface',
        'bg-surface-elevated',
        'bg-surface-hover',
        'bg-success',
        'bg-success-soft',
        'bg-success-foreground',
        'bg-warning',
        'bg-warning-soft',
        'bg-warning-foreground',
        'bg-error',
        'bg-error-soft',
        'bg-error-foreground',
        'bg-info',
        'bg-info-soft',
        'bg-info-foreground',
      ],
      'text-color': [
        'text-ink-primary',
        'text-ink-secondary',
        'text-ink-muted',
        'text-ink-disabled',
        'text-success',
        'text-success-soft',
        'text-success-foreground',
        'text-warning',
        'text-warning-soft',
        'text-warning-foreground',
        'text-error',
        'text-error-soft',
        'text-error-foreground',
        'text-info',
        'text-info-soft',
        'text-info-foreground',
      ],
      'border-color': [
        'border-success-border',
        'border-warning-border',
        'border-error-border',
        'border-info-border',
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return customTwMerge(clsx(inputs));
}

