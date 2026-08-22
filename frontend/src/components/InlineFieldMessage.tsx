import { CircleAlert, CircleCheck, Info, Sparkles, TriangleAlert } from 'lucide-react';

type Props = {
  message?: string;
  id?: string;
  tone?: 'error' | 'warning' | 'success' | 'info';
  automatic?: boolean;
};

const styles = {
  error: 'border-error-border bg-error-soft text-error-foreground shadow-[0_0_14px_rgba(220,38,38,0.14)]',
  warning: 'border-warning-border bg-warning-soft text-warning-foreground shadow-[0_0_14px_rgba(234,138,32,0.14)]',
  success: 'border-success-border bg-success-soft text-success-foreground shadow-[0_0_14px_rgba(34,197,94,0.14)]',
  info: 'border-info-border bg-info-soft text-info-foreground shadow-[0_0_14px_rgba(14,165,233,0.14)]',
};

const icons = {
  error: CircleAlert,
  warning: TriangleAlert,
  success: CircleCheck,
  info: Info,
};

export default function InlineFieldMessage({ message, id, tone = 'error', automatic = false }: Props) {
  const Icon = automatic ? Sparkles : icons[tone];
  return (
    <div className="min-h-6 pt-1" aria-live={tone === 'error' ? 'assertive' : 'polite'}>
      {message && (
        <p
          id={id}
          className={`inline-flex max-w-full items-start gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium leading-4 transition-all duration-200 animate-in fade-in-0 slide-in-from-top-1 motion-reduce:animate-none motion-reduce:transition-none ${styles[tone]}`}
          role={tone === 'error' ? 'alert' : 'status'}
          aria-atomic="true"
        >
          <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{message}</span>
        </p>
      )}
    </div>
  );
}