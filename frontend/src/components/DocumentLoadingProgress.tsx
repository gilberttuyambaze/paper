import { Download, FileText, LoaderCircle, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';

type Props = {
  resourceType: 'Paper' | 'Book' | 'Document' | string;
  stage?: string;
  loaded?: number;
  total?: number;
  percent?: number;
  error?: string | null;
  statusHttpCode?: number | null;
  onRetry?: () => void;
  onDownload?: () => void;
};

const formatBytes = (bytes?: number) => {
  if (bytes == null || bytes <= 0) return '';
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(mb >= 1 ? 1 : 2)} MB`;
};

/** Shared document loading progress component for Paper and Book readers. */
export default function DocumentLoadingProgress({
  resourceType,
  stage = 'Downloading document…',
  loaded,
  total,
  percent,
  error,
  statusHttpCode,
  onRetry,
  onDownload,
}: Props) {
  if (error) {
    let title = 'Unable to load document.';
    let description = error;

    if (statusHttpCode === 404 || error.toLowerCase().includes('not found') || error.toLowerCase().includes('missing')) {
      title = 'Document unavailable';
      description = 'This file could not be found in storage.';
    } else if (statusHttpCode === 403 || error.toLowerCase().includes('permission') || error.toLowerCase().includes('forbidden')) {
      title = "You don't have permission to access this document.";
      description = 'Please contact an administrator if you believe this is an error.';
    }

    return (
      <div className="theme-document-unavailable flex min-h-[360px] flex-col items-center justify-center gap-4 rounded-xl border border-dashed p-8 text-center" role="alert">
        <FileText className="h-12 w-12 text-muted-foreground" />
        <div>
          <p className="theme-title text-lg font-semibold">{title}</p>
          <p className="theme-muted mt-1 text-sm">{description}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3 mt-2">
          {onRetry && (
            <Button size="sm" variant="outline" onClick={onRetry} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          )}
          {onDownload && statusHttpCode !== 403 && (
            <Button size="sm" variant="outline" onClick={onDownload} className="gap-2">
              <Download className="h-4 w-4" />
              Download
            </Button>
          )}
        </div>
      </div>
    );
  }

  const determinate = typeof percent === 'number' && percent >= 0;
  const isComplete = percent === 100;
  const title = isComplete ? 'Opening document…' : `Downloading ${resourceType.toLowerCase()}`;
  const subtext = isComplete ? 'Preparing document…' : stage;

  return (
    <div className="theme-soft-panel flex min-h-[360px] flex-col items-center justify-center rounded-xl p-8 text-center" role="status" aria-live="polite">
      <div className="theme-accent-soft mb-5 flex h-14 w-14 items-center justify-center rounded-full">
        <LoaderCircle className="theme-section-icon h-7 w-7 animate-spin" />
      </div>
      <p className="theme-title text-lg font-semibold">{title}</p>
      {determinate && <p className="theme-title mt-3 text-3xl font-bold">{percent}%</p>}
      <div className="mt-4 h-2 w-full max-w-sm overflow-hidden rounded-full bg-muted">
        <div
          className={determinate ? 'h-full rounded-full bg-primary transition-all duration-200' : 'h-full w-2/5 animate-pulse rounded-full bg-primary'}
          style={determinate ? { width: `${Math.min(100, Math.max(0, percent))}%` } : undefined}
        />
      </div>
      <p className="theme-muted mt-4 text-sm">{subtext}</p>
      {loaded != null && loaded > 0 && (
        <p className="theme-muted mt-1 text-xs">
          {total != null && total > 0 ? `${formatBytes(loaded)} / ${formatBytes(total)}` : `${formatBytes(loaded)} downloaded`}
        </p>
      )}
    </div>
  );
}
