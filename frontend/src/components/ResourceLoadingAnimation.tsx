import type { CSSProperties } from 'react';

type Props = { resource: 'Paper' | 'Book' | 'Document'; progress?: number; stage?: string; className?: string };

/** Shared honest loading surface: progress is only supplied when known. */
export default function ResourceLoadingAnimation({ resource, progress, stage, className = '' }: Props) {
  const label = stage || `Preparing your ${resource.toLowerCase()}…`;
  return <div className={`w-full max-w-sm text-center ${className}`} role="status" aria-live="polite">
    <div className="upload-progress-orb mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={progress === undefined ? undefined : ({ '--upload-progress': `${progress}%` } as CSSProperties)}>
      <span className="rounded-full bg-background px-1 text-xs font-bold">{progress === undefined ? '…' : `${progress}%`}</span>
    </div>
    <p className="theme-title font-semibold">{label}</p>
    <p className="theme-muted mt-2 text-sm">{progress === undefined ? 'The reader remains available while the document is prepared.' : `${resource} reader is loading independently.`}</p>
    {progress !== undefined && <div className="upload-progress-track mt-4 h-2 overflow-hidden rounded-full" role="progressbar" aria-label={`${resource} reader loading progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><div className="upload-progress-fill h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${progress}%` }} /></div>}
  </div>;
}
